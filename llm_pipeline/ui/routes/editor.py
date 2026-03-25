"""Editor route module -- compile, available steps, DraftPipeline CRUD."""
import logging
from datetime import datetime
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.state import DraftPipeline, DraftStep, utc_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/editor", tags=["editor"])

# ---------------------------------------------------------------------------
# Request / response models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class EditorStep(BaseModel):
    step_ref: str = Field(max_length=200)
    source: Literal["draft", "registered"]
    position: int = Field(ge=0)


class EditorStrategy(BaseModel):
    strategy_name: str = Field(max_length=200)
    steps: list[EditorStep] = Field(max_length=500)


class CompileRequest(BaseModel):
    strategies: list[EditorStrategy] = Field(max_length=100)
    draft_id: int | None = None


class CompileError(BaseModel):
    strategy_name: str
    step_ref: str
    message: str
    field: str | None = None
    severity: Literal["error", "warning"] = "error"


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


def _collect_registered_prompt_keys(
    introspection_registry: dict,
) -> dict[str, set[str]]:
    """Build step_name -> {prompt_keys} from introspection registry.

    For each registered step, collects system_key and user_key values
    from introspection metadata across all pipelines. Skips pipelines
    that fail introspection.
    """
    step_keys: dict[str, set[str]] = {}
    for pipeline_name, pipeline_cls in introspection_registry.items():
        try:
            metadata = PipelineIntrospector(pipeline_cls).get_metadata()
        except Exception:
            continue
        for strategy in metadata.get("strategies", []):
            for step in strategy.get("steps", []):
                sn = step.get("step_name")
                if not sn:
                    continue
                for key_field in ("system_key", "user_key"):
                    val = step.get(key_field)
                    if val:
                        step_keys.setdefault(sn, set()).add(val)
    return step_keys


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

    # --- Pass 1: step-ref existence ---
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

    # --- Pass 2: duplicate step_ref within each strategy ---
    for strategy in body.strategies:
        seen_refs: dict[str, int] = {}
        for step in strategy.steps:
            seen_refs[step.step_ref] = seen_refs.get(step.step_ref, 0) + 1
        for ref, count in seen_refs.items():
            if count > 1:
                errors.append(
                    CompileError(
                        strategy_name=strategy.strategy_name,
                        step_ref=ref,
                        message=f"Duplicate step_ref '{ref}' appears {count} times in strategy '{strategy.strategy_name}'",
                        field="step_ref",
                        severity="error",
                    )
                )

    # --- Pass 3: empty strategies (zero steps) ---
    for strategy in body.strategies:
        if len(strategy.steps) == 0:
            errors.append(
                CompileError(
                    strategy_name=strategy.strategy_name,
                    step_ref="",
                    message=f"Strategy '{strategy.strategy_name}' has no steps",
                    field="steps",
                    severity="error",
                )
            )

    # --- Pass 4: position gaps or duplicates within each strategy ---
    for strategy in body.strategies:
        if not strategy.steps:
            continue
        positions = [s.position for s in strategy.steps]
        pos_counts: dict[int, int] = {}
        for p in positions:
            pos_counts[p] = pos_counts.get(p, 0) + 1
        dup_positions = [p for p, c in pos_counts.items() if c > 1]
        if dup_positions:
            errors.append(
                CompileError(
                    strategy_name=strategy.strategy_name,
                    step_ref="",
                    message=f"Duplicate positions {sorted(dup_positions)} in strategy '{strategy.strategy_name}'",
                    field="position",
                    severity="error",
                )
            )
        expected = list(range(len(strategy.steps)))
        actual = sorted(positions)
        if actual != expected and not dup_positions:
            errors.append(
                CompileError(
                    strategy_name=strategy.strategy_name,
                    step_ref="",
                    message=f"Position gap in strategy '{strategy.strategy_name}': expected {expected}, got {actual}",
                    field="position",
                    severity="error",
                )
            )

    # --- Pass 5: prompt key existence for registered steps ---
    step_prompt_keys = _collect_registered_prompt_keys(introspection_registry)
    # Collect all expected keys across registered steps referenced in the request
    all_expected_keys: set[str] = set()
    for strategy in body.strategies:
        for step in strategy.steps:
            if step.source == "registered" and step.step_ref in step_prompt_keys:
                all_expected_keys.update(step_prompt_keys[step.step_ref])

    if all_expected_keys:
        with Session(engine) as session:
            stmt = select(Prompt.prompt_key).where(
                Prompt.prompt_key.in_(list(all_expected_keys)),
                Prompt.is_active.is_(True),
            )
            found_keys = set(session.exec(stmt).all())

        for strategy in body.strategies:
            for step in strategy.steps:
                if step.source != "registered":
                    continue
                expected_keys = step_prompt_keys.get(step.step_ref, set())
                for key in expected_keys:
                    if key not in found_keys:
                        errors.append(
                            CompileError(
                                strategy_name=strategy.strategy_name,
                                step_ref=step.step_ref,
                                message=f"Prompt key '{key}' not found in prompts table",
                                field="prompt_key",
                                severity="warning",
                            )
                        )

    has_errors = any(e.severity == "error" for e in errors)

    # --- Stateful write path: persist compilation results to DraftPipeline ---
    if body.draft_id is not None:
        with Session(engine) as session:
            draft = session.get(DraftPipeline, body.draft_id)
            if draft is None:
                raise HTTPException(
                    status_code=404, detail="Draft pipeline not found"
                )
            draft.compilation_errors = {
                "errors": [e.model_dump() for e in errors]
            }
            draft.status = "error" if has_errors else "draft"
            draft.updated_at = utc_now()
            session.add(draft)
            session.commit()

    return CompileResponse(valid=not has_errors, errors=errors)


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
