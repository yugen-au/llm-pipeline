"""Pipeline configurations route module -- list and detail endpoints."""
import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.ui.deps import DBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pipelines", tags=["pipelines"])

# ---------------------------------------------------------------------------
# Response models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class PipelineListItem(BaseModel):
    name: str
    strategy_count: Optional[int] = None
    step_count: Optional[int] = None
    has_input_schema: bool = False
    registry_model_count: Optional[int] = None
    error: Optional[str] = None


class PipelineListResponse(BaseModel):
    pipelines: List[PipelineListItem]


class StepMetadata(BaseModel):
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
def list_pipelines(request: Request) -> PipelineListResponse:
    """List all registered pipelines with summary metadata."""
    registry: dict = getattr(request.app.state, "introspection_registry", {})

    items: List[PipelineListItem] = []
    for name, pipeline_cls in sorted(registry.items(), key=lambda x: x[0]):
        try:
            metadata = PipelineIntrospector(pipeline_cls).get_metadata()
            strategies = metadata.get("strategies", [])
            strategy_count = len(strategies)
            step_count = sum(len(s.get("steps", [])) for s in strategies)
            registry_models = metadata.get("registry_models", [])

            has_input_schema = any(
                step.get("instructions_schema") is not None
                for strategy in strategies
                for step in strategy.get("steps", [])
            )

            items.append(PipelineListItem(
                name=name,
                strategy_count=strategy_count,
                step_count=step_count,
                has_input_schema=has_input_schema,
                registry_model_count=len(registry_models),
            ))
        except Exception as exc:
            logger.warning("Failed to introspect pipeline '%s': %s", name, exc)
            items.append(PipelineListItem(
                name=name,
                error=str(exc),
            ))

    return PipelineListResponse(pipelines=items)


@router.get("/{name}", response_model=PipelineMetadata)
def get_pipeline(name: str, request: Request) -> PipelineMetadata:
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
