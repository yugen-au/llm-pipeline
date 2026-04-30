"""Pipeline configurations route module -- list and detail endpoints."""
import logging
from typing import Any, List, Optional

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.db.pipeline_visibility import PipelineVisibility
from llm_pipeline.introspection import PipelineIntrospector, enrich_with_prompt_readiness
from llm_pipeline.prompts.models import PromptMessage
from llm_pipeline.ui.deps import DBSession, WritableDBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

# ---------------------------------------------------------------------------
# Response models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class PipelineListItem(BaseModel):
    name: str
    status: Optional[str] = None  # draft | published
    strategy_count: Optional[int] = None
    step_count: Optional[int] = None
    has_input_schema: bool = False
    registry_model_count: Optional[int] = None
    error: Optional[str] = None


class PipelineListResponse(BaseModel):
    pipelines: List[PipelineListItem]


class StepMetadata(BaseModel):
    model_config = {"extra": "allow"}

    step_name: str
    class_name: str
    prompt_name: Optional[str] = None
    instructions_class: Optional[str] = None
    instructions_schema: Optional[Any] = None
    context_class: Optional[str] = None
    context_schema: Optional[Any] = None
    extractions: List[Any] = []
    transformation: Optional[Any] = None
    action_after: Optional[str] = None


class StrategyMetadata(BaseModel):
    name: str
    display_name: str
    class_name: str
    steps: List[StepMetadata] = []
    error: Optional[str] = None


class PipelineMetadata(BaseModel):
    pipeline_name: str
    registry_models: List[str] = []
    strategies: List[StrategyMetadata] = []
    execution_order: List[str] = []
    pipeline_input_schema: Optional[Any] = None


class StepPromptItem(BaseModel):
    name: str
    messages: List[PromptMessage]
    version_id: str


class StepPromptsResponse(BaseModel):
    pipeline_name: str
    step_name: str
    prompts: List[StepPromptItem]


# ---------------------------------------------------------------------------
# Endpoints (all sync def -- no DB access, reads from app.state)
# ---------------------------------------------------------------------------


@router.get("", response_model=PipelineListResponse)
def list_pipelines(
    request: Request,
    db: DBSession,
    status: Optional[str] = Query(None, description="Filter by status: draft or published"),
) -> PipelineListResponse:
    """List all registered pipelines with summary metadata."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})

    # Load visibility status from DB
    vis_map: dict[str, str] = {}
    for row in db.exec(select(PipelineVisibility)).all():
        vis_map[row.pipeline_name] = row.status

    items: List[PipelineListItem] = []
    for name, pipeline_cls in sorted(registry.items(), key=lambda x: x[0]):
        pipeline_status = vis_map.get(name, "draft")
        if status and pipeline_status != status:
            continue
        try:
            metadata = PipelineIntrospector(pipeline_cls).get_metadata()
            strategies = metadata.get("strategies", [])
            strategy_count = len(strategies)
            step_count = sum(len(s.get("steps", [])) for s in strategies)
            registry_models = metadata.get("registry_models", [])

            has_input_schema = metadata.get("pipeline_input_schema") is not None

            items.append(PipelineListItem(
                name=name,
                status=pipeline_status,
                strategy_count=strategy_count,
                step_count=step_count,
                has_input_schema=has_input_schema,
                registry_model_count=len(registry_models),
            ))
        except Exception as exc:
            logger.warning("Failed to introspect pipeline '%s': %s", name, exc)
            items.append(PipelineListItem(
                name=name,
                status=pipeline_status,
                error=str(exc),
            ))

    return PipelineListResponse(pipelines=items)


@router.get("/{name}", response_model=PipelineMetadata)
def get_pipeline(name: str, request: Request, db: DBSession) -> PipelineMetadata:
    """Full introspection detail for a single pipeline."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})

    if name not in registry:
        raise HTTPException(
            status_code=404, detail=f"Pipeline '{name}' not found"
        )

    pipeline_cls = registry[name]
    try:
        metadata = PipelineIntrospector(pipeline_cls).get_metadata()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    enrich_with_prompt_readiness(metadata, db)
    return PipelineMetadata(**metadata)


@router.get("/{name}/steps/{step_name}/prompts", response_model=StepPromptsResponse)
def get_step_prompts(
    name: str,
    step_name: str,
    request: Request,
    db: DBSession,
) -> StepPromptsResponse:
    """Return prompt content for a pipeline step (Phase E: Phoenix-backed)."""
    from llm_pipeline.introspection import _compile_bind_for_introspection
    from llm_pipeline.prompts.phoenix_client import (
        PhoenixError,
        PhoenixPromptClient,
        PromptNotFoundError,
    )

    registry: dict = getattr(request.app.state, "introspection_registry", {})
    if name not in registry:
        raise HTTPException(
            status_code=404, detail=f"Pipeline '{name}' not found"
        )

    pipeline_cls = registry[name]
    prompt_names: set[str] = set()

    strategies_cls = getattr(pipeline_cls, "STRATEGIES", None)
    strategy_classes = (
        getattr(strategies_cls, "STRATEGIES", []) if strategies_cls else []
    ) or []

    for strategy_cls in strategy_classes:
        try:
            strategy = strategy_cls()
        except Exception:
            logger.debug(
                "Failed to instantiate strategy %s for step prompts",
                strategy_cls.__name__, exc_info=True,
            )
            continue

        try:
            bindings = strategy.get_bindings()
        except Exception:
            logger.debug(
                "Failed to get_bindings for %s", strategy_cls.__name__,
                exc_info=True,
            )
            continue

        for bind in bindings:
            try:
                sd = _compile_bind_for_introspection(bind)
            except Exception:
                logger.debug(
                    "Failed to compile bind for %s",
                    strategy_cls.__name__, exc_info=True,
                )
                continue
            if sd.step_name != step_name:
                continue
            if sd.resolved_prompt_name:
                prompt_names.add(sd.resolved_prompt_name)

    if not prompt_names:
        return StepPromptsResponse(
            pipeline_name=name, step_name=step_name, prompts=[]
        )

    try:
        client = PhoenixPromptClient()
    except PhoenixError:
        return StepPromptsResponse(
            pipeline_name=name, step_name=step_name, prompts=[],
        )

    items: list[StepPromptItem] = []
    for prompt_name in sorted(prompt_names):
        try:
            version = client.get_latest(prompt_name)
        except (PhoenixError, PromptNotFoundError):
            continue
        version_id = version.get("id") or ""
        template = version.get("template") or {}
        if template.get("type") != "chat":
            continue
        messages: List[PromptMessage] = []
        for msg in template.get("messages") or []:
            role = msg.get("role")
            content = msg.get("content")
            if not isinstance(content, str):
                continue
            if role in ("system", "developer"):
                ui_role = "system"
            elif role == "user":
                ui_role = "user"
            else:
                continue
            messages.append(PromptMessage(role=ui_role, content=content))
        if not messages:
            continue
        items.append(
            StepPromptItem(
                name=prompt_name, messages=messages, version_id=version_id,
            )
        )

    return StepPromptsResponse(
        pipeline_name=name, step_name=step_name, prompts=items,
    )


# ---------------------------------------------------------------------------
# Pipeline visibility endpoints
# ---------------------------------------------------------------------------


class PipelineStatusRequest(BaseModel):
    status: Literal["draft", "published"]


@router.get("/{name}/status")
def get_pipeline_status(name: str, request: Request, db: DBSession):
    """Get the visibility status of a pipeline."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")
    row = db.exec(
        select(PipelineVisibility).where(PipelineVisibility.pipeline_name == name)
    ).first()
    return {"pipeline_name": name, "status": row.status if row else "draft"}


@router.put("/{name}/status")
def put_pipeline_status(
    name: str,
    body: PipelineStatusRequest,
    request: Request,
    db: WritableDBSession,
):
    """Set pipeline visibility status (draft or published)."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")

    row = db.exec(
        select(PipelineVisibility).where(PipelineVisibility.pipeline_name == name)
    ).first()
    if row:
        row.status = body.status
        row.updated_at = datetime.now(timezone.utc)
    else:
        db.add(PipelineVisibility(pipeline_name=name, status=body.status))
    db.commit()
    return {"pipeline_name": name, "status": body.status}


# ---------------------------------------------------------------------------
# Step model endpoints — RETIRED
# ---------------------------------------------------------------------------
#
# The per-step model used to live in the ``step_model_configs`` table,
# resolved via a three-tier resolver. After the Phoenix-owned-model
# refactor, the model is a property of the Phoenix prompt — declared in
# YAML (``llm-pipeline-prompts/{step_name}.yaml``) and pushed at
# ``uv run llm-pipeline build``. There is no DB row to GET/PUT/DELETE.
#
# These endpoints stay registered (returning HTTP 410 Gone) so the
# frontend gets a clear, intentional retirement signal instead of 404.
# Removing them entirely is a follow-up once the frontend stops calling.


_STEP_MODEL_RETIRED_DETAIL = (
    "Per-step model overrides moved to Phoenix. Edit the prompt's "
    "`model:` field in llm-pipeline-prompts/{step_name}.yaml and run "
    "`uv run llm-pipeline build` to push, or edit directly in Phoenix "
    "Playground."
)


@router.get("/{name}/steps/{step_name}/model")
def get_step_model(name: str, step_name: str, request: Request):
    """Retired endpoint. The model lives on the Phoenix prompt now."""
    del name, step_name, request
    raise HTTPException(status_code=410, detail=_STEP_MODEL_RETIRED_DETAIL)


@router.put("/{name}/steps/{step_name}/model")
def put_step_model(name: str, step_name: str, request: Request):
    """Retired endpoint. The model lives on the Phoenix prompt now."""
    del name, step_name, request
    raise HTTPException(status_code=410, detail=_STEP_MODEL_RETIRED_DETAIL)


@router.delete("/{name}/steps/{step_name}/model")
def delete_step_model(name: str, step_name: str, request: Request):
    """Retired endpoint. The model lives on the Phoenix prompt now."""
    del name, step_name, request
    raise HTTPException(status_code=410, detail=_STEP_MODEL_RETIRED_DETAIL)
