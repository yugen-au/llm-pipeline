# Step 2: Python/FastAPI Patterns Research

## 1. Framework & Dependencies

- **FastAPI 0.115.0+** (optional dep under `[project.optional-dependencies].ui`)
- **Pydantic v2** (core dep `pydantic>=2.0`)
- **SQLModel 0.0.14+** (core dep, used for DB table models only)
- **SQLAlchemy 2.0+** (core dep, sync engine)
- **Starlette** middleware (GZip, CORS) used directly
- **No async DB driver** -- project uses sync SQLite by default

## 2. Sync vs Async Convention

All endpoints are **sync `def`**, not `async def`. Comment across multiple route files:

> "all sync def -- SQLite is sync, FastAPI wraps in threadpool"

FastAPI auto-runs sync endpoints in a threadpool via `run_in_threadpool`. No `await` usage anywhere in routes. This is a **deliberate project-wide decision**, not per-endpoint.

## 3. Database Session Patterns

### 3a. Read-Only Endpoints (DI Pattern)

```python
from llm_pipeline.ui.deps import DBSession

@router.get("/drafts", response_model=DraftListResponse)
def list_drafts(db: DBSession) -> DraftListResponse:
    stmt = select(DraftStep).order_by(DraftStep.created_at.desc())
    rows = db.exec(stmt).all()
    ...
```

- `DBSession = Annotated[ReadOnlySession, Depends(get_db)]`
- `get_db()` creates `Session(engine)`, wraps in `ReadOnlySession`, yields it, closes in finally
- ReadOnlySession blocks: add, delete, flush, commit, merge, refresh, expire, expunge
- Used by: list/detail endpoints in runs.py, steps.py, events.py, prompts.py, pipelines.py, creator.py (list/get)

### 3b. Write Endpoints (Direct Session Pattern)

```python
@router.post("/drafts", status_code=201)
def create_draft_pipeline(body: CreateDraftPipelineRequest, request: Request):
    engine = request.app.state.engine
    with Session(engine) as session:
        draft = DraftPipeline(name=body.name, structure=body.structure)
        session.add(draft)
        try:
            session.commit()
            session.refresh(draft)
        except IntegrityError:
            session.rollback()
            return JSONResponse(status_code=409, ...)
```

- Bypasses DI completely -- gets engine from `request.app.state.engine`
- Creates `Session(engine)` directly via context manager
- Used by: all write endpoints in editor.py, creator.py (generate, test, accept, rename)

### 3c. Background Task Session Pattern

```python
def run_creator() -> None:
    # Runs in threadpool, separate from request lifecycle
    with Session(engine) as post_session:
        ...
        post_session.commit()
```

- Background tasks (via `BackgroundTasks.add_task`) create their own sessions
- Engine captured in closure from request handler

## 4. Request/Response Model Patterns

### Convention: Plain Pydantic BaseModel (NOT SQLModel)

Every route file has this comment block:

```python
# Response / request models (plain Pydantic, NOT SQLModel)
```

All request/response models inherit from `pydantic.BaseModel`. SQLModel is reserved exclusively for DB table definitions in `llm_pipeline/state.py`.

### Naming Conventions

| Pattern | Example |
|---------|---------|
| List item | `DraftPipelineItem`, `RunListItem`, `StepListItem` |
| Detail | `DraftPipelineDetail`, `RunDetail`, `StepDetail` |
| List response | `DraftPipelineListResponse`, `RunListResponse` (wraps items + total) |
| Create request | `CreateDraftPipelineRequest`, `TriggerRunRequest` |
| Update request | `UpdateDraftPipelineRequest`, `RenameRequest` |
| Response | `CompileResponse`, `GenerateResponse`, `AcceptResponse` |

### List Response Shape

```python
class DraftPipelineListResponse(BaseModel):
    items: list[DraftPipelineItem]
    total: int
```

Some have pagination fields (`offset`, `limit`) -- e.g. `RunListResponse`, `EventListResponse`.

### Modern Python Type Syntax

Uses `str | None` (PEP 604) and `list[str]` (PEP 585) -- not `Optional[str]` or `List[str]` in newer files. Older files still use `Optional[str]` and `List[str]` from typing.

## 5. Error Handling Patterns

### HTTPException (most common)

```python
# 404 Not Found
raise HTTPException(status_code=404, detail="Draft pipeline not found")

# 422 Unprocessable Entity (config/validation)
raise HTTPException(status_code=422, detail="No model configured...")

# 500 Internal Server Error
raise HTTPException(status_code=500, detail=str(exc))
```

### JSONResponse for 409 Conflict (IntegrityError)

```python
from sqlalchemy.exc import IntegrityError

try:
    session.commit()
except IntegrityError:
    session.rollback()
    return JSONResponse(
        status_code=409,
        content={"detail": "name_conflict", "suggested_name": suggested},
    )
```

Pattern includes finding a free suffix (`_2` through `_9`) for the suggested name.

### Background Task Error Handling

```python
try:
    pipeline.execute(...)
    pipeline.save()
except Exception:
    logger.exception("Background ... failed for run_id=%s", run_id)
    # Close pipeline session to avoid deadlock
    if pipeline is not None:
        pipeline.close()
    # Update status in separate session
    with Session(engine) as err_session:
        draft.status = "error"
        err_session.commit()
finally:
    bridge.complete()
    db_buffer.flush()
```

## 6. Router & Mounting Pattern

```python
# In route module
router = APIRouter(prefix="/editor", tags=["editor"])

# In app.py
app.include_router(editor_router, prefix="/api")
```

Final URL: `/api/editor/compile`, `/api/editor/drafts`, etc.

## 7. SQLModel Table Definitions (state.py)

### DraftPipeline (already exists)

```python
class DraftPipeline(SQLModel, table=True):
    __tablename__ = "draft_pipelines"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    structure: dict = Field(sa_column=Column(JSON))
    compilation_errors: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    status: str = Field(default="draft", max_length=20)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    __table_args__ = (
        UniqueConstraint("name", name="uq_draft_pipelines_name"),
        Index("ix_draft_pipelines_status", "status"),
    )
```

### DraftStep (already exists)

Same pattern: `SQLModel, table=True`, JSON columns via `sa_column=Column(JSON)`, `utc_now()` default factory, unique name constraint, status index.

### Table Registration (db/__init__.py)

Tables explicitly listed in `init_pipeline_db()`:

```python
SQLModel.metadata.create_all(engine, tables=[
    ..., DraftStep.__table__, DraftPipeline.__table__,
])
```

## 8. Test Patterns

### In-Memory SQLite with StaticPool

```python
from sqlalchemy.pool import StaticPool

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
init_pipeline_db(engine)
```

`StaticPool` ensures all connections (including FastAPI threadpool) share same in-memory DB.

### App Factory for Tests

```python
def _make_seeded_app():
    app = FastAPI(title="test")
    app.add_middleware(CORSMiddleware, ...)
    app.state.engine = engine
    app.state.default_model = "test-model"
    app.include_router(editor_router, prefix="/api")
    # Seed data
    with Session(engine) as s:
        s.add(DraftStep(...))
        s.commit()
    return app
```

### TestClient Usage

```python
from starlette.testclient import TestClient

with TestClient(app) as client:
    resp = client.get("/api/editor/drafts")
    assert resp.status_code == 200
```

## 9. Existing editor.py Endpoints (Already Implemented)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/editor/compile` | Validate step_refs exist (structural only) |
| GET | `/api/editor/available-steps` | Merged draft + registered steps |
| POST | `/api/editor/drafts` | Create DraftPipeline (201) |
| GET | `/api/editor/drafts` | List DraftPipelines |
| GET | `/api/editor/drafts/{draft_id}` | Get single DraftPipeline |
| PATCH | `/api/editor/drafts/{draft_id}` | Update name/structure |
| DELETE | `/api/editor/drafts/{draft_id}` | Delete DraftPipeline (204) |

## 10. Deviations from Task 52 Spec

1. **Compile does not instantiate pipeline classes** -- task spec called for `build_pipeline_class()`, `_validate_foreign_key_dependencies()`, `_validate_registry_order()`, `_build_execution_order()`. Actual implementation does step_ref existence checks only.

2. **Compile does not save DraftPipeline** -- task spec saved draft on both success and error. Actual implementation separates compile (validation) from draft CRUD (POST/PATCH /drafts).

3. **More endpoints than specified** -- task spec had 2 endpoints (compile + list drafts). Actual has 7 (compile + available-steps + full CRUD).

These deviations appear intentional -- the implementation has cleaner separation of concerns than the original spec.

## 11. app.state Registry Pattern

```python
app.state.engine          # SQLAlchemy Engine
app.state.pipeline_registry       # Dict[str, Callable] - pipeline factories
app.state.introspection_registry  # Dict[str, Type[PipelineConfig]] - for metadata
app.state.default_model           # str | None - pydantic-ai model string
```

Accessed in endpoints via `request.app.state.*` or `getattr(request.app.state, "...", {})`.
