# Research Summary

## Executive Summary

Validated 3 research documents against actual source code (app.py, pipelines.py, deps.py, introspection.py, conftest.py, frontend types.ts, pipelines.ts, test_introspection.py). Core architecture findings are consistent: empty router exists and is wired, introspection_registry on app.state is typed and ready, PipelineIntrospector is pure class-level with caching. However, a critical contradiction exists between research docs on the list endpoint response shape and field set. Three questions require CEO clarification before planning.

## Domain Findings

### App Factory & Router Wiring
**Source:** step-1, step-2, app.py (verified)
- `create_app()` accepts `introspection_registry: Optional[Dict[str, Type[PipelineConfig]]]` -- confirmed at line 20
- Stored as `app.state.introspection_registry = introspection_registry or {}` -- confirmed at line 65
- `pipelines_router` imported and mounted with `prefix="/api"` -- confirmed at lines 72, 79
- Final URL path: `/api/pipelines` and `/api/pipelines/{name}`
- No changes needed to app.py

### Pipelines Router (Target File)
**Source:** step-1, step-2, pipelines.py (verified)
- Contains only: `router = APIRouter(prefix="/pipelines", tags=["pipelines"])` -- confirmed, 4 lines total
- No endpoints, no imports beyond APIRouter
- Ready for implementation

### PipelineIntrospector
**Source:** step-1, step-2, introspection.py (verified)
- Located at `llm_pipeline/introspection.py` (NOT `ui/introspection.py` as task 23 originally planned -- accepted deviation)
- Exported from `llm_pipeline/__init__.py` (confirmed via Graphiti)
- `get_metadata()` returns dict with keys: `pipeline_name`, `registry_models`, `strategies`, `execution_order`
- Class-level cache `_cache: ClassVar[Dict[int, Dict]]` keyed by `id(pipeline_cls)`
- No DB, FastAPI, or LLM dependencies -- confirmed via Graphiti and source
- Defensive error handling for broken strategies: returns `error` key in strategy dict, no exception
- Step entries include: step_name, class_name, system_key, user_key, instructions_class, instructions_schema, context_class, context_schema, extractions, transformation, action_after

### Existing Endpoint Patterns
**Source:** step-1, step-2, runs.py (verified)
- All sync `def` (not `async def`)
- Response models: plain Pydantic `BaseModel`, NOT SQLModel
- DB routes use `DBSession` dependency; non-DB routes use `Request` for `app.state` access
- Error handling: `HTTPException(status_code=404)` for not-found
- Paginated responses: `{ items: [...], total: int, offset: int, limit: int }`
- Non-DB access pattern (from runs.py trigger_run): `registry: dict = getattr(request.app.state, "pipeline_registry", {})`

### Frontend Contract (Existing Code)
**Source:** step-1, types.ts, pipelines.ts (verified)
- `usePipelines()` expects: `apiClient<{ pipelines: PipelineListItem[] }>('/pipelines')`
- `usePipeline(name)` expects: `apiClient<PipelineMetadata>('/pipelines/' + name)`
- `PipelineListItem`: `{ name, strategy_count, step_count, has_input_schema }`
- `PipelineMetadata`: `{ pipeline_name, registry_models, strategies, execution_order }` -- matches introspector output exactly
- All types marked `@provisional`
- Detail response types (PipelineStepMetadata, StrategyMetadata, etc.) fully mirror introspector output shape

### Test Infrastructure
**Source:** step-1, step-2, conftest.py (verified)
- `_make_app()` does NOT set `app.state.introspection_registry` -- confirmed line 49 only sets `pipeline_registry`
- Test pipeline classes exist in `tests/test_introspection.py`: WidgetPipeline, ScanPipeline, GadgetPipeline
- These classes cover: extractions, transformations (Pydantic + non-Pydantic), broken strategies, context
- `test_introspection.py` has `clear_introspector_cache` autouse fixture -- pipeline endpoint tests will need similar
- Pattern: custom fixtures per test file when different seeding needed (e.g. test_prompts.py)

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| [pending - see Questions below] | [awaiting CEO response] | [TBD] |

## Assumptions Validated
- [x] pipelines.py router exists and is empty -- confirmed against source
- [x] Router already wired in app.py with /api prefix -- confirmed lines 72, 79
- [x] introspection_registry stored on app.state as Dict[str, Type[PipelineConfig]] -- confirmed line 20, 65
- [x] PipelineIntrospector has no DB/FastAPI/LLM deps -- confirmed via source and Graphiti
- [x] get_metadata() returns stable dict shape with 4 top-level keys -- confirmed via source (lines 255-260)
- [x] Class-level cache prevents repeated introspection overhead -- confirmed (line 200-202)
- [x] Broken strategies handled defensively (error key, no exception) -- confirmed (lines 231-239)
- [x] All existing endpoints use sync def, plain Pydantic BaseModel -- confirmed via runs.py
- [x] No pagination needed for pipeline list (bounded by registered classes) -- consistent across all docs
- [x] conftest.py _make_app() missing introspection_registry -- confirmed (line 49)
- [x] Test pipeline classes from test_introspection.py reusable for endpoint tests -- classes are module-level, no DB conflict
- [x] Detail endpoint response should match PipelineMetadata frontend type exactly -- types.ts lines 296-301 mirror introspector output
- [x] Frontend types are provisional and explicitly expect task 24 to provide the backend -- confirmed @provisional tags

## Open Items
- **CRITICAL: List response shape contradiction** -- step 1 + frontend use `{ pipelines: [...] }` key; step 3 uses `{ items: [...], total }` key. Must resolve before planning.
- **CRITICAL: PipelineListItem field disagreement** -- frontend has `has_input_schema: boolean`; step 3 proposes `registry_model_count: int` instead. Must resolve.
- **MEDIUM: has_input_schema semantic definition** -- if kept, need to define derivation logic (instructions_schema? context_schema? either?)
- **LOW: List error handling strategy** -- what to do when introspection fails for one pipeline in the list (skip, include with error, or 500)
- **LOW: Cache clearing in endpoint tests** -- pipeline endpoint tests need `PipelineIntrospector._cache.clear()` fixture (not mentioned in research but required)
- **LOW: Alphabetical sort** -- step 3 recommends sorting by name; needs confirmation since dict insertion order != alphabetical

## Recommendations for Planning
1. **Match existing frontend types** for list endpoint -- use `{ pipelines: PipelineListItem[] }` key (not `items`) since frontend code already exists and consumes this shape. Minimizes downstream work for task 40.
2. **Use Option A (strictly typed Pydantic models)** for detail response -- consistent with codebase convention, enables OpenAPI docs, frontend types already exist.
3. **Create dedicated test fixture** in new `tests/ui/test_pipelines.py` that builds app with introspection_registry populated. Import test pipeline classes from test_introspection.py.
4. **Include cache-clearing fixture** in test_pipelines.py to prevent cross-test pollution (mirror test_introspection.py pattern).
5. **No conftest.py changes** -- use per-file fixture pattern (like test_prompts.py) to keep existing test infrastructure stable.
6. **Sync def, no DBSession** -- follow non-DB access pattern from trigger_run: `request.app.state.introspection_registry` via `Request` param.
7. **Defensive try/except per pipeline** in list endpoint for safety, but **skip broken pipelines silently** (simplest, no frontend type changes needed). Detail endpoint gets try/except -> 500 as safety net.
