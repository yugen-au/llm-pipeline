"""Pipeline run steps route — list and detail backed by ``PipelineNodeSnapshot``.

The legacy ``PipelineStepState`` table was retired in the
pydantic-graph migration; everything the UI needs is now derivable
from the snapshot rows that pydantic-graph writes via
``SqlmodelStatePersistence``.

The route preserves the old ``StepListItem`` / ``StepDetail`` response
shape so the frontend doesn't need to change in lockstep.
"""
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.naming import to_snake_case
from llm_pipeline.state import PipelineNodeSnapshot, PipelineRun
from llm_pipeline.ui.deps import DBSession

router = APIRouter(prefix="/runs/{run_id}/steps", tags=["steps"])


# ---------------------------------------------------------------------------
# Response models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class StepListItem(BaseModel):
    step_name: str
    step_number: int
    execution_time_ms: Optional[int] = None
    model: Optional[str] = None
    created_at: datetime


class StepListResponse(BaseModel):
    items: List[StepListItem]


class StepDetail(BaseModel):
    step_name: str
    step_number: int
    pipeline_name: str
    run_id: str
    input_hash: str
    result_data: Any
    context_snapshot: dict
    prompt_name: Optional[str] = None
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_run_or_404(db: DBSession, run_id: str) -> PipelineRun:
    """Return run or raise 404."""
    stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
    run = db.exec(stmt).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


def _step_name_from_class(class_name: str) -> str:
    """Snake-case the node class name, stripping the kind suffix."""
    if class_name.endswith("Step"):
        return to_snake_case(class_name, strip_suffix="Step")
    if class_name.endswith("Extraction"):
        return to_snake_case(class_name, strip_suffix="Extraction")
    if class_name.endswith("Review"):
        return to_snake_case(class_name, strip_suffix="Review")
    return to_snake_case(class_name)


def _duration_ms(duration: float | None) -> int | None:
    """Convert pydantic-graph's float-seconds duration to ms (rounded)."""
    if duration is None:
        return None
    return int(round(duration * 1000.0))


def _step_output(snap: PipelineNodeSnapshot) -> Any:
    """Reach into the snapshot's state and return this node's output, if any."""
    state = snap.state_snapshot or {}
    outputs = state.get("outputs", {}) or {}
    items = outputs.get(snap.node_class_name)
    if items is None:
        # Snapshot was taken BEFORE the node ran (state hadn't recorded
        # output yet). Try the next snapshot's state via the row order
        # — for the steps route we can return None and the frontend
        # treats it as 'no output yet'.
        return None
    return items[0] if isinstance(items, list) and len(items) == 1 else items


def _prompt_name(class_name: str) -> Optional[str]:
    """Phoenix prompt name for a step class, derived from its snake-case name."""
    if not class_name.endswith("Step"):
        return None
    return to_snake_case(class_name, strip_suffix="Step")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=StepListResponse)
def list_steps(run_id: str, db: DBSession) -> StepListResponse:
    """List node executions for a pipeline run, ordered by sequence."""
    _get_run_or_404(db, run_id)

    snaps = db.exec(
        select(PipelineNodeSnapshot)
        .where(
            PipelineNodeSnapshot.run_id == run_id,
            PipelineNodeSnapshot.kind == "node",
        )
        .order_by(PipelineNodeSnapshot.sequence)
    ).all()

    return StepListResponse(
        items=[
            StepListItem(
                step_name=_step_name_from_class(s.node_class_name),
                step_number=s.sequence + 1,
                execution_time_ms=_duration_ms(s.duration),
                model=(s.state_snapshot or {})
                    .get("metadata", {}).get("__step_model__"),
                created_at=s.created_at,
            )
            for s in snaps
        ],
    )


@router.get("/{step_number}", response_model=StepDetail)
def get_step(run_id: str, step_number: int, db: DBSession) -> StepDetail:
    """Full detail for a single node execution.

    ``step_number`` is the 1-based ``sequence + 1`` from the list
    endpoint. ``input_hash``, ``prompt_system_key`` /
    ``prompt_user_key`` / ``prompt_version`` are derived where
    possible (the framework no longer writes them as columns).
    """
    run = _get_run_or_404(db, run_id)

    snap = db.exec(
        select(PipelineNodeSnapshot)
        .where(
            PipelineNodeSnapshot.run_id == run_id,
            PipelineNodeSnapshot.kind == "node",
            PipelineNodeSnapshot.sequence == step_number - 1,
        )
    ).first()
    if snap is None:
        raise HTTPException(status_code=404, detail="Step not found")

    metadata = (snap.state_snapshot or {}).get("metadata", {}) or {}

    return StepDetail(
        step_name=_step_name_from_class(snap.node_class_name),
        step_number=snap.sequence + 1,
        pipeline_name=run.pipeline_name,
        run_id=run_id,
        input_hash="",  # No longer stored — caching dropped in pydantic-graph migration.
        result_data=_step_output(snap),
        context_snapshot=metadata,
        prompt_name=_prompt_name(snap.node_class_name),
        prompt_version=None,
        model=metadata.get("__step_model__"),
        execution_time_ms=_duration_ms(snap.duration),
        created_at=snap.created_at,
    )
