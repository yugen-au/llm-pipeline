"""Pipeline events route module."""
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.state import PipelineRun
from llm_pipeline.ui.deps import DBSession

router = APIRouter(prefix="/runs/{run_id}/events", tags=["events"])

# ---------------------------------------------------------------------------
# Response models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class EventItem(BaseModel):
    event_type: str
    pipeline_name: str
    run_id: str
    timestamp: datetime
    event_data: dict


class EventListResponse(BaseModel):
    items: List[EventItem]
    total: int
    offset: int
    limit: int


# ---------------------------------------------------------------------------
# Query params model
# ---------------------------------------------------------------------------


class EventListParams(BaseModel):
    event_type: Optional[str] = None
    step_name: Optional[str] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)


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


@router.get("", response_model=EventListResponse)
def list_events(
    run_id: str,
    params: Annotated[EventListParams, Depends()],
    db: DBSession,
) -> EventListResponse:
    """Paginated list of events for a pipeline run with optional event_type filter."""
    _get_run_or_404(db, run_id)

    # Count query
    count_stmt = (
        select(func.count())
        .select_from(PipelineEventRecord)
        .where(PipelineEventRecord.run_id == run_id)
    )
    if params.event_type is not None:
        count_stmt = count_stmt.where(
            PipelineEventRecord.event_type == params.event_type
        )
    if params.step_name is not None:
        count_stmt = count_stmt.where(
            PipelineEventRecord.step_name == params.step_name
        )
    total: int = db.scalar(count_stmt) or 0

    # Data query
    data_stmt = (
        select(PipelineEventRecord)
        .where(PipelineEventRecord.run_id == run_id)
    )
    if params.event_type is not None:
        data_stmt = data_stmt.where(
            PipelineEventRecord.event_type == params.event_type
        )
    if params.step_name is not None:
        data_stmt = data_stmt.where(
            PipelineEventRecord.step_name == params.step_name
        )
    data_stmt = (
        data_stmt
        .order_by(PipelineEventRecord.timestamp)
        .offset(params.offset)
        .limit(params.limit)
    )
    events = db.exec(data_stmt).all()

    return EventListResponse(
        items=[
            EventItem(
                event_type=e.event_type,
                pipeline_name=e.pipeline_name,
                run_id=e.run_id,
                timestamp=e.timestamp,
                event_data=e.event_data,
            )
            for e in events
        ],
        total=total,
        offset=params.offset,
        limit=params.limit,
    )
