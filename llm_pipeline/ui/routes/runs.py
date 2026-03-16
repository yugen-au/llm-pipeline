"""Pipeline runs route module -- list, detail, trigger."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from llm_pipeline.events.emitter import CompositeEmitter
from llm_pipeline.events.handlers import BufferedEventHandler
from llm_pipeline.state import PipelineRun, PipelineStepState
from llm_pipeline.ui.bridge import UIBridge
from llm_pipeline.ui.deps import DBSession
from llm_pipeline.ui.routes.websocket import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/runs", tags=["runs"])

# ---------------------------------------------------------------------------
# Response / request models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class RunListItem(BaseModel):
    run_id: str
    pipeline_name: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    step_count: Optional[int] = None
    total_time_ms: Optional[int] = None


class RunListResponse(BaseModel):
    items: List[RunListItem]
    total: int
    offset: int
    limit: int


class StepSummary(BaseModel):
    step_name: str
    step_number: int
    execution_time_ms: Optional[int] = None
    created_at: datetime


class RunDetail(BaseModel):
    run_id: str
    pipeline_name: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    step_count: Optional[int] = None
    total_time_ms: Optional[int] = None
    steps: List[StepSummary]


class TriggerRunRequest(BaseModel):
    pipeline_name: str
    input_data: Optional[Dict[str, Any]] = None


class TriggerRunResponse(BaseModel):
    run_id: str
    status: str


# ---------------------------------------------------------------------------
# Query params model
# ---------------------------------------------------------------------------


class RunListParams(BaseModel):
    pipeline_name: Optional[str] = None
    status: Optional[str] = None
    started_after: Optional[datetime] = None
    started_before: Optional[datetime] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=50, ge=1, le=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_filters(stmt, params: RunListParams):
    """Append .where() clauses for non-None filter params."""
    if params.pipeline_name is not None:
        stmt = stmt.where(PipelineRun.pipeline_name == params.pipeline_name)
    if params.status is not None:
        stmt = stmt.where(PipelineRun.status == params.status)
    if params.started_after is not None:
        stmt = stmt.where(PipelineRun.started_at >= params.started_after)
    if params.started_before is not None:
        stmt = stmt.where(PipelineRun.started_at <= params.started_before)
    return stmt


# ---------------------------------------------------------------------------
# Endpoints (all sync def -- SQLite is sync, FastAPI wraps in threadpool)
# ---------------------------------------------------------------------------


@router.get("", response_model=RunListResponse)
def list_runs(
    params: Annotated[RunListParams, Depends()],
    db: DBSession,
) -> RunListResponse:
    """Paginated list of pipeline runs with optional filters."""
    # Count query
    count_stmt = select(func.count()).select_from(PipelineRun)
    count_stmt = _apply_filters(count_stmt, params)
    total: int = db.scalar(count_stmt) or 0

    # Data query
    data_stmt = select(PipelineRun)
    data_stmt = _apply_filters(data_stmt, params)
    data_stmt = (
        data_stmt
        .order_by(PipelineRun.started_at.desc())
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = db.exec(data_stmt).all()

    return RunListResponse(
        items=[
            RunListItem(
                run_id=r.run_id,
                pipeline_name=r.pipeline_name,
                status=r.status,
                started_at=r.started_at,
                completed_at=r.completed_at,
                step_count=r.step_count,
                total_time_ms=r.total_time_ms,
            )
            for r in rows
        ],
        total=total,
        offset=params.offset,
        limit=params.limit,
    )


@router.get("/{run_id}", response_model=RunDetail)
def get_run(run_id: str, db: DBSession) -> RunDetail:
    """Single run detail with step summaries."""
    stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
    run = db.exec(stmt).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    steps_stmt = (
        select(PipelineStepState)
        .where(PipelineStepState.run_id == run_id)
        .order_by(PipelineStepState.step_number)
    )
    steps = db.exec(steps_stmt).all()

    return RunDetail(
        run_id=run.run_id,
        pipeline_name=run.pipeline_name,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        step_count=run.step_count,
        total_time_ms=run.total_time_ms,
        steps=[
            StepSummary(
                step_name=s.step_name,
                step_number=s.step_number,
                execution_time_ms=s.execution_time_ms,
                created_at=s.created_at,
            )
            for s in steps
        ],
    )


@router.post("", response_model=TriggerRunResponse, status_code=202)
def trigger_run(
    body: TriggerRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> TriggerRunResponse:
    """Trigger a pipeline run in the background.

    The pipeline_registry on app.state maps pipeline names to factory
    callables with signature
    ``(run_id: str, engine: Engine, event_emitter: PipelineEventEmitter | None = None) -> pipeline``
    where the returned object exposes ``.execute()`` and ``.save()``.

    A :class:`~llm_pipeline.ui.bridge.UIBridge` is constructed per run and
    passed as ``event_emitter`` so pipeline events are forwarded to
    WebSocket clients in real time.
    """
    registry: dict = getattr(request.app.state, "pipeline_registry", {})
    factory = registry.get(body.pipeline_name)
    if factory is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline '{body.pipeline_name}' not found in registry",
        )

    # Guard: model must be configured before pipeline execution
    default_model = getattr(request.app.state, "default_model", None)
    if default_model is None:
        raise HTTPException(
            status_code=422,
            detail="No model configured. Set LLM_PIPELINE_MODEL env var or pass --model flag.",
        )

    run_id = str(uuid.uuid4())
    engine = request.app.state.engine

    # Create PipelineRun record before background task so frontend
    # can poll /steps and /events without 404 race condition.
    with Session(engine) as pre_session:
        pre_session.add(PipelineRun(
            run_id=run_id,
            pipeline_name=body.pipeline_name,
            status="running",
        ))
        pre_session.commit()

    # Notify global WS subscribers before background task starts
    ws_manager.broadcast_global({
        "type": "run_created",
        "run_id": run_id,
        "pipeline_name": body.pipeline_name,
        "started_at": datetime.now(timezone.utc).isoformat(),
    })

    def run_pipeline() -> None:
        bridge = UIBridge(run_id=run_id)
        db_buffer = BufferedEventHandler(engine)
        emitter = CompositeEmitter([bridge, db_buffer])
        try:
            pipeline = factory(run_id=run_id, engine=engine, event_emitter=emitter, input_data=body.input_data or {})
            pipeline.execute(data=None, input_data=body.input_data)
            pipeline.save()
        except Exception:
            logger.exception("Background pipeline execution failed for run_id=%s", run_id)
            try:
                with Session(engine) as err_session:
                    run = err_session.exec(
                        select(PipelineRun).where(PipelineRun.run_id == run_id)
                    ).first()
                    if run:
                        run.status = "failed"
                        run.completed_at = datetime.now(timezone.utc)
                        err_session.add(run)
                        err_session.commit()
            except Exception:
                logger.exception(
                    "Failed to update PipelineRun status for run_id=%s", run_id
                )
        finally:
            bridge.complete()
            try:
                count = db_buffer.flush()
                logger.info("Flushed %d events to DB for run_id=%s", count, run_id)
            except Exception:
                logger.exception("Failed to flush events to DB for run_id=%s", run_id)

    background_tasks.add_task(run_pipeline)

    return TriggerRunResponse(run_id=run_id, status="accepted")


# ---------------------------------------------------------------------------
# Context evolution models + endpoint
# ---------------------------------------------------------------------------


class ContextSnapshot(BaseModel):
    step_name: str
    step_number: int
    context_snapshot: dict


class ContextEvolutionResponse(BaseModel):
    run_id: str
    snapshots: List[ContextSnapshot]


@router.get("/{run_id}/context", response_model=ContextEvolutionResponse)
def get_context_evolution(run_id: str, db: DBSession) -> ContextEvolutionResponse:
    """Context snapshot at each step, ordered by step number."""
    stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
    run = db.exec(stmt).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    steps_stmt = (
        select(PipelineStepState)
        .where(PipelineStepState.run_id == run_id)
        .order_by(PipelineStepState.step_number)
    )
    steps = db.exec(steps_stmt).all()

    return ContextEvolutionResponse(
        run_id=run_id,
        snapshots=[
            ContextSnapshot(
                step_name=s.step_name,
                step_number=s.step_number,
                context_snapshot=s.context_snapshot,
            )
            for s in steps
        ],
    )
