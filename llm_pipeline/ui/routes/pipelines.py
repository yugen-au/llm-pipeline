"""Pipeline configurations route module -- list and detail endpoints."""
import logging
from typing import Any, List, Optional

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.db.step_config import StepModelConfig
from llm_pipeline.db.pipeline_visibility import PipelineVisibility
from llm_pipeline.introspection import PipelineIntrospector, enrich_with_prompt_readiness
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
    system_key: Optional[str] = None
    user_key: Optional[str] = None
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


class StepModelRequest(BaseModel):
    model: str


class StepPromptItem(BaseModel):
    prompt_key: str
    prompt_type: str
    content: str
    required_variables: Optional[List[str]] = None
    version: str


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
    """Return prompt/instruction content for a pipeline step."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})
    if name not in registry:
        raise HTTPException(
            status_code=404, detail=f"Pipeline '{name}' not found"
        )

    # Collect prompt keys declared by this step in this pipeline via
    # introspection to prevent cross-pipeline leakage when two pipelines
    # share the same step_name.
    pipeline_cls = registry[name]
    metadata = PipelineIntrospector(pipeline_cls).get_metadata()
    declared_keys: set[str] = set()
    for strategy in metadata.get("strategies", []):
        for step in strategy.get("steps", []):
            if step.get("step_name") == step_name:
                if step.get("system_key"):
                    declared_keys.add(step["system_key"])
                if step.get("user_key"):
                    declared_keys.add(step["user_key"])

    if not declared_keys:
        return StepPromptsResponse(
            pipeline_name=name, step_name=step_name, prompts=[]
        )

    stmt = select(Prompt).where(Prompt.prompt_key.in_(declared_keys))  # type: ignore[union-attr]
    prompts = db.exec(stmt).all()

    return StepPromptsResponse(
        pipeline_name=name,
        step_name=step_name,
        prompts=[
            StepPromptItem(
                prompt_key=p.prompt_key,
                prompt_type=p.prompt_type,
                content=p.content,
                required_variables=p.required_variables,
                version=p.version,
            )
            for p in prompts
        ],
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
# Step model config endpoints
# ---------------------------------------------------------------------------


def _find_step_model_from_introspection(
    registry: dict, pipeline_name: str, step_name: str,
) -> Optional[str]:
    """Return step-level model from introspection metadata, or None."""
    pipeline_cls = registry.get(pipeline_name)
    if pipeline_cls is None:
        return None
    metadata = PipelineIntrospector(pipeline_cls).get_metadata()
    for strategy in metadata.get("strategies", []):
        for step in strategy.get("steps", []):
            if step.get("step_name") == step_name:
                return step.get("model")
    return None


@router.get("/{name}/steps/{step_name}/model")
def get_step_model(
    name: str,
    step_name: str,
    request: Request,
    db: DBSession,
):
    """Get the effective model for a pipeline step."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")

    stmt = select(StepModelConfig).where(
        StepModelConfig.pipeline_name == name,
        StepModelConfig.step_name == step_name,
    )
    row = db.exec(stmt).first()
    if row is not None:
        return {"model": row.model, "source": "db"}

    introspected_model = _find_step_model_from_introspection(registry, name, step_name)
    if introspected_model is not None:
        return {"model": introspected_model, "source": "step_definition"}

    return {"model": None, "source": "pipeline_default"}


@router.put("/{name}/steps/{step_name}/model")
def put_step_model(
    name: str,
    step_name: str,
    body: StepModelRequest,
    request: Request,
    db: WritableDBSession,
):
    """Set or update the model override for a pipeline step."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")

    stmt = select(StepModelConfig).where(
        StepModelConfig.pipeline_name == name,
        StepModelConfig.step_name == step_name,
    )
    row = db.exec(stmt).first()
    if row is not None:
        row.model = body.model
    else:
        row = StepModelConfig(
            pipeline_name=name,
            step_name=step_name,
            model=body.model,
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "pipeline_name": row.pipeline_name, "step_name": row.step_name, "model": row.model}


@router.delete("/{name}/steps/{step_name}/model")
def delete_step_model(
    name: str,
    step_name: str,
    request: Request,
    db: WritableDBSession,
):
    """Remove a model override for a pipeline step."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})
    if name not in registry:
        raise HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")

    stmt = select(StepModelConfig).where(
        StepModelConfig.pipeline_name == name,
        StepModelConfig.step_name == step_name,
    )
    row = db.exec(stmt).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Model override not found")

    db.delete(row)
    db.commit()
    return {"detail": "Model override removed"}
