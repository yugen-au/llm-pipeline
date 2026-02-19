"""Pipeline run steps route module -- list and detail."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.state import PipelineRun, PipelineStepState
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
    result_data: dict
    context_snapshot: dict
    prompt_system_key: Optional[str] = None
    prompt_user_key: Optional[str] = None
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


# ---------------------------------------------------------------------------
# Endpoints (all sync def -- SQLite is sync, FastAPI wraps in threadpool)
# ---------------------------------------------------------------------------


@router.get("", response_model=StepListResponse)
def list_steps(run_id: str, db: DBSession) -> StepListResponse:
    """List steps for a pipeline run, ordered by step_number."""
    _get_run_or_404(db, run_id)

    stmt = (
        select(PipelineStepState)
        .where(PipelineStepState.run_id == run_id)
        .order_by(PipelineStepState.step_number)
    )
    steps = db.exec(stmt).all()

    return StepListResponse(
        items=[
            StepListItem(
                step_name=s.step_name,
                step_number=s.step_number,
                execution_time_ms=s.execution_time_ms,
                model=s.model,
                created_at=s.created_at,
            )
            for s in steps
        ],
    )


@router.get("/{step_number}", response_model=StepDetail)
def get_step(run_id: str, step_number: int, db: DBSession) -> StepDetail:
    """Full detail for a single step, looked up by run_id + step_number."""
    stmt = (
        select(PipelineStepState)
        .where(
            PipelineStepState.run_id == run_id,
            PipelineStepState.step_number == step_number,
        )
    )
    step = db.exec(stmt).first()
    if step is None:
        raise HTTPException(status_code=404, detail="Step not found")

    return StepDetail(
        step_name=step.step_name,
        step_number=step.step_number,
        pipeline_name=step.pipeline_name,
        run_id=step.run_id,
        input_hash=step.input_hash,
        result_data=step.result_data,
        context_snapshot=step.context_snapshot,
        prompt_system_key=step.prompt_system_key,
        prompt_user_key=step.prompt_user_key,
        prompt_version=step.prompt_version,
        model=step.model,
        execution_time_ms=step.execution_time_ms,
        created_at=step.created_at,
    )
