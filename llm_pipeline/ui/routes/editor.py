"""Editor route module -- compile, available steps, DraftPipeline CRUD."""
import logging
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.state import DraftPipeline, DraftStep, utc_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/editor", tags=["editor"])

# ---------------------------------------------------------------------------
# Request / response models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class EditorStep(BaseModel):
    step_ref: str
    source: Literal["draft", "registered"]
    position: int


class EditorStrategy(BaseModel):
    strategy_name: str
    steps: list[EditorStep]


class CompileRequest(BaseModel):
    strategies: list[EditorStrategy]


class CompileError(BaseModel):
    strategy_name: str
    step_ref: str
    message: str


class CompileResponse(BaseModel):
    valid: bool
    errors: list[CompileError]


class AvailableStep(BaseModel):
    step_ref: str
    source: Literal["draft", "registered"]
    status: str | None = None
    pipeline_names: list[str] = []


class AvailableStepsResponse(BaseModel):
    steps: list[AvailableStep]


class DraftPipelineItem(BaseModel):
    id: int
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class DraftPipelineDetail(DraftPipelineItem):
    structure: dict
    compilation_errors: dict | None = None


class CreateDraftPipelineRequest(BaseModel):
    name: str
    structure: dict


class UpdateDraftPipelineRequest(BaseModel):
    name: str | None = None
    structure: dict | None = None


class DraftPipelineListResponse(BaseModel):
    items: list[DraftPipelineItem]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_registered_steps(
    introspection_registry: dict,
) -> dict[str, list[str]]:
    """Build step_name -> [pipeline_names] from introspection registry.

    Returns a dict mapping each step_name (snake_case) to the list of
    pipeline names that contain it.
    """
    step_pipelines: dict[str, list[str]] = {}
    for pipeline_name, pipeline_cls in introspection_registry.items():
        try:
            metadata = PipelineIntrospector(pipeline_cls).get_metadata()
        except Exception:
            logger.warning(
                "Failed to introspect pipeline '%s' for editor, skipping",
                pipeline_name,
                exc_info=True,
            )
            continue
        for strategy in metadata.get("strategies", []):
            for step in strategy.get("steps", []):
                sn = step.get("step_name")
                if sn:
                    step_pipelines.setdefault(sn, [])
                    if pipeline_name not in step_pipelines[sn]:
                        step_pipelines[sn].append(pipeline_name)
    return step_pipelines


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/compile", response_model=CompileResponse)
def compile_pipeline(body: CompileRequest, request: Request) -> CompileResponse:
    """Validate step_refs exist in introspection registry or non-errored DraftSteps.

    Structural validation only -- no LLM calls.
    """
    engine = request.app.state.engine
    introspection_registry: dict = getattr(
        request.app.state, "introspection_registry", {}
    )

    # Build set of known registered step names
    registered_steps = set(_collect_registered_steps(introspection_registry).keys())

    # Build set of non-errored draft step names
    with Session(engine) as session:
        stmt = select(DraftStep.name).where(DraftStep.status != "error")
        draft_names = set(session.exec(stmt).all())

    known = registered_steps | draft_names

    errors: list[CompileError] = []
    for strategy in body.strategies:
        for step in strategy.steps:
            if step.step_ref not in known:
                errors.append(
                    CompileError(
                        strategy_name=strategy.strategy_name,
                        step_ref=step.step_ref,
                        message=f"Step '{step.step_ref}' not found in registered steps or non-errored drafts",
                    )
                )

    return CompileResponse(valid=len(errors) == 0, errors=errors)


@router.get("/available-steps", response_model=AvailableStepsResponse)
def available_steps(request: Request) -> AvailableStepsResponse:
    """Merged non-errored DraftSteps + registered steps, deduplicated by step_ref.

    Registered wins on name clash; pipeline_names included for provenance.
    """
    engine = request.app.state.engine
    introspection_registry: dict = getattr(
        request.app.state, "introspection_registry", {}
    )

    # Registered steps with pipeline provenance
    registered_map = _collect_registered_steps(introspection_registry)

    # Non-errored draft steps
    with Session(engine) as session:
        stmt = select(DraftStep).where(DraftStep.status != "error")
        drafts = session.exec(stmt).all()

    # Build result: registered first, then drafts (skip duplicates)
    result: list[AvailableStep] = []
    seen: set[str] = set()

    for step_name, pipelines in sorted(registered_map.items()):
        result.append(
            AvailableStep(
                step_ref=step_name,
                source="registered",
                status=None,
                pipeline_names=pipelines,
            )
        )
        seen.add(step_name)

    for draft in drafts:
        if draft.name not in seen:
            result.append(
                AvailableStep(
                    step_ref=draft.name,
                    source="draft",
                    status=draft.status,
                    pipeline_names=[],
                )
            )
            seen.add(draft.name)

    return AvailableStepsResponse(steps=result)


# ---------------------------------------------------------------------------
# DraftPipeline CRUD
# ---------------------------------------------------------------------------


@router.post("/drafts", response_model=DraftPipelineDetail, status_code=201)
def create_draft_pipeline(
    body: CreateDraftPipelineRequest, request: Request
) -> DraftPipelineDetail | JSONResponse:
    """Create a new DraftPipeline."""
    engine = request.app.state.engine
    with Session(engine) as session:
        draft = DraftPipeline(
            name=body.name,
            structure=body.structure,
        )
        session.add(draft)
        try:
            session.commit()
            session.refresh(draft)
        except IntegrityError:
            session.rollback()
            return JSONResponse(
                status_code=409,
                content={"detail": "name_conflict", "name": body.name},
            )

        return DraftPipelineDetail(
            id=draft.id,
            name=draft.name,
            status=draft.status,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            structure=draft.structure,
            compilation_errors=draft.compilation_errors,
        )


@router.get("/drafts", response_model=DraftPipelineListResponse)
def list_draft_pipelines(request: Request) -> DraftPipelineListResponse:
    """List all DraftPipelines ordered by created_at desc."""
    engine = request.app.state.engine
    with Session(engine) as session:
        stmt = select(DraftPipeline).order_by(DraftPipeline.created_at.desc())
        rows = session.exec(stmt).all()
        return DraftPipelineListResponse(
            items=[
                DraftPipelineItem(
                    id=d.id,
                    name=d.name,
                    status=d.status,
                    created_at=d.created_at,
                    updated_at=d.updated_at,
                )
                for d in rows
            ],
            total=len(rows),
        )


@router.get("/drafts/{draft_id}", response_model=DraftPipelineDetail)
def get_draft_pipeline(draft_id: int, request: Request) -> DraftPipelineDetail:
    """Get a single DraftPipeline by ID."""
    engine = request.app.state.engine
    with Session(engine) as session:
        draft = session.get(DraftPipeline, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Draft pipeline not found")
        return DraftPipelineDetail(
            id=draft.id,
            name=draft.name,
            status=draft.status,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            structure=draft.structure,
            compilation_errors=draft.compilation_errors,
        )


@router.patch(
    "/drafts/{draft_id}",
    response_model=DraftPipelineDetail,
    responses={409: {"description": "Name conflict"}},
)
def update_draft_pipeline(
    draft_id: int,
    body: UpdateDraftPipelineRequest,
    request: Request,
) -> DraftPipelineDetail | JSONResponse:
    """Update name and/or structure of a DraftPipeline.

    Returns 409 with suggested_name on name collision.
    """
    engine = request.app.state.engine
    with Session(engine) as session:
        draft = session.get(DraftPipeline, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Draft pipeline not found")

        if body.name is not None:
            draft.name = body.name
        if body.structure is not None:
            draft.structure = body.structure

        draft.updated_at = utc_now()

        try:
            session.add(draft)
            session.commit()
            session.refresh(draft)
        except IntegrityError:
            session.rollback()
            # Find a free suffix for suggested name
            base = body.name or draft.name
            suggested = base
            for i in range(2, 10):
                candidate = f"{base}_{i}"
                existing = session.exec(
                    select(DraftPipeline).where(DraftPipeline.name == candidate)
                ).first()
                if existing is None:
                    suggested = candidate
                    break
            return JSONResponse(
                status_code=409,
                content={"detail": "name_conflict", "suggested_name": suggested},
            )

        return DraftPipelineDetail(
            id=draft.id,
            name=draft.name,
            status=draft.status,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            structure=draft.structure,
            compilation_errors=draft.compilation_errors,
        )


@router.delete("/drafts/{draft_id}", status_code=204)
def delete_draft_pipeline(draft_id: int, request: Request) -> None:
    """Delete a DraftPipeline by ID."""
    engine = request.app.state.engine
    with Session(engine) as session:
        draft = session.get(DraftPipeline, draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="Draft pipeline not found")
        session.delete(draft)
        session.commit()
