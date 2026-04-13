"""Review endpoints for human-in-the-loop review system."""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from llm_pipeline.state import PipelineReview
from llm_pipeline.ui.deps import DBSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["reviews"])


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


@router.get("/{token}")
def get_review(token: str, db: DBSession) -> ReviewDetailResponse:
    """Fetch review data by token. Used by the review page."""
    review = db.exec(
        select(PipelineReview).where(PipelineReview.token == token)
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    if review.status == "completed":
        raise HTTPException(status_code=410, detail="Review already completed")

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
    )
