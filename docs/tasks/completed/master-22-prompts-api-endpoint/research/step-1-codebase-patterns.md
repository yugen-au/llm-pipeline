# Step 1: Codebase Patterns for Prompts API Endpoint

## Route File Structure

All route modules in `llm_pipeline/ui/routes/` follow the same pattern:

```
llm_pipeline/ui/routes/
  __init__.py          # empty package marker
  runs.py              # GET /runs, GET /runs/{run_id}, POST /runs
  steps.py             # GET /runs/{run_id}/steps, GET /runs/{run_id}/steps/{step_number}
  events.py            # GET /runs/{run_id}/events
  prompts.py           # STUB ONLY - router + prefix/tags, no endpoints
  pipelines.py         # STUB ONLY - router + prefix/tags, no endpoints
  websocket.py         # WS /ws/runs/{run_id}
```

### Router Declaration Pattern

Every route module:
1. Creates `router = APIRouter(prefix="/<resource>", tags=["<resource>"])`
2. Defines response models as plain Pydantic `BaseModel` (NOT SQLModel)
3. Defines query param models as `BaseModel` with `Query()` defaults
4. Uses `sync def` (not async) for all HTTP endpoints (SQLite is sync; FastAPI wraps in threadpool)
5. Injects DB via `db: DBSession` parameter (from `llm_pipeline.ui.deps`)

### Current prompts.py stub

```python
"""Prompts route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/prompts", tags=["prompts"])
```

Mounted in `app.py` as: `app.include_router(prompts_router, prefix="/api")` -> effective prefix `/api/prompts`

## App Factory (`llm_pipeline/ui/app.py`)

- `create_app(db_path, cors_origins, pipeline_registry, introspection_registry)` -> `FastAPI`
- Creates engine, calls `init_pipeline_db(engine)`, stores on `app.state.engine`
- Lazy-imports all 6 routers inside function body (avoids circular imports)
- Includes all routers with `prefix="/api"` except websocket (no prefix)
- CORS middleware with configurable origins (default `["*"]`)

## Database Session Handling (`llm_pipeline/ui/deps.py`)

```python
def get_db(request: Request) -> Generator[ReadOnlySession, None, None]:
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield ReadOnlySession(session)
    finally:
        session.close()

DBSession = Annotated[ReadOnlySession, Depends(get_db)]
```

Key points:
- `DBSession` is the type alias used in route function signatures
- Yields `ReadOnlySession` which blocks all write operations (add, commit, delete, etc.)
- Allows: `exec()`, `scalar()`, `query()`, `get()`, `execute()`, `scalars()`
- Session closed in `finally` block

## Response Model Patterns

All response models are **plain Pydantic BaseModel** (never SQLModel). Pattern from existing routes:

### List endpoint response:
```python
class ItemModel(BaseModel):
    field1: str
    field2: Optional[str] = None

class ListResponse(BaseModel):
    items: List[ItemModel]
    total: int
    offset: int
    limit: int
```

### Detail endpoint response:
```python
class DetailModel(BaseModel):
    field1: str
    nested: List[SubModel]
```

### Query params model:
```python
class ListParams(BaseModel):
    filter1: Optional[str] = None
    filter2: Optional[str] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=50, ge=1, le=200)
```

Used as: `params: Annotated[ListParams, Depends()]`

## Error Handling Conventions

- 404: `raise HTTPException(status_code=404, detail="<Resource> not found")`
- Helper pattern: `_get_run_or_404(db, run_id)` helper function in events.py and steps.py
- No custom exception handlers; FastAPI defaults handle validation errors (422)

## Query Patterns

```python
# Count query
count_stmt = select(func.count()).select_from(Model)
count_stmt = _apply_filters(count_stmt, params)
total: int = db.scalar(count_stmt) or 0

# Data query
data_stmt = select(Model)
data_stmt = _apply_filters(data_stmt, params)
data_stmt = data_stmt.order_by(Model.field.desc()).offset(params.offset).limit(params.limit)
rows = db.exec(data_stmt).all()

# Single item
stmt = select(Model).where(Model.key == value)
item = db.exec(stmt).first()
```

Filter helper pattern:
```python
def _apply_filters(stmt, params):
    if params.field is not None:
        stmt = stmt.where(Model.field == params.field)
    return stmt
```

## Test Patterns (`tests/ui/`)

### conftest.py fixtures:
- `_make_app()`: StaticPool in-memory SQLite, `check_same_thread=False`, builds full FastAPI app with all routers
- `app_client`: empty DB TestClient
- `seeded_app_client`: pre-populated with runs/steps/events seed data

### Test structure:
- Tests use `starlette.testclient.TestClient`
- Assert response status codes, JSON body structure, field values
- Seed data inserted via `Session(engine)` directly in fixtures

## Prompt Data Layer

### Prompt model (`llm_pipeline/db/prompt.py`):
| Field | Type | Notes |
|---|---|---|
| id | int (PK) | auto-increment |
| prompt_key | str(100) | indexed, part of unique constraint |
| prompt_name | str(200) | display name |
| prompt_type | str(50) | "system" or "user", part of unique constraint |
| category | str(50) | optional, indexed with step_name |
| step_name | str(50) | optional, indexed with category |
| content | str | template text with {variable_name} placeholders |
| required_variables | List[str] (JSON) | extracted from content during sync |
| description | str | optional |
| version | str(20) | default "1.0" |
| is_active | bool | default True, indexed |
| created_at | datetime | UTC |
| updated_at | datetime | UTC |
| created_by | str(100) | optional |

Constraints:
- `UniqueConstraint('prompt_key', 'prompt_type')` -- one system + one user per key
- `Index("ix_prompts_category_step", "category", "step_name")`
- `Index("ix_prompts_active", "is_active")`

### Variable extraction (`llm_pipeline/prompts/loader.py`):
```python
def extract_variables_from_content(content: str) -> List[str]:
    pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
    # returns unique ordered list of variable names
```

### PromptService (`llm_pipeline/prompts/service.py`):
- Constructor takes `Session`, stores as `self.session`
- `get_prompt(prompt_key, prompt_type, context, fallback)` -> str (content)
- Filters by `is_active == True`
- Not used by routes currently (routes query DB directly via DBSession)

## AMBIGUITIES IDENTIFIED

### 1. BLOCKING: pipeline_name filter does not exist on Prompt model
Task 22 spec says `pipeline_name: str = None` as a query filter. The Prompt table has **no pipeline_name column**. Available organizational fields: `category`, `step_name`. Need CEO decision on which field to map to, or whether to drop this filter.

### 2. Variable extraction strategy
Task says "reuse extract_variables_from_content()" but Prompt model already stores `required_variables` (populated during `sync_prompts`). Options:
- (a) Use stored `required_variables` from DB (fast, consistent)
- (b) Always re-extract from content (matches task spec literally)
- (c) Use stored if available, re-extract as fallback (handles legacy rows with NULL)

### 3. GET /prompts/{prompt_key} response shape
Task says "Return full prompt detail with both system and user variants." The unique constraint is `(prompt_key, prompt_type)`, so one key can have both a system and user row. Should the detail endpoint return a compound object like:
```json
{
  "prompt_key": "...",
  "system": { "content": "...", "variables": [...] },
  "user": { "content": "...", "variables": [...] }
}
```
Or return them as a flat list of prompt objects?
