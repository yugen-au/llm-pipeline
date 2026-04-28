"""Review endpoints for human-in-the-loop review system."""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel
from sqlmodel import Session, select

from llm_pipeline.state import PipelineRun, PipelineReview
from llm_pipeline.ui.deps import DBSession
from llm_pipeline.ui.routes.websocket import manager as ws_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["reviews"])


class ReviewListItem(BaseModel):
    token: str
    run_id: str
    pipeline_name: str
    step_name: str
    step_number: int
    status: str
    decision: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class ReviewListResponse(BaseModel):
    items: List[ReviewListItem]
    total: int


class ReviewDetailResponse(BaseModel):
    token: str
    run_id: str
    pipeline_name: str
    step_name: str
    step_number: int
    status: str
    review_data: Optional[dict] = None
    decision: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None


class ReviewSubmitRequest(BaseModel):
    decision: str  # approved, minor_revision, major_revision, restart
    notes: Optional[str] = None
    resume_from: Optional[str] = None


class ReviewSubmitResponse(BaseModel):
    run_id: str
    decision: str
    status: str  # resumed, restarted


@router.get("", response_model=ReviewListResponse)
def list_reviews(
    db: DBSession,
    status: Optional[str] = Query(None, description="Filter by status: pending or completed"),
    pipeline_name: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> ReviewListResponse:
    """List reviews with optional filters."""
    stmt = select(PipelineReview).order_by(PipelineReview.created_at.desc())
    if status:
        stmt = stmt.where(PipelineReview.status == status)
    if pipeline_name:
        stmt = stmt.where(PipelineReview.pipeline_name == pipeline_name)

    from sqlalchemy import func
    count_stmt = select(func.count()).select_from(PipelineReview)
    if status:
        count_stmt = count_stmt.where(PipelineReview.status == status)
    if pipeline_name:
        count_stmt = count_stmt.where(PipelineReview.pipeline_name == pipeline_name)
    total = db.exec(count_stmt).one()

    reviews = db.exec(stmt.offset(offset).limit(limit)).all()
    return ReviewListResponse(
        items=[
            ReviewListItem(
                token=r.token,
                run_id=r.run_id,
                pipeline_name=r.pipeline_name,
                step_name=r.step_name,
                step_number=r.step_number,
                status=r.status,
                decision=r.decision,
                notes=r.notes,
                created_at=r.created_at.isoformat(),
                completed_at=r.completed_at.isoformat() if r.completed_at else None,
            )
            for r in reviews
        ],
        total=total,
    )


@router.get("/{token}", response_model=ReviewDetailResponse)
def get_review(token: str, db: DBSession) -> ReviewDetailResponse:
    """Fetch review data by token. Used by the review page."""
    review = db.exec(
        select(PipelineReview).where(PipelineReview.token == token)
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    return ReviewDetailResponse(
        token=review.token,
        run_id=review.run_id,
        pipeline_name=review.pipeline_name,
        step_name=review.step_name,
        step_number=review.step_number,
        status=review.status,
        review_data=review.review_data,
        decision=review.decision,
        notes=review.notes,
        created_at=review.created_at.isoformat(),
        completed_at=review.completed_at.isoformat() if review.completed_at else None,
    )


@router.post("/{token}", response_model=ReviewSubmitResponse)
def submit_review(
    token: str,
    body: ReviewSubmitRequest,
    background_tasks: BackgroundTasks,
    request: Request,
) -> ReviewSubmitResponse:
    """Submit a review decision. Token-keyed for webhook callbacks + UI."""
    from llm_pipeline.review import ReviewDecision

    engine = request.app.state.engine

    valid_decisions = {d.value for d in ReviewDecision}
    if body.decision not in valid_decisions:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid decision. Must be one of: {', '.join(valid_decisions)}",
        )

    with Session(engine) as session:
        review = session.exec(
            select(PipelineReview).where(PipelineReview.token == token)
        ).first()
        if not review:
            raise HTTPException(status_code=404, detail="Review not found")
        if review.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"Review is not pending (status: {review.status})",
            )

        run_id = review.run_id
        run = session.exec(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        ).first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        if run.status != "awaiting_review":
            raise HTTPException(
                status_code=409,
                detail=f"Run is not awaiting review (status: {run.status})",
            )

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

    # Notify connected WS clients of the review-completed transition.
    # State (PipelineReview row) is the source of truth; this is just a nudge.
    ws_manager.broadcast_to_run(run_id, {
        "type": "review_completed",
        "run_id": run_id,
        "pipeline_name": pipeline_name,
        "step_name": reviewed_step_name,
        "step_number": reviewed_step_number,
        "decision": body.decision,
        "notes": body.notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    if body.decision == "restart":
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
            pipeline = None
            try:
                pipeline = factory(run_id=new_run_id, engine=engine)
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
                ws_manager.signal_run_complete(new_run_id)

        background_tasks.add_task(run_restart)
        return ReviewSubmitResponse(run_id=new_run_id, decision=body.decision, status="restarted")

    registry = getattr(request.app.state, "pipeline_registry", {})
    factory = registry.get(pipeline_name)
    if factory is None:
        raise HTTPException(status_code=404, detail="Pipeline not found in registry")

    if body.decision == "approved":
        resume_index = reviewed_step_number
    elif body.decision == "minor_revision":
        resume_index = reviewed_step_number - 1
    else:  # major_revision
        resume_step_name = body.resume_from or reviewed_step_name
        resume_index = _resolve_step_index(request, pipeline_name, resume_step_name)

    def run_resume():
        pipeline = None
        try:
            pipeline = factory(run_id=run_id, engine=engine)
            pipeline.execute_from_step(
                resume_step_index=resume_index,
                review_notes=body.notes,
                review_decision=body.decision,
                input_data=original_input_data,
            )
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
            ws_manager.signal_run_complete(run_id)

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
