"""Review endpoints for human-in-the-loop review system."""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.state import PipelineReview
from llm_pipeline.ui.deps import DBSession

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

    # Count
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
