# Step 3: API Route Conventions Research

## Source Files Analyzed
- `llm_pipeline/ui/app.py` - app factory, router mounting
- `llm_pipeline/ui/deps.py` - DB session dependency injection
- `llm_pipeline/ui/routes/runs.py` - fully implemented, paginated list + detail + trigger
- `llm_pipeline/ui/routes/steps.py` - fully implemented, nested under runs
- `llm_pipeline/ui/routes/events.py` - fully implemented, nested under runs, paginated
- `llm_pipeline/ui/routes/prompts.py` - empty stub (our target)
- `llm_pipeline/ui/routes/pipelines.py` - empty stub
- `llm_pipeline/ui/routes/websocket.py` - async WebSocket, separate pattern
- `llm_pipeline/ui/__init__.py` - import guard
- `llm_pipeline/session/readonly.py` - ReadOnlySession wrapper
- `llm_pipeline/db/prompt.py` - Prompt SQLModel
- `llm_pipeline/prompts/loader.py` - extract_variables_from_content()
- `tests/ui/conftest.py` - test fixtures, _make_app()
- `tests/ui/test_integration.py` - integration test patterns
- `tests/test_ui.py` - unit tests for stubs/factory

## 1. Router Creation & Mounting

### Router instantiation pattern
```python
router = APIRouter(prefix="/resource_plural", tags=["resource_plural"])
```
- Prefix: lowercase, plural noun matching resource
- Tags: list with single string matching prefix (no slash)

### Mounting in app.py
```python
app.include_router(some_router, prefix="/api")
```
- All HTTP routers mounted with `prefix="/api"`
- Final URL: `/api/{router_prefix}/{path}`
- WebSocket router is the ONLY exception: mounted without `/api` prefix

### Existing router prefixes
| Router | Prefix | Final base URL |
|--------|--------|---------------|
| runs | `/runs` | `/api/runs` |
| steps | `/runs/{run_id}/steps` | `/api/runs/{run_id}/steps` |
| events | `/runs/{run_id}/events` | `/api/runs/{run_id}/events` |
| prompts | `/prompts` | `/api/prompts` |
| pipelines | `/pipelines` | `/api/pipelines` |
| websocket | (none) | `/ws/runs/{run_id}` |

### Prompts router already registered
The stub `router = APIRouter(prefix="/prompts", tags=["prompts"])` exists and is already mounted in `app.py` line 78: `app.include_router(prompts_router, prefix="/api")`. No app.py changes needed.

## 2. File Structure Convention

Every route file follows this exact structure (comment banners included):

```
"""Docstring describing module."""
<imports>

router = APIRouter(prefix="...", tags=["..."])

# ---------------------------------------------------------------------------
# Response / request models (plain Pydantic, NOT SQLModel)
# ---------------------------------------------------------------------------

class ...

# ---------------------------------------------------------------------------
# Query params model
# ---------------------------------------------------------------------------

class ...Params(BaseModel):
    ...

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _helper(...):
    ...

# ---------------------------------------------------------------------------
# Endpoints (all sync def -- SQLite is sync, FastAPI wraps in threadpool)
# ---------------------------------------------------------------------------

@router.get(...)
def list_...:
    ...

@router.get("/{id}")
def get_...:
    ...
```

## 3. Import Conventions

### Standard imports across route files
```python
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func          # only when using count()
from sqlmodel import select

from llm_pipeline.<model_module> import <Model>
from llm_pipeline.ui.deps import DBSession
```

### Key notes
- `from __future__ import annotations` is NOT used in route files (only in app.py and bridge.py)
- Response models use `from pydantic import BaseModel` (NOT SQLModel)
- DB queries use `from sqlmodel import select`
- `func.count()` uses `from sqlalchemy import func`
- No logging imported in read-only route files (only in runs.py which has trigger logic)

## 4. Response Model Conventions

### Rule: Plain Pydantic BaseModel, never SQLModel
Every route file includes the comment: `# Response models (plain Pydantic, NOT SQLModel)`

### List response envelope (paginated)
```python
class XxxListResponse(BaseModel):
    items: List[XxxListItem]
    total: int
    offset: int
    limit: int
```
Used by: runs.py (RunListResponse), events.py (EventListResponse)

### List response envelope (non-paginated)
```python
class XxxListResponse(BaseModel):
    items: List[XxxListItem]
```
Used by: steps.py (StepListResponse) - no pagination needed since steps are bounded per run

### Detail response
```python
class XxxDetail(BaseModel):
    field1: type
    field2: Optional[type] = None
    ...
```
Flat Pydantic model with all fields from DB model + any computed fields.

### Response model wiring
```python
@router.get("", response_model=XxxListResponse)
def list_xxx(...) -> XxxListResponse:
    ...

@router.get("/{id}", response_model=XxxDetail)
def get_xxx(...) -> XxxDetail:
    ...
```
Both `response_model=` parameter AND return type annotation are used.

## 5. Query Parameter Patterns

### Pydantic model for query params
```python
class XxxListParams(BaseModel):
    filter_field: Optional[str] = None
    another_filter: Optional[str] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=50, ge=1, le=200)
```

### Injection pattern
```python
@router.get(...)
def list_xxx(
    params: Annotated[XxxListParams, Depends()],
    db: DBSession,
) -> ...:
```

### Pagination defaults by endpoint
| Endpoint | limit default | limit max |
|----------|--------------|-----------|
| runs | 50 | 200 |
| events | 100 | 500 |

### Filter application pattern
```python
def _apply_filters(stmt, params: XxxListParams):
    """Append .where() clauses for non-None filter params."""
    if params.some_field is not None:
        stmt = stmt.where(Model.some_field == params.some_field)
    return stmt
```

## 6. Database Session Usage

### Dependency injection
```python
from llm_pipeline.ui.deps import DBSession
# DBSession = Annotated[ReadOnlySession, Depends(get_db)]
```

### Session methods used in routes
- `db.exec(stmt).all()` - fetch multiple rows
- `db.exec(stmt).first()` - fetch single row (returns None if not found)
- `db.scalar(stmt)` - fetch scalar value (used for COUNT queries)

### Query building pattern
```python
# Count query (for pagination)
count_stmt = select(func.count()).select_from(Model)
count_stmt = _apply_filters(count_stmt, params)
total: int = db.scalar(count_stmt) or 0

# Data query
data_stmt = select(Model)
data_stmt = _apply_filters(data_stmt, params)
data_stmt = (
    data_stmt
    .order_by(Model.field.desc())
    .offset(params.offset)
    .limit(params.limit)
)
rows = db.exec(data_stmt).all()
```

### 404 pattern
```python
item = db.exec(stmt).first()
if item is None:
    raise HTTPException(status_code=404, detail="X not found")
```

### Helper for parent existence check
```python
def _get_run_or_404(db: DBSession, run_id: str) -> PipelineRun:
    stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
    run = db.exec(stmt).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
```

## 7. Endpoint Function Conventions

### sync def (NOT async)
All HTTP endpoints use `def` not `async def`. Comment in every file:
```python
# Endpoints (all sync def -- SQLite is sync, FastAPI wraps in threadpool)
```

### Parameter order
1. Path params (if any)
2. `params: Annotated[XxxParams, Depends()]` (if filtering/pagination)
3. `db: DBSession`

### Return pattern
Explicit construction of response model from DB rows:
```python
return XxxListResponse(
    items=[
        XxxListItem(
            field1=r.field1,
            field2=r.field2,
        )
        for r in rows
    ],
    total=total,
    offset=params.offset,
    limit=params.limit,
)
```
Fields are mapped explicitly (no `.model_dump()` or `from_orm()`).

## 8. Testing Conventions

### Test fixtures (conftest.py)
- `_make_app()` creates app with StaticPool in-memory SQLite
- `app_client` fixture: empty DB
- `seeded_app_client` fixture: pre-populated with test data
- Uses `TestClient` from `starlette.testclient`

### Test patterns
- HTTP: `resp = client.get("/api/resource", params={...})` then assert `resp.status_code` and `resp.json()`
- Seed data uses fixed UUIDs for deterministic assertions
- Tests verify response shape (total, items, offset, limit) and content

## 9. Prompt Model Reference (for endpoint design)

### Prompt table columns
| Column | Type | Notes |
|--------|------|-------|
| id | Optional[int] | PK, auto |
| prompt_key | str(100) | indexed |
| prompt_name | str(200) | |
| prompt_type | str(50) | "system" or "user" |
| category | Optional[str(50)] | |
| step_name | Optional[str(50)] | |
| content | str | template text |
| required_variables | Optional[List[str]] | JSON column |
| description | Optional[str] | |
| version | str(20) | default "1.0" |
| is_active | bool | default True |
| created_at | datetime | |
| updated_at | datetime | |
| created_by | Optional[str(100)] | |

### Unique constraint
`(prompt_key, prompt_type)` - a prompt_key can have both a "system" and "user" variant.

### Variable extraction utility
```python
from llm_pipeline.prompts.loader import extract_variables_from_content
# extract_variables_from_content(content: str) -> List[str]
# Finds {variable_name} patterns, returns unique ordered list
```

## 10. Ambiguity: pipeline_name filter

Task 22 spec says:
```python
@router.get('/prompts')
async def list_prompts(
    prompt_type: str = None,
    pipeline_name: str = None
):
```

**The Prompt model has NO `pipeline_name` column.** Closest fields are `category` and `step_name`. This needs CEO clarification during implementation planning -- either:
1. Map `pipeline_name` filter to `category` column
2. Add a `pipeline_name` column to Prompt model (schema change, out of scope for task 22)
3. Drop the `pipeline_name` filter and use `category` + `step_name` filters instead

## 11. Known Test Deviation

`tests/test_ui.py` line 141-143 asserts `events router has prefix /events` but actual code has `prefix="/runs/{run_id}/events"`. This test is stale/wrong. Not blocking for prompts work but worth noting.

## 12. Checklist: What Prompts Router Must Follow

- [ ] `router = APIRouter(prefix="/prompts", tags=["prompts"])` (already exists)
- [ ] Response models: plain Pydantic BaseModel, NOT SQLModel
- [ ] Comment banner sections matching existing pattern
- [ ] `sync def` endpoints (not async)
- [ ] `DBSession` dependency from `llm_pipeline.ui.deps`
- [ ] `select()` from sqlmodel for queries
- [ ] `func.count()` from sqlalchemy for pagination count
- [ ] `Annotated[ParamsModel, Depends()]` for query params
- [ ] `response_model=` + return type annotation on each endpoint
- [ ] Explicit field mapping in response construction (no from_orm)
- [ ] `HTTPException(status_code=404, detail="...")` for not found
- [ ] Paginated list: `{ items, total, offset, limit }` envelope
- [ ] Import `extract_variables_from_content` from `llm_pipeline.prompts.loader`
