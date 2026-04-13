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
from llm_pipeline.state import PipelineRun, PipelineStepState, PipelineReview
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
    error_message: Optional[str] = None


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
    error_message: Optional[str] = None
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

    # Guard: pipeline must be published
    from sqlmodel import select as sql_select
    from llm_pipeline.db.pipeline_visibility import PipelineVisibility
    with Session(request.app.state.engine) as vis_session:
        vis = vis_session.exec(
            sql_select(PipelineVisibility).where(
                PipelineVisibility.pipeline_name == body.pipeline_name,
            )
        ).first()
    if not vis or vis.status != "published":
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline '{body.pipeline_name}' is not published",
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
        pipeline = None
        try:
            pipeline = factory(run_id=run_id, engine=engine, event_emitter=emitter, input_data=body.input_data or {})
            pipeline.execute(data=None, input_data=body.input_data)
            # Only save extractions if pipeline completed (not paused for review)
            if not getattr(pipeline, '_awaiting_review', False):
                pipeline.save()
        except Exception as exc:
            logger.exception("Background pipeline execution failed for run_id=%s", run_id)
            error_msg = f"{type(exc).__name__}: {exc}"
            # Release pipeline session lock BEFORE opening err_session.
            # pipeline._real_session holds an open transaction with a row
            # lock on pipeline_runs.  If we open err_session and try to
            # UPDATE the same row while that lock is held, PostgreSQL will
            # block indefinitely (single-threaded deadlock).
            if pipeline is not None:
                try:
                    pipeline.close()
                except Exception:
                    pass
            try:
                with Session(engine) as err_session:
                    run = err_session.exec(
                        select(PipelineRun).where(PipelineRun.run_id == run_id)
                    ).first()
                    if run:
                        run.status = "failed"
                        run.completed_at = datetime.now(timezone.utc)
                        run.error_message = error_msg[:2000]
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
# Review submission
# ---------------------------------------------------------------------------


class ReviewSubmitRequest(BaseModel):
    decision: str  # approved, minor_revision, major_revision, restart
    notes: Optional[str] = None
    resume_from: Optional[str] = None


class ReviewSubmitResponse(BaseModel):
    run_id: str
    decision: str
    status: str  # resumed, restarted


@router.post("/{run_id}/review", response_model=ReviewSubmitResponse)
def submit_review(
    run_id: str,
    body: ReviewSubmitRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> ReviewSubmitResponse:
    """Submit a review decision for a paused pipeline run."""
    from llm_pipeline.review import ReviewDecision
    from llm_pipeline.events.types import ReviewCompleted

    engine = request.app.state.engine

    # Validate decision
    valid_decisions = {d.value for d in ReviewDecision}
    if body.decision not in valid_decisions:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid decision. Must be one of: {', '.join(valid_decisions)}",
        )

    # Validate run exists and is awaiting review
    with Session(engine) as session:
        run = session.exec(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        ).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.status != "awaiting_review":
            raise HTTPException(
                status_code=409, detail=f"Run is not awaiting review (status: {run.status})"
            )

        # Find pending review
        review = session.exec(
            select(PipelineReview).where(
                PipelineReview.run_id == run_id,
                PipelineReview.status == "pending",
            )
        ).first()
        if not review:
            raise HTTPException(status_code=404, detail="No pending review found")

        # Update review record
        review.status = "completed"
        review.decision = body.decision
        review.notes = body.notes
        review.resume_from = body.resume_from
        review.completed_at = datetime.now(timezone.utc)
        session.add(review)

        reviewed_step_number = review.step_number
        reviewed_step_name = review.step_name
        pipeline_name = review.pipeline_name
        original_input_data = review.input_data

        if body.decision == "restart":
            run.status = "restarted"
            run.completed_at = datetime.now(timezone.utc)
            session.add(run)
        else:
            run.status = "running"
            session.add(run)

        session.commit()

    # Determine resume behavior
    if body.decision == "restart":
        # New run — trigger fresh execution
        new_run_id = str(uuid.uuid4())
        registry = getattr(request.app.state, "pipeline_registry", {})
        factory = registry.get(pipeline_name)
        if factory is None:
            raise HTTPException(status_code=404, detail="Pipeline not found in registry")

        with Session(engine) as pre_session:
            pre_session.add(PipelineRun(
                run_id=new_run_id,
                pipeline_name=pipeline_name,
                status="running",
                started_at=datetime.now(timezone.utc),
            ))
            pre_session.commit()

        def run_restart():
            bridge = UIBridge(run_id=new_run_id)
            db_buffer = BufferedEventHandler(engine)
            emitter = CompositeEmitter([bridge, db_buffer])
            pipeline = None
            try:
                pipeline = factory(run_id=new_run_id, engine=engine, event_emitter=emitter)
                pipeline.execute(data=None)
                pipeline.save()
            except Exception:
                logger.exception("Restart pipeline failed for run_id=%s", new_run_id)
                if pipeline is not None:
                    try:
                        pipeline.close()
                    except Exception:
                        pass
                try:
                    with Session(engine) as err_session:
                        r = err_session.exec(
                            select(PipelineRun).where(PipelineRun.run_id == new_run_id)
                        ).first()
                        if r:
                            r.status = "failed"
                            r.completed_at = datetime.now(timezone.utc)
                            err_session.add(r)
                            err_session.commit()
                except Exception:
                    pass
            finally:
                bridge.complete()
                try:
                    db_buffer.flush()
                except Exception:
                    pass

        background_tasks.add_task(run_restart)
        return ReviewSubmitResponse(run_id=new_run_id, decision=body.decision, status="restarted")

    # Resume: approved, minor_revision, or major_revision
    registry = getattr(request.app.state, "pipeline_registry", {})
    factory = registry.get(pipeline_name)
    if factory is None:
        raise HTTPException(status_code=404, detail="Pipeline not found in registry")

    if body.decision == "approved":
        resume_index = reviewed_step_number  # step N completed, resume from N+1 (0-based: step_number)
    elif body.decision == "minor_revision":
        resume_index = reviewed_step_number - 1  # re-run same step (0-based)
    else:  # major_revision
        # Find step index by name
        resume_step_name = body.resume_from or review.step_name
        resume_index = _resolve_step_index(request, pipeline_name, resume_step_name)

    def run_resume():
        bridge = UIBridge(run_id=run_id)
        db_buffer = BufferedEventHandler(engine)
        emitter = CompositeEmitter([bridge, db_buffer])
        pipeline = None
        try:
            pipeline = factory(run_id=run_id, engine=engine, event_emitter=emitter)
            pipeline.execute_from_step(
                resume_step_index=resume_index,
                review_notes=body.notes,
                input_data=original_input_data,
            )
            # Check if paused again for another review
            with Session(engine) as check_session:
                run_row = check_session.exec(
                    select(PipelineRun).where(PipelineRun.run_id == run_id)
                ).first()
            if run_row and run_row.status != "awaiting_review":
                pipeline.save()
        except Exception:
            logger.exception("Resume pipeline failed for run_id=%s", run_id)
            if pipeline is not None:
                try:
                    pipeline.close()
                except Exception:
                    pass
            try:
                with Session(engine) as err_session:
                    r = err_session.exec(
                        select(PipelineRun).where(PipelineRun.run_id == run_id)
                    ).first()
                    if r:
                        r.status = "failed"
                        r.completed_at = datetime.now(timezone.utc)
                        err_session.add(r)
                        err_session.commit()
            except Exception:
                pass
        finally:
            bridge.complete()
            try:
                db_buffer.flush()
            except Exception:
                pass

    background_tasks.add_task(run_resume)
    return ReviewSubmitResponse(run_id=run_id, decision=body.decision, status="resumed")


def _resolve_step_index(request: Request, pipeline_name: str, step_name: str) -> int:
    """Find the 0-based step index for a step name within a pipeline."""
    from llm_pipeline.introspection import PipelineIntrospector
    registry = getattr(request.app.state, "introspection_registry", {})
    pipeline_cls = registry.get(pipeline_name)
    if not pipeline_cls:
        return 0
    metadata = PipelineIntrospector(pipeline_cls).get_metadata()
    for strategy in metadata.get("strategies", []):
        for i, step in enumerate(strategy.get("steps", [])):
            if step.get("step_name") == step_name:
                return i
    return 0


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
