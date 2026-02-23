# Research Summary

## Executive Summary

Validated 3 research documents against actual source code (app.py, pipelines.py, deps.py, introspection.py, conftest.py, frontend types.ts, pipelines.ts, test_introspection.py). Core architecture findings are consistent: empty router exists and is wired, introspection_registry on app.state is typed and ready, PipelineIntrospector is pure class-level with caching. Three contradictions between research docs were identified and resolved via CEO decisions (see Q&A History). All open items now resolved -- ready for planning.

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
| List response wrapper key: `{ pipelines: [...] }` (frontend) vs `{ items: [...], total }` (step-3)? | Use `{ pipelines: [...] }` -- match existing frontend contract, no pagination/total. | Step-3 proposal overruled. Backend returns `{ "pipelines": [...] }` key. No total/offset/limit fields. This diverges from paginated endpoints (runs, prompts, events) intentionally since pipeline data is static config. |
| PipelineListItem fields: keep `has_input_schema` (frontend) or replace with `registry_model_count` (step-3)? | Include BOTH. Boolean is cheap and already in frontend types. Count adds useful detail. | Frontend PipelineListItem type needs `registry_model_count: number` added. Backend returns: `name`, `strategy_count`, `step_count`, `has_input_schema`, `registry_model_count`. |
| List error handling: skip failed pipelines, include with error flag, or 500? | Include with error flag. Skip = hidden data loss (bad). 500 = single point of failure (worst). Error flag = explicit, no hidden failures (best). | Backend: try/except per pipeline. Failed pipeline gets name + error string + null counts. Log warning server-side. Frontend PipelineListItem type needs optional `error: string \| null` field added. |

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
- [x] List response uses `{ pipelines: [...] }` wrapper key (not `items`) -- CEO decision, matches frontend usePipelines() contract
- [x] PipelineListItem includes both has_input_schema and registry_model_count -- CEO decision
- [x] has_input_schema = any step has non-null instructions_schema -- derived from step 1 research + introspector source (instructions_schema comes from step_definition(instructions=Class))
- [x] Failed pipelines included in list with error flag + null counts -- CEO decision (explicit > silent skip > fail-all)
- [x] Frontend PipelineListItem type needs registry_model_count + error fields added -- task 40 scope, backend returns them from task 24

## Open Items
- ~~CRITICAL: List response shape~~ -- RESOLVED: use `{ pipelines: [...] }` key (CEO decision)
- ~~CRITICAL: PipelineListItem fields~~ -- RESOLVED: include both `has_input_schema` and `registry_model_count` (CEO decision)
- ~~MEDIUM: has_input_schema semantics~~ -- RESOLVED: derived as `any step across any strategy has non-null instructions_schema` (step 1 research definition, confirmed by introspector source -- `instructions_schema` is the Pydantic JSON schema for the LLM result type, set via `step_definition(instructions=SomeInstructionsClass)`)
- ~~MEDIUM: List error handling~~ -- RESOLVED: include failed pipelines with error flag + null counts, log warning (CEO decision)
- **NOTE: Frontend type updates needed** -- PipelineListItem in types.ts needs: add `registry_model_count: number`, add `error: string | null`. These are task 40 scope (frontend) but backend must return them from task 24.
- **NOTE: Cache clearing in endpoint tests** -- pipeline endpoint tests need `PipelineIntrospector._cache.clear()` fixture (mirror test_introspection.py pattern)
- **NOTE: Alphabetical sort** -- list endpoint should sort by name for deterministic output (explicit `sorted()` call since dict insertion order != alphabetical)

## Recommendations for Planning

### Confirmed Decisions (CEO-approved)
1. **List response shape**: `{ "pipelines": [PipelineListItem, ...] }` -- no total/offset/limit. Matches existing frontend `usePipelines()` contract.
2. **PipelineListItem fields**: `name: str`, `strategy_count: int`, `step_count: int`, `has_input_schema: bool`, `registry_model_count: int`, `error: Optional[str]`. Backend Pydantic model must include all six fields.
3. **has_input_schema derivation**: `True` if any step across any strategy has non-null `instructions_schema` in introspector output. For errored pipelines: `False`.
4. **Error handling (list)**: try/except per pipeline. On failure: include `PipelineListItem(name=name, strategy_count=None, step_count=None, has_input_schema=False, registry_model_count=None, error=str(exc))`. Log `logger.warning(...)` server-side.
5. **Error handling (detail)**: 404 if name not in registry. try/except around `get_metadata()` -> 500 with detail string (safety net; introspector is already defensive).

### Implementation Patterns
6. **Strictly typed Pydantic models (Option A)** for detail response -- consistent with codebase convention, enables OpenAPI docs, frontend types already mirror introspector output.
7. **Sync def, no DBSession** -- follow non-DB access pattern from trigger_run: `request.app.state.introspection_registry` via `Request` param.
8. **Alphabetical sort** on list endpoint -- `sorted(registry.items(), key=lambda x: x[0])` for deterministic output.

### Testing
9. **Create dedicated test fixture** in new `tests/ui/test_pipelines.py` that builds app with introspection_registry populated. Import test pipeline classes from test_introspection.py (WidgetPipeline, ScanPipeline, GadgetPipeline).
10. **Include cache-clearing fixture** -- autouse fixture calling `PipelineIntrospector._cache.clear()` (mirror test_introspection.py).
11. **No conftest.py changes** -- use per-file fixture pattern (like test_prompts.py) to keep existing test infrastructure stable.
12. **Test cases**: empty registry (200, empty list), populated registry, 404 on unknown name, error pipeline in list (verify error field populated + counts null), detail for valid pipeline, detail for errored pipeline class (verify 500 or defensive dict).

### Downstream Impact
13. **Frontend type updates (task 40 scope)**: PipelineListItem in types.ts needs `registry_model_count: number` and `error: string | null` added. Backend ships these fields now; frontend adopts them in task 40.
14. **Detail response matches PipelineMetadata type exactly** -- no frontend type changes needed for detail endpoint.
