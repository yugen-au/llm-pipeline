"""Eval system endpoints — thin Phoenix-backed passthrough.

Phoenix is the source of truth for datasets, examples, experiments,
runs, and per-case results. The framework keeps one local table
(``EvaluationAcceptance``) for the audit row written by the
accept-to-production walk.

Datasets and examples cross every layer as the canonical ``Dataset`` /
``Example`` models defined in :mod:`llm_pipeline.evals.models`. The
translation from raw Phoenix dicts to those models happens here at
the route layer; consumers further in (runner, acceptance, frontend
types) only see the canonical shape.

Route surface:

- ``GET    /api/evals/datasets``                          list datasets
- ``GET    /api/evals/datasets/{dataset_id}``             one dataset + examples
- ``POST   /api/evals/datasets``                          upload a new dataset
- ``DELETE /api/evals/datasets/{dataset_id}``             delete a dataset
- ``POST   /api/evals/datasets/{dataset_id}/cases``       add examples
- ``DELETE /api/evals/datasets/{dataset_id}/cases/{ex}``  delete one example
- ``GET    /api/evals/datasets/{dataset_id}/runs``        list experiments
- ``GET    /api/evals/datasets/{dataset_id}/runs/{exp}``  one experiment + per-case runs
- ``POST   /api/evals/datasets/{dataset_id}/runs``        trigger an evaluation
- ``POST   /api/evals/experiments/{exp_id}/accept``       accept-to-production walk
- ``GET    /api/evals/schema``                            JSON Schema for a target
- ``GET    /api/evals/delta-type-whitelist``              type whitelist for variant editor
- ``GET    /api/evals/datasets/{dataset_id}/prod-prompts`` resolved system+user prompts
- ``GET    /api/evals/datasets/{dataset_id}/prod-model``   resolved StepModelConfig

Eval runs execute in a background task because ``Dataset.evaluate`` is
async + multi-case + Phoenix-bound. Every other endpoint is sync.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.evals.acceptance import AcceptanceError, accept_experiment
from llm_pipeline.evals.models import (
    Dataset,
    Example,
    dataset_to_phoenix_upload_kwargs,
    example_to_phoenix_payload,
    phoenix_to_dataset,
)
from llm_pipeline.evals.phoenix_client import (
    DatasetNotFoundError,
    ExperimentNotFoundError,
    PhoenixDatasetClient,
    PhoenixDatasetError,
)
from llm_pipeline.evals.runner import (
    EvalTargetError,
    create_experiment_record,
    run_dataset,
)
from llm_pipeline.evals.variants import Variant, get_type_whitelist
from llm_pipeline.ui.deps import DBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evals", tags=["evals"])


# ---------------------------------------------------------------------------
# Request / response shapes (only the ones that don't fit the canonical model)
# ---------------------------------------------------------------------------


class DatasetListResponse(BaseModel):
    items: List[Dataset]
    next_cursor: Optional[str] = None


class RunTriggerRequest(BaseModel):
    variant: Optional[dict] = None
    run_name: Optional[str] = None
    max_concurrency: Optional[int] = None


class AcceptRequest(BaseModel):
    accepted_by: Optional[str] = None
    notes: Optional[str] = None


class TypeWhitelistResponse(BaseModel):
    types: List[str]


class SchemaResponse(BaseModel):
    schema_: dict


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _client(request: Request) -> PhoenixDatasetClient:
    cached = getattr(request.app.state, "_phoenix_dataset_client", None)
    if cached is not None:
        return cached
    try:
        client = PhoenixDatasetClient()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Phoenix dataset client unavailable: {exc}",
        ) from exc
    request.app.state._phoenix_dataset_client = client
    return client


def _phoenix_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DatasetNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ExperimentNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PhoenixDatasetError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _fetch_dataset(client: PhoenixDatasetClient, dataset_id: str) -> Dataset:
    """Phoenix get_dataset + list_examples joined into the canonical model."""
    record = _phoenix_call(client.get_dataset, dataset_id)
    examples_payload = _phoenix_call(client.list_examples, dataset_id)
    return phoenix_to_dataset(record, examples_payload)


# ---------------------------------------------------------------------------
# Static endpoints (registered before parameterised paths)
# ---------------------------------------------------------------------------


@router.get("/schema", response_model=SchemaResponse)
def get_input_schema(
    request: Request,
    target_type: str = Query(..., pattern="^(step|pipeline)$"),
    target_name: str = Query(..., min_length=1),
) -> SchemaResponse:
    """JSON Schema for a step's INPUTS or a pipeline's INPUT_DATA."""
    introspection_registry: dict = getattr(
        request.app.state, "introspection_registry", {},
    )
    if target_type == "pipeline":
        return _pipeline_schema(target_name, introspection_registry)
    return _step_schema(target_name, introspection_registry)


@router.get("/delta-type-whitelist", response_model=TypeWhitelistResponse)
def get_delta_type_whitelist() -> TypeWhitelistResponse:
    """Allowed ``type_str`` values for the variant editor's instruction-delta UI."""
    return TypeWhitelistResponse(types=get_type_whitelist())


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


@router.get("/datasets", response_model=DatasetListResponse)
def list_datasets(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    cursor: Optional[str] = Query(None),
) -> DatasetListResponse:
    """List datasets — one row per Phoenix dataset, examples not populated."""
    payload = _phoenix_call(
        _client(request).list_datasets, limit=limit, cursor=cursor,
    )
    items = [phoenix_to_dataset(r) for r in (payload.get("data") or [])]
    return DatasetListResponse(items=items, next_cursor=payload.get("next_cursor"))


@router.post("/datasets", response_model=Dataset, status_code=201)
def upload_dataset(body: Dataset, request: Request) -> Dataset:
    """Create a new Phoenix dataset from a canonical ``Dataset`` payload."""
    kwargs = dataset_to_phoenix_upload_kwargs(body)
    record = _phoenix_call(_client(request).upload_dataset, **kwargs)
    return phoenix_to_dataset(record)


@router.get("/datasets/{dataset_id}", response_model=Dataset)
def get_dataset(dataset_id: str, request: Request) -> Dataset:
    """One dataset with its examples populated."""
    return _fetch_dataset(_client(request), dataset_id)


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, request: Request) -> Response:
    _phoenix_call(_client(request).delete_dataset, dataset_id)
    return Response(status_code=204)


@router.post(
    "/datasets/{dataset_id}/cases",
    response_model=Dataset,
    status_code=201,
)
def add_examples(
    dataset_id: str,
    body: List[Example],
    request: Request,
) -> Dataset:
    """Append examples; return the updated dataset (with all examples)."""
    client = _client(request)
    _phoenix_call(
        client.add_examples,
        dataset_id,
        [example_to_phoenix_payload(ex) for ex in body],
    )
    return _fetch_dataset(client, dataset_id)


@router.delete(
    "/datasets/{dataset_id}/cases/{example_id}", status_code=204,
)
def delete_example(
    dataset_id: str, example_id: str, request: Request,
) -> Response:
    _phoenix_call(_client(request).delete_example, dataset_id, example_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Experiments (== runs in the legacy frontend's vocabulary)
# ---------------------------------------------------------------------------


@router.get("/datasets/{dataset_id}/runs")
def list_experiments(dataset_id: str, request: Request) -> dict:
    return _phoenix_call(_client(request).list_experiments, dataset_id)


@router.get("/datasets/{dataset_id}/runs/{experiment_id}")
def get_experiment(
    dataset_id: str, experiment_id: str, request: Request,
) -> dict:
    client = _client(request)
    experiment = _phoenix_call(client.get_experiment, experiment_id)
    runs = _phoenix_call(client.list_runs, experiment_id)
    return {"experiment": experiment, "runs": runs}


@router.post("/datasets/{dataset_id}/runs", status_code=202)
def trigger_run(
    dataset_id: str,
    req: RunTriggerRequest,
    request: Request,
    background: BackgroundTasks,
) -> dict:
    """Launch an evaluation in the background; return immediately."""
    pipeline_registry: dict = getattr(
        request.app.state, "pipeline_registry", {},
    )
    if not pipeline_registry:
        raise HTTPException(
            status_code=422,
            detail=(
                "No pipelines registered. Discover or register pipelines "
                "before triggering evaluations."
            ),
        )

    default_model = getattr(request.app.state, "default_model", None)
    if not default_model and not (req.variant or {}).get("model"):
        raise HTTPException(
            status_code=422,
            detail=(
                "No model configured. Set LLM_PIPELINE_MODEL or pass "
                "a variant with an explicit model override."
            ),
        )

    try:
        variant = Variant.model_validate(req.variant or {})
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail=f"variant payload invalid: {exc}",
        ) from exc

    engine = request.app.state.engine
    client = _client(request)

    # Resolve the dataset's target_type / target_name first so a malformed
    # dataset surfaces synchronously (not buried inside the background task).
    record = _phoenix_call(client.get_dataset, dataset_id)
    dataset = phoenix_to_dataset(record)
    target_type = dataset.metadata.target_type
    target_name = dataset.metadata.target_name
    if target_type is None or not target_name:
        raise HTTPException(
            status_code=422,
            detail=(
                "Dataset metadata is missing target_type / target_name; "
                "cannot trigger an evaluation."
            ),
        )

    try:
        experiment = create_experiment_record(
            client=client,
            dataset_id=dataset_id,
            variant=variant,
            target_type=target_type,
            target_name=target_name,
            run_name=req.run_name,
        )
    except PhoenixDatasetError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    experiment_id = experiment.get("id") or experiment.get("experiment_id")
    if not experiment_id:
        raise HTTPException(
            status_code=502,
            detail="Phoenix create_experiment returned no id.",
        )

    def _runner() -> None:
        try:
            asyncio.run(run_dataset(
                dataset_id,
                variant,
                pipeline_registry=pipeline_registry,
                model=default_model or variant.model or "",
                engine=engine,
                run_name=req.run_name,
                max_concurrency=req.max_concurrency,
                client=client,
                experiment_id=experiment_id,
            ))
        except EvalTargetError:
            logger.exception("Eval target resolution failed")
        except Exception:
            logger.exception("Eval run failed")

    background.add_task(_runner)
    return {
        "status": "accepted",
        "dataset_id": dataset_id,
        "experiment_id": experiment_id,
    }


# ---------------------------------------------------------------------------
# Accept-to-production
# ---------------------------------------------------------------------------


@router.post("/experiments/{experiment_id}/accept")
def post_accept_experiment(
    experiment_id: str,
    req: AcceptRequest,
    request: Request,
    db: DBSession,
) -> dict:
    """Walk the variant delta into production surfaces."""
    pipeline_registry: dict = getattr(
        request.app.state, "pipeline_registry", {},
    )
    if not pipeline_registry:
        raise HTTPException(status_code=422, detail="No pipelines registered.")
    engine = request.app.state.engine
    client = _client(request)

    try:
        row = accept_experiment(
            experiment_id,
            pipeline_registry=pipeline_registry,
            engine=engine,
            dataset_client=client,
            accepted_by=req.accepted_by,
            notes=req.notes,
        )
    except AcceptanceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (DatasetNotFoundError, ExperimentNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PhoenixDatasetError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "id": row.id,
        "experiment_id": row.experiment_id,
        "dataset_id": row.dataset_id,
        "pipeline_name": row.pipeline_name,
        "step_name": row.step_name,
        "delta_summary": row.delta_summary,
        "accept_paths": row.accept_paths,
        "accepted_at": row.accepted_at.isoformat(),
        "accepted_by": row.accepted_by,
        "notes": row.notes,
    }


# ---------------------------------------------------------------------------
# Production-config introspection
# ---------------------------------------------------------------------------


@router.get("/datasets/{dataset_id}/prod-model")
def get_dataset_prod_model(
    dataset_id: str, request: Request, db: DBSession,
) -> dict:
    """Return the ``StepModelConfig`` row for the dataset's step target."""
    client = _client(request)
    record = _phoenix_call(client.get_dataset, dataset_id)
    dataset = phoenix_to_dataset(record)
    if dataset.metadata.target_type != "step" or not dataset.metadata.target_name:
        raise HTTPException(
            status_code=422,
            detail="prod-model endpoint supports step-targets only.",
        )

    pipeline_registry: dict = getattr(
        request.app.state, "pipeline_registry", {},
    )
    pipeline_name, step_name = _resolve_step_target(
        pipeline_registry, dataset.metadata.target_name,
    )

    from llm_pipeline.db.step_config import StepModelConfig

    cfg = db.exec(
        select(StepModelConfig).where(
            StepModelConfig.pipeline_name == pipeline_name,
            StepModelConfig.step_name == step_name,
        ),
    ).first()
    if cfg is None:
        return {"pipeline_name": pipeline_name, "step_name": step_name, "model": None}
    return {
        "pipeline_name": pipeline_name,
        "step_name": step_name,
        "model": cfg.model,
        "request_limit": cfg.request_limit,
    }


@router.get("/datasets/{dataset_id}/prod-prompts")
def get_dataset_prod_prompts(
    dataset_id: str, request: Request,
) -> dict:
    """Return the production system + user prompt content for a step target."""
    from llm_pipeline.prompts.phoenix_client import (
        PhoenixError,
        PhoenixPromptClient,
        PromptNotFoundError,
    )

    client = _client(request)
    record = _phoenix_call(client.get_dataset, dataset_id)
    dataset = phoenix_to_dataset(record)
    if dataset.metadata.target_type != "step" or not dataset.metadata.target_name:
        raise HTTPException(
            status_code=422,
            detail="prod-prompts endpoint supports step-targets only.",
        )

    pipeline_registry: dict = getattr(
        request.app.state, "pipeline_registry", {},
    )
    node_cls = _resolve_step_node(pipeline_registry, dataset.metadata.target_name)
    prompt_name = node_cls.resolved_prompt_name()
    step_name = node_cls.step_name()

    cached = getattr(request.app.state, "_phoenix_prompt_client", None)
    try:
        prompt_client = cached if cached is not None else PhoenixPromptClient()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Phoenix prompt client unavailable: {exc}",
        ) from exc
    request.app.state._phoenix_prompt_client = prompt_client

    try:
        version = prompt_client.get_by_tag(prompt_name, "production")
    except PromptNotFoundError:
        try:
            version = prompt_client.get_latest(prompt_name)
        except PromptNotFoundError:
            return {
                "prompt_name": prompt_name,
                "step_name": step_name,
                "system": None,
                "user": None,
                "variable_definitions": None,
            }
    except PhoenixError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    system_text, user_text = _split_chat_messages(version)

    record_metadata: dict = {}
    try:
        for record in (prompt_client.list_prompts(limit=200) or {}).get("data") or []:
            if record.get("name") == prompt_name:
                record_metadata = record.get("metadata") or {}
                break
    except PhoenixError:
        pass

    return {
        "prompt_name": prompt_name,
        "step_name": step_name,
        "system": system_text,
        "user": user_text,
        "variable_definitions": record_metadata.get("variable_definitions"),
    }


# ---------------------------------------------------------------------------
# Helpers (introspection schema + step lookup)
# ---------------------------------------------------------------------------


def _pipeline_schema(target_name: str, registry: dict) -> SchemaResponse:
    pipeline_record = registry.get(target_name)
    if pipeline_record is None:
        raise HTTPException(
            status_code=404, detail=f"Pipeline {target_name!r} not found.",
        )
    pipeline_cls = pipeline_record.get("pipeline_class") if isinstance(
        pipeline_record, dict,
    ) else pipeline_record
    input_cls = getattr(pipeline_cls, "INPUT_DATA", None)
    if input_cls is None:
        return SchemaResponse(schema_={})
    return SchemaResponse(schema_=input_cls.model_json_schema())


def _step_schema(target_name: str, registry: dict) -> SchemaResponse:
    for record in registry.values():
        pipeline_cls = record.get("pipeline_class") if isinstance(
            record, dict,
        ) else record
        for node_cls in getattr(pipeline_cls, "nodes", []):
            if node_cls.__name__ == target_name:
                inputs_cls = getattr(node_cls, "INPUTS", None)
                if inputs_cls is None:
                    return SchemaResponse(schema_={})
                return SchemaResponse(schema_=inputs_cls.model_json_schema())
    raise HTTPException(
        status_code=404, detail=f"Step {target_name!r} not found.",
    )


def _resolve_step_node(registry: dict, step_class_name: str) -> Any:
    """Find the ``LLMStepNode`` subclass with ``__name__ == step_class_name``."""
    for record in registry.values():
        pipeline_cls = record.get("pipeline_class") if isinstance(
            record, dict,
        ) else record
        for node_cls in getattr(pipeline_cls, "nodes", []):
            if node_cls.__name__ == step_class_name:
                return node_cls
    raise HTTPException(
        status_code=404,
        detail=f"Step {step_class_name!r} not found in any registered pipeline.",
    )


def _split_chat_messages(
    version: dict[str, Any],
) -> tuple[Optional[str], Optional[str]]:
    """Pull system + user message text out of a Phoenix CHAT prompt version."""
    template = (version or {}).get("template") or {}
    if template.get("type") == "string":
        body = template.get("template")
        return (None, body) if isinstance(body, str) else (None, None)
    if template.get("type") != "chat":
        return None, None
    system_text: Optional[str] = None
    user_text: Optional[str] = None
    for msg in template.get("messages") or []:
        role = msg.get("role")
        content = msg.get("content")
        text = _flatten_message_content(content)
        if role in {"system", "developer"} and system_text is None:
            system_text = text
        elif role == "user" and user_text is None:
            user_text = text
    return system_text, user_text


def _flatten_message_content(content: Any) -> Optional[str]:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            p.get("text") for p in content
            if isinstance(p, dict) and p.get("type") == "text"
        ]
        joined = "".join(t for t in parts if isinstance(t, str))
        return joined or None
    return None


def _resolve_step_target(
    registry: dict, step_class_name: str,
) -> tuple[str, str]:
    for record in registry.values():
        pipeline_cls = record.get("pipeline_class") if isinstance(
            record, dict,
        ) else record
        for node_cls in getattr(pipeline_cls, "nodes", []):
            if node_cls.__name__ == step_class_name:
                return pipeline_cls.pipeline_name(), node_cls.step_name()
    raise HTTPException(
        status_code=404,
        detail=f"Step {step_class_name!r} not found in any registered pipeline.",
    )
