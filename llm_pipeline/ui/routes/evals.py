"""Eval system endpoints — thin Phoenix-backed passthrough.

Phase-3 rewrite: Phoenix is the source of truth for datasets, examples,
experiments, runs, and per-case results. The framework keeps just one
local table (``EvaluationAcceptance``) for the audit row written by
the accept-to-production walk.

Route surface (preserved from the legacy file's URL shapes):

- ``GET    /api/evals/datasets``                          list datasets
- ``GET    /api/evals/datasets/{dataset_id}``             one dataset + its examples
- ``POST   /api/evals/datasets``                          upload a new dataset
- ``DELETE /api/evals/datasets/{dataset_id}``             delete a dataset
- ``POST   /api/evals/datasets/{dataset_id}/cases``       add examples to a dataset
- ``DELETE /api/evals/datasets/{dataset_id}/cases/{ex}``  delete one example
- ``GET    /api/evals/datasets/{dataset_id}/runs``        list experiments for the dataset
- ``GET    /api/evals/datasets/{dataset_id}/runs/{exp}``  one experiment + per-case runs
- ``POST   /api/evals/datasets/{dataset_id}/runs``        trigger an evaluation
- ``POST   /api/evals/experiments/{exp_id}/accept``       accept-to-production walk
- ``GET    /api/evals/schema``                            JSON Schema for a target
- ``GET    /api/evals/delta-type-whitelist``              type whitelist for variant editor
- ``GET    /api/evals/datasets/{dataset_id}/prod-prompts``    resolved system+user prompts
- ``GET    /api/evals/datasets/{dataset_id}/prod-model``      resolved StepModelConfig

Eval runs execute in a background task because ``Dataset.evaluate`` is
async + multi-case + Phoenix-bound (potentially slow). Every other
endpoint is synchronous.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.evals.acceptance import AcceptanceError, accept_experiment
from llm_pipeline.evals.phoenix_client import (
    DatasetNotFoundError,
    ExperimentNotFoundError,
    PhoenixDatasetClient,
    PhoenixDatasetError,
)
from llm_pipeline.evals.runner import EvalTargetError, run_dataset
from llm_pipeline.evals.variants import Variant, get_type_whitelist
from llm_pipeline.ui.deps import DBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evals", tags=["evals"])


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class DatasetUploadRequest(BaseModel):
    name: str
    target_type: Literal["step", "pipeline"]
    target_name: str
    examples: List[dict]
    description: Optional[str] = None


class CaseAddRequest(BaseModel):
    examples: List[dict]


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
    """Resolve (and cache) the Phoenix datasets/experiments client."""
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


@router.get(
    "/delta-type-whitelist", response_model=TypeWhitelistResponse,
)
def get_delta_type_whitelist() -> TypeWhitelistResponse:
    """Allowed ``type_str`` values for the variant editor's instruction-delta UI."""
    return TypeWhitelistResponse(types=get_type_whitelist())


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


@router.get("/datasets")
def list_datasets(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    cursor: Optional[str] = Query(None),
) -> dict:
    return _phoenix_call(
        _client(request).list_datasets, limit=limit, cursor=cursor,
    )


@router.post("/datasets", status_code=201)
def upload_dataset(req: DatasetUploadRequest, request: Request) -> dict:
    return _phoenix_call(
        _client(request).upload_dataset,
        name=req.name,
        examples=req.examples,
        description=req.description,
        metadata={
            "target_type": req.target_type,
            "target_name": req.target_name,
        },
    )


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: str, request: Request) -> dict:
    client = _client(request)
    record = _phoenix_call(client.get_dataset, dataset_id)
    examples = _phoenix_call(client.list_examples, dataset_id)
    return {"dataset": record, "examples": examples}


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: str, request: Request) -> None:
    _phoenix_call(_client(request).delete_dataset, dataset_id)


@router.post("/datasets/{dataset_id}/cases", status_code=201)
def add_examples(
    dataset_id: str, req: CaseAddRequest, request: Request,
) -> dict:
    return _phoenix_call(
        _client(request).add_examples, dataset_id, req.examples,
    )


@router.delete(
    "/datasets/{dataset_id}/cases/{example_id}", status_code=204,
)
def delete_example(
    dataset_id: str, example_id: str, request: Request,
) -> None:
    _phoenix_call(_client(request).delete_example, dataset_id, example_id)


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


@router.post(
    "/datasets/{dataset_id}/runs", status_code=202,
)
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
            status_code=422,
            detail=f"variant payload invalid: {exc}",
        ) from exc

    engine = request.app.state.engine
    client = _client(request)

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
            ))
        except EvalTargetError:
            logger.exception("Eval target resolution failed")
        except Exception:
            logger.exception("Eval run failed")

    background.add_task(_runner)
    return {"status": "accepted", "dataset_id": dataset_id}


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
    """Walk the variant delta into production surfaces.

    Surfaces touched: ``StepModelConfig`` (model), Phoenix prompt
    versions (prompt overrides), source files (instructions delta).
    Inserts an ``EvaluationAcceptance`` audit row; returns it.
    """
    pipeline_registry: dict = getattr(
        request.app.state, "pipeline_registry", {},
    )
    if not pipeline_registry:
        raise HTTPException(
            status_code=422,
            detail="No pipelines registered.",
        )
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
# Production-config introspection (unchanged surface)
# ---------------------------------------------------------------------------


@router.get("/datasets/{dataset_id}/prod-model")
def get_dataset_prod_model(
    dataset_id: str, request: Request, db: DBSession,
) -> dict:
    """Return the ``StepModelConfig`` row for the dataset's step target."""
    client = _client(request)
    record = _phoenix_call(client.get_dataset, dataset_id)
    metadata = (record or {}).get("metadata") or {}
    target_type = metadata.get("target_type")
    target_name = metadata.get("target_name")
    if target_type != "step" or not target_name:
        raise HTTPException(
            status_code=422,
            detail="prod-model endpoint supports step-targets only.",
        )

    pipeline_registry: dict = getattr(
        request.app.state, "pipeline_registry", {},
    )
    pipeline_name, step_name = _resolve_step_target(
        pipeline_registry, target_name,
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


# ---------------------------------------------------------------------------
# Helpers (introspection schema + step lookup)
# ---------------------------------------------------------------------------


def _pipeline_schema(target_name: str, registry: dict) -> SchemaResponse:
    pipeline_record = registry.get(target_name)
    if pipeline_record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline {target_name!r} not found.",
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
