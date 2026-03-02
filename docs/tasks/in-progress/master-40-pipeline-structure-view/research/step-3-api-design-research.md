# Step 3: API Design Research -- Backend API Layer for Pipeline Structure View

## 1. API Framework & Architecture

**Framework**: FastAPI (sync endpoints, SQLite backend, threadpool-wrapped)
**App factory**: `llm_pipeline/ui/app.py` -- `create_app()` accepts `db_path`, `cors_origins`, `pipeline_registry`, `introspection_registry`
**Router mounting**: All route modules mounted under `/api` prefix except WebSocket (`/ws/runs`, `/ws/runs/{run_id}`)
**CORS**: Permissive defaults (`["*"]`)
**Auth**: None -- no authentication or authorization patterns exist

## 2. Router Organization

Each resource has its own file in `llm_pipeline/ui/routes/`:

| File | Prefix | Tags | Endpoints |
|------|--------|------|-----------|
| `runs.py` | `/runs` | runs | GET list, GET detail, POST trigger, GET context |
| `steps.py` | `/runs/{run_id}/steps` | steps | GET list, GET detail |
| `events.py` | `/runs/{run_id}/events` | events | GET list |
| `prompts.py` | `/prompts` | prompts | GET list, GET detail |
| `pipelines.py` | `/pipelines` | pipelines | GET list, GET detail, GET step prompts |
| `websocket.py` | (no prefix) | websocket | WS /ws/runs, WS /ws/runs/{run_id} |

All HTTP endpoints are **sync `def`** (not `async def`). FastAPI wraps them in threadpool automatically since SQLite is sync.

## 3. Database & ORM Patterns

**Engine**: SQLite via `sqlmodel.create_engine`, stored on `app.state.engine`
**Session injection**: `deps.py` provides `DBSession = Annotated[ReadOnlySession, Depends(get_db)]`
**ReadOnlySession**: Wraps SQLModel Session, blocks write ops (add/delete/commit/flush), allows read ops (exec/query/scalar/get)
**Query pattern**: `select(Model).where(...)` via SQLModel, `func.count()` for totals
**Models**: `PipelineRun`, `PipelineStepState`, `PipelineRunInstance` in `state.py`; `PipelineEventRecord` in `events/models.py`; `Prompt` in `db/prompt.py`

## 4. Serialization Patterns

**Response models**: Plain `pydantic.BaseModel` (NOT SQLModel) for all API responses
**Convention**: Models defined at top of each route file in a `Response models` section
**Mapping**: Manual field-by-field mapping from SQLModel rows to Pydantic models (no `.from_orm()`)
**Nested models**: Supported (e.g. `RunDetail.steps: List[StepSummary]`)
**Optional fields**: `Optional[T] = None` for nullable values
**JSON fields**: `dict` or `Any` for schemaless data (e.g. `instructions_schema: Optional[Any]`)
**List wrappers**: `SomethingListResponse(items=[], total=N, offset=N, limit=N)` for paginated; `SomethingListResponse(items=[])` for non-paginated

## 5. Existing Pipeline API Endpoints (Task 24 -- DONE)

### GET /api/pipelines
- Returns `PipelineListResponse { pipelines: List[PipelineListItem] }`
- Reads from `app.state.introspection_registry` (not DB)
- Per-pipeline error handling: broken pipelines included with `error` field set, counts as null
- Sorted alphabetically by name

### GET /api/pipelines/{name}
- Returns `PipelineMetadata` matching `PipelineIntrospector.get_metadata()` shape
- 404 if name not in registry, 500 if introspection raises
- No DB access -- pure class-level introspection

### GET /api/pipelines/{name}/steps/{step_name}/prompts
- Returns `StepPromptsResponse { pipeline_name, step_name, prompts: List[StepPromptItem] }`
- **Uses DB** via DBSession to fetch actual prompt content from `Prompt` table
- Cross-pipeline leakage prevention: only returns keys declared by this step in this pipeline
- Empty prompts list if step has no declared keys

### Response Models in pipelines.py
```
PipelineListItem(name, strategy_count?, step_count?, has_input_schema, registry_model_count?, error?)
PipelineListResponse(pipelines: List[PipelineListItem])
StepMetadata(step_name, class_name, system_key?, user_key?, instructions_class?, instructions_schema?, context_class?, context_schema?, extractions[], transformation?, action_after?)
StrategyMetadata(name, display_name, class_name, steps: List[StepMetadata], error?)
PipelineMetadata(pipeline_name, registry_models[], strategies: List[StrategyMetadata], execution_order[], pipeline_input_schema?)
StepPromptItem(prompt_key, prompt_type, content, required_variables?, version)
StepPromptsResponse(pipeline_name, step_name, prompts: List[StepPromptItem])
```

## 6. Pipeline Registration Mechanism

Two separate registries on `app.state`:
- `pipeline_registry: Dict[str, Callable]` -- factory callables for execution (POST /api/runs)
- `introspection_registry: Dict[str, Type[PipelineConfig]]` -- class types for introspection (GET /api/pipelines)

Both set via `create_app()` parameters. No auto-discovery; host app must register explicitly.

## 7. PipelineIntrospector Output Shape

`PipelineIntrospector(pipeline_cls).get_metadata()` returns:
```python
{
    "pipeline_name": str,           # snake_case derived from class name
    "registry_models": [str],       # model class names from REGISTRY.MODELS
    "strategies": [
        {
            "name": str,            # snake_case from class name or NAME attr
            "display_name": str,    # DISPLAY_NAME attr or class name
            "class_name": str,      # raw class name
            "steps": [
                {
                    "step_name": str,
                    "class_name": str,
                    "system_key": str | None,
                    "user_key": str | None,
                    "instructions_class": str | None,
                    "instructions_schema": dict | None,  # JSON Schema from model_json_schema()
                    "context_class": str | None,
                    "context_schema": dict | None,
                    "extractions": [
                        {
                            "class_name": str,
                            "model_class": str | None,
                            "methods": [str]
                        }
                    ],
                    "transformation": {
                        "class_name": str,
                        "input_type": str | None,
                        "input_schema": dict | None,
                        "output_type": str | None,
                        "output_schema": dict | None
                    } | None,
                    "action_after": str | None
                }
            ],
            "error": str | None     # only set if strategy instantiation failed
        }
    ],
    "execution_order": [str],       # deduplicated step names across strategies
    "pipeline_input_schema": dict | None  # from INPUT_DATA ClassVar
}
```

Results cached per pipeline class identity (`id(cls)`). No DB/LLM dependencies.

## 8. Frontend API Layer (Task 31 -- DONE)

### Hooks (src/api/pipelines.ts)
- `usePipelines()` -- queryKey: `['pipelines']`, fetches `GET /api/pipelines`
- `usePipeline(name)` -- queryKey: `['pipelines', name]`, `enabled: Boolean(name)`
- `useStepInstructions(pipelineName, stepName)` -- queryKey: `['pipelines', name, 'steps', stepName, 'prompts']`, `staleTime: Infinity`

### TypeScript Types (src/api/types.ts) -- @provisional
All pipeline-related types exist but marked provisional. Key observation:

**Frontend-Backend Type Mismatches**:
1. Frontend `PipelineListItem` has `strategy_count: number`, `step_count: number` (non-nullable)
   Backend `PipelineListItem` has `strategy_count: Optional[int] = None`, `step_count: Optional[int] = None` (nullable for error cases)
2. Frontend `PipelineListItem` MISSING fields: `registry_model_count`, `error`
3. Frontend `PipelineStepMetadata` has `system_key: string`, `user_key: string` (non-nullable)
   Backend `StepMetadata` has `system_key: Optional[str] = None`, `user_key: Optional[str] = None` (nullable)

These mismatches must be fixed when removing @provisional tags during implementation.

### Query Client (src/queryClient.ts / src/api/client.ts)
- `apiClient<T>(path, options?)` prepends `/api`, throws typed `ApiError`
- All hooks use `@tanstack/react-query` v5

## 9. Testing Patterns

- **Test framework**: pytest with starlette.testclient.TestClient
- **Fixtures**: `conftest.py` provides `app_client` (empty) and `seeded_app_client` (with test data)
- **Pipeline test fixtures**: `empty_introspection_client` and `populated_introspection_client` with test pipeline classes from `tests/test_introspection.py`
- **DB**: In-memory SQLite with `StaticPool` for thread safety
- **Mocking**: `unittest.mock.patch.object` for PipelineIntrospector error paths
- **20 existing pipeline tests** in `tests/ui/test_pipelines.py`

## 10. Implications for Task 40 Implementation

### No new backend endpoints needed
All three endpoints required by the Structure View already exist:
1. `GET /api/pipelines` -- pipeline list with counts
2. `GET /api/pipelines/{name}` -- full introspection metadata
3. `GET /api/pipelines/{name}/steps/{step_name}/prompts` -- step prompt content

### Frontend work required
1. Fix @provisional TypeScript types to match actual backend response shapes
2. Build the PipelinesPage component (currently a stub in `src/routes/pipelines.tsx`)
3. Components needed: pipeline list sidebar, strategy list, step list, schema viewer, prompt key links
4. All data is static config (not runtime) -- `staleTime: Infinity` appropriate for detail queries

### No auth considerations
No existing auth patterns to follow or integrate with.

## 11. Key Files Reference

### Backend
- `llm_pipeline/ui/app.py` -- app factory, router wiring, registry setup
- `llm_pipeline/ui/deps.py` -- DBSession dependency injection
- `llm_pipeline/ui/routes/pipelines.py` -- pipeline endpoints (6 Pydantic models, 3 endpoints)
- `llm_pipeline/introspection.py` -- PipelineIntrospector (pure class-level, cached, no DB)

### Frontend
- `llm_pipeline/ui/frontend/src/api/types.ts` -- TypeScript interfaces (@provisional pipeline types)
- `llm_pipeline/ui/frontend/src/api/pipelines.ts` -- TanStack Query hooks (3 hooks)
- `llm_pipeline/ui/frontend/src/api/query-keys.ts` -- query key factory
- `llm_pipeline/ui/frontend/src/api/client.ts` -- fetch wrapper
- `llm_pipeline/ui/frontend/src/routes/pipelines.tsx` -- placeholder stub (to be replaced)

### Tests
- `tests/ui/test_pipelines.py` -- 20 endpoint tests
- `tests/ui/conftest.py` -- shared fixtures, app factory helper
