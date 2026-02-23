"""Prompts route module -- list and detail endpoints."""
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.prompts.loader import extract_variables_from_content
from llm_pipeline.ui.deps import DBSession

router = APIRouter(prefix="/prompts", tags=["prompts"])

# ---------------------------------------------------------------------------
# Response models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------


class PromptItem(BaseModel):
    id: int
    prompt_key: str
    prompt_name: str
    prompt_type: str
    category: Optional[str]
    step_name: Optional[str]
    content: str
    required_variables: Optional[List[str]]
    description: Optional[str]
    version: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str]


class PromptListResponse(BaseModel):
    items: List[PromptItem]
    total: int
    offset: int
    limit: int


# PromptVariant has identical fields to PromptItem (system or user variant in grouped detail)
PromptVariant = PromptItem


class PromptDetailResponse(BaseModel):
    prompt_key: str
    variants: List[PromptVariant]


# ---------------------------------------------------------------------------
# Query params model
# ---------------------------------------------------------------------------


class PromptListParams(BaseModel):
    category: Optional[str] = None
    step_name: Optional[str] = None
    prompt_type: Optional[str] = None
    is_active: Optional[bool] = True
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=50, ge=1, le=200)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_variables(prompt: Prompt) -> Optional[List[str]]:
    """Return stored required_variables when non-null, else extract from content."""
    if prompt.required_variables is not None:
        return prompt.required_variables
    return extract_variables_from_content(prompt.content)


def _to_prompt_item(prompt: Prompt) -> PromptItem:
    """Map a Prompt DB row to a PromptItem response model."""
    return PromptItem(
        id=prompt.id,
        prompt_key=prompt.prompt_key,
        prompt_name=prompt.prompt_name,
        prompt_type=prompt.prompt_type,
        category=prompt.category,
        step_name=prompt.step_name,
        content=prompt.content,
        required_variables=_resolve_variables(prompt),
        description=prompt.description,
        version=prompt.version,
        is_active=prompt.is_active,
        created_at=prompt.created_at,
        updated_at=prompt.updated_at,
        created_by=prompt.created_by,
    )


def _apply_filters(stmt, params: PromptListParams):
    """Append .where() clauses for non-None filter params."""
    if params.category is not None:
        stmt = stmt.where(Prompt.category == params.category)
    if params.step_name is not None:
        stmt = stmt.where(Prompt.step_name == params.step_name)
    if params.prompt_type is not None:
        stmt = stmt.where(Prompt.prompt_type == params.prompt_type)
    if params.is_active is not None:
        stmt = stmt.where(Prompt.is_active == params.is_active)
    return stmt


# ---------------------------------------------------------------------------
# Endpoints (all sync def -- SQLite is sync, FastAPI wraps in threadpool)
# ---------------------------------------------------------------------------


@router.get("", response_model=PromptListResponse)
def list_prompts(
    params: Annotated[PromptListParams, Depends()],
    db: DBSession,
) -> PromptListResponse:
    """Paginated list of prompts with optional filters."""
    # Count query
    count_stmt = select(func.count()).select_from(Prompt)
    count_stmt = _apply_filters(count_stmt, params)
    total: int = db.scalar(count_stmt) or 0

    # Data query
    data_stmt = select(Prompt)
    data_stmt = _apply_filters(data_stmt, params)
    data_stmt = (
        data_stmt
        .order_by(Prompt.prompt_key, Prompt.prompt_type)
        .offset(params.offset)
        .limit(params.limit)
    )
    rows = db.exec(data_stmt).all()

    return PromptListResponse(
        items=[_to_prompt_item(r) for r in rows],
        total=total,
        offset=params.offset,
        limit=params.limit,
    )


@router.get("/{prompt_key}", response_model=PromptDetailResponse)
def get_prompt(prompt_key: str, db: DBSession) -> PromptDetailResponse:
    """Grouped detail for a prompt key showing all variants (system/user).

    Returns all variants regardless of is_active status. The list endpoint
    handles active filtering for browsing; the detail endpoint shows
    everything for a given key.
    """
    stmt = (
        select(Prompt)
        .where(Prompt.prompt_key == prompt_key)
        .order_by(Prompt.prompt_type)
    )
    rows = db.exec(stmt).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Prompt not found")

    return PromptDetailResponse(
        prompt_key=prompt_key,
        variants=[_to_prompt_item(r) for r in rows],
    )
