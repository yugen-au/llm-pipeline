# Research Step 1: Existing API Patterns

## Key Finding: Task 51 Already Implemented All Editor Endpoints

Task 51 (visual pipeline editor) shipped 7 backend endpoints in `llm_pipeline/ui/routes/editor.py`. These overlap significantly with task 52's described scope:

| Endpoint | Exists? | Task 52 Spec |
|----------|---------|-------------|
| `POST /api/editor/compile` | YES (L128-161) | YES |
| `GET /api/editor/available-steps` | YES (L164-210) | not mentioned |
| `POST /api/editor/drafts` | YES (L218-248) | implied |
| `GET /api/editor/drafts` | YES (L251-270) | YES |
| `GET /api/editor/drafts/{id}` | YES (L273-289) | implied |
| `PATCH /api/editor/drafts/{id}` | YES (L292-349) | implied |
| `DELETE /api/editor/drafts/{id}` | YES (L352-361) | implied |

### Current Compile vs Task 52 Spec

**Current compile** (task 51): Checks step_ref existence against introspection_registry + non-errored DraftSteps. Structural validation only. Stateless (no DraftPipeline created).

**Task 52 spec**: Build dynamic PipelineConfig class from structure, instantiate to trigger `_validate_foreign_key_dependencies()`, `_validate_registry_order()`, `_build_execution_order()`. Save DraftPipeline with compilation_errors on failure.

This is a fundamentally different validation depth. `build_pipeline_class()` does not exist anywhere in the codebase.

---

## Route Architecture Patterns

### App Factory (`llm_pipeline/ui/app.py`)

- `create_app()` factory function returns FastAPI instance
- Engine stored on `app.state.engine`
- Registries stored on `app.state.pipeline_registry` (factories) and `app.state.introspection_registry` (classes)
- `app.state.default_model` stores pydantic-ai model string
- All route modules imported and included with `prefix="/api"` (except websocket)
- CORS middleware with `["*"]` origins, GZip compression

### Router Registration

```python
# Pattern in app.py
from llm_pipeline.ui.routes.editor import router as editor_router
app.include_router(editor_router, prefix="/api")
```

Each router has its own prefix:
- `/runs` -> `/api/runs`
- `/pipelines` -> `/api/pipelines`
- `/prompts` -> `/api/prompts`
- `/creator` -> `/api/creator`
- `/editor` -> `/api/editor`

### Router Definition Pattern

```python
router = APIRouter(prefix="/editor", tags=["editor"])
```

Tags match the prefix name. Each route file is self-contained with request/response models at top.

---

## Endpoint Implementation Patterns

### Request/Response Models

- Always plain Pydantic `BaseModel`, NEVER `SQLModel`
- Comment convention: `# Request / response models (plain Pydantic, NOT SQLModel)`
- List responses wrap items with total count: `DraftPipelineListResponse(items=[], total=int)`
- Paginated responses add offset/limit (runs, events, prompts)
- Detail models extend list item models: `DraftPipelineDetail(DraftPipelineItem)`

### DB Access Patterns

**Read-only endpoints** use `DBSession` dependency (from `deps.py`):
```python
from llm_pipeline.ui.deps import DBSession

@router.get("/drafts")
def list_drafts(db: DBSession) -> ...:
    stmt = select(DraftStep).order_by(...)
    rows = db.exec(stmt).all()
```

**Write endpoints** open `Session(engine)` directly:
```python
@router.post("/drafts")
def create_draft(body: CreateRequest, request: Request):
    engine = request.app.state.engine
    with Session(engine) as session:
        session.add(obj)
        session.commit()
        session.refresh(obj)
```

### Error Handling

- 404: `raise HTTPException(status_code=404, detail="...")`
- 409 (name conflict): `return JSONResponse(status_code=409, content={...})`
- 422 (validation): `raise HTTPException(status_code=422, detail="...")`
- 500 (internal): `raise HTTPException(status_code=500, detail=str(exc))`

### Sync Endpoints

All route handlers are `def` (sync), not `async def`. Comment: "all sync def -- FastAPI wraps in threadpool". This is appropriate for SQLite/sync DB access.

---

## State Models (`llm_pipeline/state.py`)

### DraftPipeline

```python
class DraftPipeline(SQLModel, table=True):
    __tablename__ = "draft_pipelines"
    id: Optional[int] = Field(primary_key=True)
    name: str = Field(max_length=100)           # unique
    structure: dict = Field(sa_column=Column(JSON))
    compilation_errors: Optional[dict] = Field(sa_column=Column(JSON))
    status: str = Field(default="draft")        # draft, tested, accepted, error
    created_at: datetime
    updated_at: datetime
```

### DraftStep

```python
class DraftStep(SQLModel, table=True):
    __tablename__ = "draft_steps"
    id: Optional[int] = Field(primary_key=True)
    name: str = Field(max_length=100)           # unique
    description: Optional[str]
    generated_code: dict = Field(sa_column=Column(JSON))
    test_results: Optional[dict] = Field(sa_column=Column(JSON))
    validation_errors: Optional[dict] = Field(sa_column=Column(JSON))
    status: str = Field(default="draft")        # draft, tested, accepted, error
    run_id: Optional[str]
    created_at: datetime
    updated_at: datetime
```

Both registered in `init_pipeline_db()` via `SQLModel.metadata.create_all()`.

---

## PipelineConfig Validation Logic (`llm_pipeline/pipeline.py`)

### __init__ Validation Chain (L273-275)

```python
self._build_execution_order()
self._validate_foreign_key_dependencies()
self._validate_registry_order()
```

### _build_execution_order (L334-349)

Iterates strategies, deduplicates step classes, builds `_step_order` dict mapping step_class -> position. Also maps extraction models to steps and tracks transformations.

### _validate_foreign_key_dependencies (L368-385)

Checks that for every FK relationship in REGISTRY.MODELS, the target model appears BEFORE the source model in the registry list. Raises `ValueError` with structured message.

### _validate_registry_order (L387-404)

Checks that registry model order matches extraction step execution order. Raises `ValueError` if a model appears before another in registry but its extraction step runs later.

### __init_subclass__ (L160-207)

Class-level validation during subclass definition:
- Pipeline class must end with "Pipeline" suffix
- Registry class must be named `{Prefix}Registry`
- Strategies class must be named `{Prefix}Strategies`
- AgentRegistry class must be named `{Prefix}AgentRegistry`
- INPUT_DATA must be PipelineInputData subclass if declared

### __init__ Requirements (L209-291)

Constructor requires:
- `model: str` (pydantic-ai model string) - REQUIRED
- `engine` or `session` for DB
- `REGISTRY` class var must be set
- `STRATEGIES` class var must be set (or strategies param)

For validation-only instantiation, `model` is required but no LLM calls happen during __init__. A dummy model string could work.

---

## Frontend API Layer

### Client (`api/client.ts`)

```typescript
export async function apiClient<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`/api${path}`, options)
    // throws ApiError on non-OK
    return response.json() as Promise<T>
}
```

### Editor Hooks (`api/editor.ts`)

7 TanStack Query hooks matching all 7 backend endpoints:
- `useAvailableSteps()` -> GET /editor/available-steps
- `useDraftPipelines()` -> GET /editor/drafts
- `useDraftPipeline(id)` -> GET /editor/drafts/{id}
- `useCompilePipeline()` -> POST /editor/compile (mutation)
- `useCreateDraftPipeline()` -> POST /editor/drafts (mutation, invalidates list)
- `useUpdateDraftPipeline()` -> PATCH /editor/drafts/{id} (mutation, invalidates detail+list)
- `useDeleteDraftPipeline()` -> DELETE /editor/drafts/{id} (mutation, invalidates list)

---

## Introspection System (`llm_pipeline/introspection.py`)

`PipelineIntrospector` operates entirely on class types (no instantiation). Returns cached metadata dict:
```python
{
    "pipeline_name": str,
    "registry_models": [str],
    "strategies": [{
        "name": str,
        "display_name": str,
        "class_name": str,
        "steps": [{
            "step_name": str,
            "class_name": str,
            "system_key": str | None,
            "user_key": str | None,
            ...
        }]
    }],
    "execution_order": [str],
    "pipeline_input_schema": dict | None,
}
```

The editor's `_collect_registered_steps()` helper already uses PipelineIntrospector to build step_name -> pipeline_names mapping.

---

## Architectural Questions Requiring CEO Input

1. **Scope overlap**: Task 51 already implemented all 7 editor endpoints including compile and drafts CRUD. Is task 52's remaining scope limited to enhancing compile with PipelineConfig-level validation (build_pipeline_class + instantiation)?

2. **Draft step validation**: Should `build_pipeline_class()` support draft steps (code stored as JSON in draft_steps.generated_code, not importable Python)? If yes, this requires dynamic code loading/exec which has security implications. If no, compile can only validate pipelines composed entirely of registered steps.

3. **Compile side-effects**: Current compile is stateless (returns CompileResponse, no DB writes). Task 52 spec shows compile creating/updating DraftPipeline records. Should compile gain this side-effect, or should validation remain stateless with DraftPipeline CRUD handled by existing endpoints?

4. **Model parameter**: PipelineConfig.__init__ requires a `model: str` parameter. For validation-only compile, what model string should be used? A dummy value like `"test"` would work since no LLM calls happen during __init__, but this feels fragile.

5. **Tests**: Task 51 SUMMARY recommends adding pytest tests for editor endpoints. Should task 52 include writing these tests, or is that separate work?
