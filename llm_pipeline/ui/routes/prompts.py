"""Prompts route module -- list, detail, and CRUD endpoints."""
from datetime import datetime, timezone
from typing import Annotated, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.prompts.utils import (
    _increment_version,
    extract_variables_from_content,
)
from llm_pipeline.prompts.variables import (
    get_code_prompt_variables,
    rebuild_from_db,
)
from llm_pipeline.ui.deps import DBSession, WritableDBSession

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
    variable_definitions: Optional[Dict] = None
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
# Request models (CRUD)
# ---------------------------------------------------------------------------


class PromptCreateRequest(BaseModel):
    prompt_key: str
    prompt_name: str
    prompt_type: str  # "system" or "user"
    content: str
    category: Optional[str] = None
    step_name: Optional[str] = None
    description: Optional[str] = None
    version: str = "1.0"
    created_by: Optional[str] = None
    variable_definitions: Optional[Dict] = None


class PromptUpdateRequest(BaseModel):
    prompt_name: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    step_name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None
    created_by: Optional[str] = None
    variable_definitions: Optional[Dict] = None


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
        variable_definitions=prompt.variable_definitions,
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


# ---------------------------------------------------------------------------
# CRUD endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=PromptItem, status_code=201)
def create_prompt(
    body: PromptCreateRequest,
    db: WritableDBSession,
) -> PromptItem:
    """Create a new prompt."""
    required_variables = extract_variables_from_content(body.content)

    # Resolve variable_definitions: use provided or auto-generate from content
    var_defs = body.variable_definitions
    if var_defs is None and required_variables:
        var_defs = {
            v: {"type": "str", "description": ""}
            for v in required_variables
        }

    prompt = Prompt(
        prompt_key=body.prompt_key,
        prompt_name=body.prompt_name,
        prompt_type=body.prompt_type,
        content=body.content,
        category=body.category,
        step_name=body.step_name,
        description=body.description,
        version=body.version,
        created_by=body.created_by,
        required_variables=required_variables,
        variable_definitions=var_defs,
    )
    try:
        db.add(prompt)
        db.commit()
        db.refresh(prompt)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Prompt already exists")

    if prompt.variable_definitions:
        rebuild_from_db(prompt.prompt_key, prompt.prompt_type, prompt.variable_definitions)

    return _to_prompt_item(prompt)


@router.put("/{prompt_key}/{prompt_type}", response_model=PromptItem)
def update_prompt(
    prompt_key: str,
    prompt_type: str,
    body: PromptUpdateRequest,
    db: WritableDBSession,
) -> PromptItem:
    """Update an existing prompt."""
    stmt = select(Prompt).where(
        Prompt.prompt_key == prompt_key,
        Prompt.prompt_type == prompt_type,
    )
    prompt = db.exec(stmt).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    updates = body.model_dump(exclude_unset=True)

    # Track whether variable_definitions changed
    var_defs_changed = "variable_definitions" in updates

    for field, value in updates.items():
        setattr(prompt, field, value)

    # Re-extract variables if content changed
    if "content" in updates:
        prompt.required_variables = extract_variables_from_content(prompt.content)

        # Sync variable_definitions if not explicitly provided
        if not var_defs_changed:
            new_vars = set(prompt.required_variables or [])
            existing_defs = dict(prompt.variable_definitions or {})
            # Add new variables with defaults
            for v in new_vars:
                if v not in existing_defs:
                    existing_defs[v] = {"type": "str", "description": ""}
            # Remove variables no longer in content
            existing_defs = {k: v for k, v in existing_defs.items() if k in new_vars}
            prompt.variable_definitions = existing_defs or None
            var_defs_changed = True

    # Auto-increment version if not explicitly provided
    if "version" not in updates:
        prompt.version = _increment_version(prompt.version)

    prompt.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(prompt)

    if var_defs_changed and prompt.variable_definitions:
        rebuild_from_db(prompt.prompt_key, prompt.prompt_type, prompt.variable_definitions)

    return _to_prompt_item(prompt)


@router.delete("/{prompt_key}/{prompt_type}")
def delete_prompt(
    prompt_key: str,
    prompt_type: str,
    db: WritableDBSession,
) -> dict:
    """Soft-delete (deactivate) a prompt."""
    stmt = select(Prompt).where(
        Prompt.prompt_key == prompt_key,
        Prompt.prompt_type == prompt_type,
    )
    prompt = db.exec(stmt).first()
    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    prompt.is_active = False
    prompt.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"detail": "Prompt deactivated"}


@router.get("/{prompt_key}/{prompt_type}/variables")
def get_prompt_variable_schema(
    prompt_key: str, prompt_type: str, db: DBSession,
) -> dict:
    """Return merged variable schema from DB definitions and code class."""
    # 1. DB variable_definitions
    stmt = select(Prompt).where(
        Prompt.prompt_key == prompt_key,
        Prompt.prompt_type == prompt_type,
    )
    prompt = db.exec(stmt).first()
    db_defs: dict = (prompt.variable_definitions or {}) if prompt else {}

    # 2. Code-registered class
    code_cls = get_code_prompt_variables(prompt_key, prompt_type)
    code_fields: dict[str, dict] = {}
    if code_cls:
        for name, field_info in code_cls.model_fields.items():
            annotation = field_info.annotation
            type_name = getattr(annotation, '__name__', str(annotation))
            code_fields[name] = {
                "type": type_name,
                "description": field_info.description or "",
                "required": field_info.is_required(),
                "has_default": field_info.default is not None or field_info.default_factory is not None,
            }

    # 3. Merge: all unique field names
    all_names = set(db_defs.keys()) | set(code_fields.keys())
    fields = []
    for name in sorted(all_names):
        in_db = name in db_defs
        in_code = name in code_fields

        if in_db and in_code:
            source = "both"
        elif in_db:
            source = "db"
        else:
            source = "code"

        # Prefer DB values when available, fall back to code
        if in_db:
            f_type = db_defs[name].get("type", "str")
            f_desc = db_defs[name].get("description", "")
        else:
            f_type = code_fields[name]["type"]
            f_desc = code_fields[name]["description"]

        f_required = code_fields[name]["required"] if in_code else True
        f_has_default = code_fields[name]["has_default"] if in_code else False

        fields.append({
            "name": name,
            "type": f_type,
            "description": f_desc,
            "required": f_required,
            "has_default": f_has_default,
            "source": source,
        })

    return {
        "fields": fields,
        "has_code_class": code_cls is not None,
        "code_class_name": code_cls.__name__ if code_cls else None,
    }
