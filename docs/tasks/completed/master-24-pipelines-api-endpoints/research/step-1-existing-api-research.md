# Step 1: Existing API Structure Research

## 1. Application Architecture

### App Factory (`llm_pipeline/ui/app.py`)

- `create_app()` returns a `FastAPI` instance
- Params: `db_path`, `cors_origins`, `pipeline_registry`, `introspection_registry`
- Stores `engine`, `pipeline_registry`, `introspection_registry` on `app.state`
- CORS middleware: allow all origins by default, credentials=False
- Routers imported inside function body (deferred imports), mounted with `app.include_router(router, prefix="/api")`
- WebSocket router mounted without `/api` prefix

### Router Registration Pattern

```python
from llm_pipeline.ui.routes.runs import router as runs_router
app.include_router(runs_router, prefix="/api")
```

All REST routers get `/api` prefix. Each router defines its own sub-prefix:
| Router | File | Prefix (after /api) | Tags |
|--------|------|---------------------|------|
| runs | routes/runs.py | /runs | ["runs"] |
| steps | routes/steps.py | /runs/{run_id}/steps | ["steps"] |
| events | routes/events.py | /runs/{run_id}/events | ["events"] |
| prompts | routes/prompts.py | /prompts | ["prompts"] |
| pipelines | routes/pipelines.py | /pipelines | ["pipelines"] |
| websocket | routes/websocket.py | (none - /ws prefix) | ["websocket"] |

### Dependency Injection (`llm_pipeline/ui/deps.py`)

- `get_db(request)` yields `ReadOnlySession` wrapping SQLModel `Session`
- Typed alias: `DBSession = Annotated[ReadOnlySession, Depends(get_db)]`
- `Request` object used directly to access `app.state.engine`, `app.state.pipeline_registry`

## 2. Existing Route Patterns

### Response Models

All routes use plain Pydantic `BaseModel` (NOT SQLModel) for responses. Standard layout per file:

1. Response/request models section
2. Query params model section
3. Helpers section
4. Endpoints section

### Endpoint Style

- All sync `def` (not `async def`) -- SQLite is sync, FastAPI wraps in threadpool
- DB-backed routes use `DBSession` dependency
- `Request` used when accessing `app.state` directly (e.g. `trigger_run`)
- Return typed response models directly

### Error Handling

- `HTTPException(status_code=404, detail="...")` for not-found resources
- 422 automatic from Pydantic/FastAPI validation (invalid query params, body)
- Helper pattern: `_get_run_or_404(db, run_id)` for parent resource validation

### Pagination (DB routes only)

- Offset/limit via `Query(default=..., ge=..., le=...)` in Pydantic params model
- Response wraps: `{ items: [...], total: int, offset: int, limit: int }`
- Used by runs, events, prompts; NOT by steps (simple list)

## 3. Pipelines Router Current State

**File:** `llm_pipeline/ui/routes/pipelines.py`
**Content:** Empty shell -- router declaration only, no endpoints:

```python
"""Pipeline configurations route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/pipelines", tags=["pipelines"])
```

Already registered in `app.py` at line 72/79.

## 4. Introspection Infrastructure (Task 23 Output)

### `PipelineIntrospector` (`llm_pipeline/introspection.py`)

- Constructor: `PipelineIntrospector(pipeline_cls: Type[PipelineConfig])`
- No DB, FastAPI, or LLM dependencies
- Class-level cache (`_cache: ClassVar[Dict[int, Dict]]`) keyed by `id(pipeline_cls)`
- `get_metadata()` returns:

```python
{
    "pipeline_name": str,          # snake_case derived from class name
    "registry_models": List[str],  # model class names from REGISTRY.MODELS
    "strategies": [
        {
            "name": str,           # snake_case strategy name
            "display_name": str,   # class __name__ or DISPLAY_NAME
            "class_name": str,     # raw class name
            "steps": [
                {
                    "step_name": str,
                    "class_name": str,
                    "system_key": str,
                    "user_key": str,
                    "instructions_class": str | None,
                    "instructions_schema": dict | None,  # Pydantic JSON schema
                    "context_class": str | None,
                    "context_schema": dict | None,
                    "extractions": [{"class_name", "model_class", "methods"}],
                    "transformation": {"class_name", "input_type", "input_schema", "output_type", "output_schema"} | None,
                    "action_after": str | None,
                }
            ],
            "error": str | None,   # only if strategy instantiation failed
        }
    ],
    "execution_order": List[str],  # deduplicated step names
}
```

### `app.state.introspection_registry`

- Type: `Dict[str, Type[PipelineConfig]]` -- maps pipeline name to class
- Set in `create_app()`: `app.state.introspection_registry = introspection_registry or {}`
- Separate from `pipeline_registry` (which stores factory callables for execution)

## 5. Frontend Contract (Provisional Types)

### `GET /api/pipelines` expected response:

```typescript
{ pipelines: PipelineListItem[] }
```

Where `PipelineListItem`:
```typescript
{
  name: string
  strategy_count: number
  step_count: number
  has_input_schema: boolean
}
```

**No pagination.** Pipelines are static config, small count per application.

### `GET /api/pipelines/{name}` expected response:

```typescript
PipelineMetadata  // matches PipelineIntrospector.get_metadata() shape exactly
```

Fields: `pipeline_name`, `registry_models`, `strategies` (with steps), `execution_order`.

### Frontend file: `llm_pipeline/ui/frontend/src/api/pipelines.ts`

- `usePipelines()` calls `apiClient<{ pipelines: PipelineListItem[] }>('/pipelines')`
- `usePipeline(name)` calls `apiClient<PipelineMetadata>('/pipelines/' + name)`
- Both use TanStack Query with default staleTime (30s)

## 6. Test Infrastructure

### Test conftest (`tests/ui/conftest.py`)

- `_make_app()` creates app with in-memory SQLite (StaticPool, check_same_thread=False)
- Includes all routers including pipelines_router
- Does NOT set `app.state.introspection_registry` -- needs adding for pipeline endpoint tests
- Fixtures: `app_client` (empty DB), `seeded_app_client` (pre-populated runs/steps/events)

### Test pattern

- `TestClient(app)` from Starlette
- Test classes grouped by endpoint (e.g. `TestListRuns`, `TestGetRun`)
- Tests in `tests/ui/test_<resource>.py`
- Custom fixtures per test file when different seeding needed (e.g. `test_prompts.py` has `seeded_prompts_client`)

## 7. Implementation Recommendations

### Endpoint 1: `GET /api/pipelines` (List)

- Iterate `app.state.introspection_registry`, run `PipelineIntrospector(cls).get_metadata()` per entry
- Derive `PipelineListItem` summary from full metadata:
  - `name` = metadata `pipeline_name`
  - `strategy_count` = `len(metadata["strategies"])`
  - `step_count` = `len(metadata["execution_order"])` (deduplicated)
  - `has_input_schema` = any step across any strategy has non-null `instructions_schema`
- Return `{ "pipelines": [...] }` (no pagination needed)
- Access via `Request` dependency (like `trigger_run` pattern), not `DBSession`

### Endpoint 2: `GET /api/pipelines/{name}` (Detail)

- Look up `name` in `app.state.introspection_registry`
- If not found: `HTTPException(status_code=404, detail="Pipeline '...' not found")`
- Run `PipelineIntrospector(cls).get_metadata()` and return directly
- Response model should match `PipelineMetadata` frontend type

### No DB dependency

Neither endpoint needs `DBSession`. Access `request.app.state.introspection_registry` via `Request` param.

### Test file

New `tests/ui/test_pipelines.py` with:
- Fixture creating app with `introspection_registry` containing test pipeline classes
- Test classes: `TestListPipelines`, `TestGetPipeline`
- Reuse fake pipeline class pattern from `tests/test_introspection.py`

## 8. Scope Boundaries

### In scope (Task 24)
- Two REST endpoints in `routes/pipelines.py`
- Pydantic response models
- Error handling (404 for unknown pipeline)
- Tests in `tests/ui/test_pipelines.py`

### Out of scope
- Task 40: Pipeline Structure frontend view (downstream, depends on task 24)
- Task 52: Visual Editor API endpoints (downstream, depends on task 24)
- Pagination: not needed for static config data
- DB models: no new DB tables
- Authentication/authorization: not present in any existing route
