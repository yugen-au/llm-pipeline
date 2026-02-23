# PLANNING

## Summary
Implement two REST endpoints in `llm_pipeline/ui/routes/pipelines.py`: `GET /api/pipelines` (list all registered pipelines with summary fields) and `GET /api/pipelines/{name}` (full introspection detail via PipelineIntrospector). The router shell and app.py wiring already exist; only endpoint logic, Pydantic models, and tests need to be added.

## Plugin & Agents
**Plugin:** backend-development
**Subagents:** backend-development:backend-architect, backend-development:test-automator
**Skills:** none

## Phases
1. Implement endpoints - add Pydantic response models and endpoint functions to pipelines.py
2. Tests - create tests/ui/test_pipelines.py with dedicated fixtures and test cases

## Architecture Decisions

### Response shape for list endpoint
**Choice:** `{ "pipelines": [...] }` wrapper key, no pagination fields (total/offset/limit)
**Rationale:** Matches existing frontend `usePipelines()` contract exactly. Pipeline config is static (bounded, not DB rows), so pagination is unnecessary. CEO-approved decision.
**Alternatives:** Paginated `{ items, total, offset, limit }` (runs pattern) -- rejected as frontend expects `pipelines` key and no pagination.

### PipelineListItem fields
**Choice:** Six fields: `name: str`, `strategy_count: Optional[int]`, `step_count: Optional[int]`, `has_input_schema: bool`, `registry_model_count: Optional[int]`, `error: Optional[str]`
**Rationale:** CEO decision -- include both `has_input_schema` (existing frontend type) and count fields (richer detail). Error field enables graceful per-pipeline failure without hiding data loss or failing entire request.
**Alternatives:** Only counts (step-3 proposal) or only has_input_schema (frontend baseline) -- both rejected.

### Error handling strategy
**Choice:** try/except per pipeline in list; null counts + error string for failed pipelines. Detail endpoint: 404 if not in registry, 500 if introspection raises unexpectedly.
**Rationale:** CEO decision -- explicit error flag beats silent skip (hidden data loss) and beats 500 (single point of failure). PipelineIntrospector is already defensive for broken strategies; 500 on detail is a safety net only.
**Alternatives:** Skip failed pipelines silently; fail entire list request with 500.

### has_input_schema derivation
**Choice:** `True` if any step across any strategy has non-null `instructions_schema` in introspector output.
**Rationale:** `instructions_schema` is the Pydantic JSON schema set via `step_definition(instructions=SomeClass)`. Presence indicates the pipeline accepts structured LLM input. For errored pipelines: hardcoded `False`.
**Alternatives:** Check only default strategy steps -- rejected as too narrow.

### Test fixture isolation
**Choice:** New per-file fixtures in `tests/ui/test_pipelines.py`; reuse `_make_app()` from conftest.py with `introspection_registry` set on `app.state` post-construction. No conftest.py changes.
**Rationale:** Matches test_prompts.py pattern (per-file fixture). Avoids polluting shared conftest. Existing _make_app() does not set introspection_registry, so tests set it directly on app.state.
**Alternatives:** Modify _make_app() to accept introspection_registry param -- rejected to keep shared infrastructure stable.

### Alphabetical sort on list
**Choice:** Sort by name: `sorted(registry.items(), key=lambda x: x[0])`
**Rationale:** Dict insertion order is non-deterministic across Python versions and registry population order. Deterministic output is required for reliable tests and consistent UI.
**Alternatives:** Unsorted (insertion order) -- rejected.

## Implementation Steps

### Step 1: Implement endpoints in pipelines.py
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /websites/fastapi_tiangolo
**Group:** A

1. Add imports: `logging`, `Any`, `Dict`, `List`, `Optional`, `Type`, `Request`, `HTTPException`, `BaseModel`, `PipelineIntrospector`
2. Define `PipelineListItem(BaseModel)` with fields: `name: str`, `strategy_count: Optional[int] = None`, `step_count: Optional[int] = None`, `has_input_schema: bool = False`, `registry_model_count: Optional[int] = None`, `error: Optional[str] = None`
3. Define `PipelineListResponse(BaseModel)` with field: `pipelines: List[PipelineListItem]`
4. Define detail response Pydantic models mirroring introspector output shape: `StepMetadata`, `StrategyMetadata`, `PipelineMetadata` -- use `Any` for nested dict fields (instructions_schema, context_schema, extractions, transformation) to avoid tight coupling to introspector internals
5. Implement `GET ""` endpoint `list_pipelines(request: Request) -> PipelineListResponse`:
   - Fetch registry: `registry: dict = getattr(request.app.state, "introspection_registry", {})`
   - Iterate `sorted(registry.items(), key=lambda x: x[0])`
   - For each `(name, pipeline_cls)`: try/except block calling `PipelineIntrospector(pipeline_cls).get_metadata()`
   - On success: derive `strategy_count`, `step_count` (sum of steps across all strategies), `registry_model_count`, `has_input_schema` from metadata dict
   - On exception: append item with `name=name`, all counts `None`, `has_input_schema=False`, `error=str(exc)`. Log `logger.warning(...)`.
   - Return `PipelineListResponse(pipelines=[...])`
6. Implement `GET "/{name}"` endpoint `get_pipeline(name: str, request: Request) -> PipelineMetadata`:
   - Fetch registry; if name not in registry raise `HTTPException(status_code=404, detail=f"Pipeline '{name}' not found")`
   - Call `PipelineIntrospector(pipeline_cls).get_metadata()` in try/except
   - On exception: raise `HTTPException(status_code=500, detail=str(exc))`
   - Return `PipelineMetadata(**metadata)` (or construct explicitly)

### Step 2: Add tests for pipeline endpoints
**Agent:** backend-development:test-automator
**Skills:** none
**Context7 Docs:** /websites/fastapi_tiangolo
**Group:** B

1. Create `tests/ui/test_pipelines.py`
2. Import `_make_app` from `tests.ui.conftest`, import `PipelineIntrospector` from `llm_pipeline.introspection`, import pipeline test classes from `tests.test_introspection` (WidgetPipeline or equivalent -- check which complete pipeline classes exist in that file; fall back to defining minimal inline pipeline if none are module-level)
3. Add autouse fixture `clear_introspector_cache` calling `PipelineIntrospector._cache.clear()` (mirror test_introspection.py pattern)
4. Add fixture `introspection_client(pipeline_cls_map)` that calls `_make_app()`, sets `app.state.introspection_registry = pipeline_cls_map`, returns `TestClient(app)`
5. Add fixture `empty_introspection_client` -- registry `{}`
6. Add fixture `populated_introspection_client` -- registry with 2+ test pipeline classes (use classes from test_introspection.py if available as module-level symbols, else define minimal inline)
7. Test cases for `GET /api/pipelines`:
   - `test_list_empty_registry_returns_200_empty_list`: 200, `{ "pipelines": [] }`
   - `test_list_populated_returns_all_pipelines_alphabetically`: verify names sorted, all count fields present and non-null
   - `test_list_item_has_expected_fields`: check each field key in response items
   - `test_list_errored_pipeline_included_with_error_flag`: register a broken class (e.g., class without proper strategies), verify item present with `error` not null and counts null
8. Test cases for `GET /api/pipelines/{name}`:
   - `test_detail_unknown_name_returns_404`: status 404
   - `test_detail_known_pipeline_returns_metadata`: 200, response contains `pipeline_name`, `strategies`, `execution_order`, `registry_models`
   - `test_detail_response_shape_matches_introspector_output`: spot-check key fields match `PipelineIntrospector(cls).get_metadata()` output directly

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| No complete pipeline class available at module level in test_introspection.py | Medium | Check file for WidgetPipeline/ScanPipeline/GadgetPipeline module-level definitions; if missing, define a minimal inline pipeline in test_pipelines.py |
| `has_input_schema` derivation logic is complex (nested list traversal) | Low | Unit test the derivation by registering a step with and without `instructions_schema`, verify boolean flips |
| Introspector detail models too strict (breaking if introspector output shape changes) | Low | Use `Any` / `Dict[str, Any]` for nested schema fields in Pydantic detail models rather than deeply nested typed models |
| Cache not cleared between tests causes cross-test contamination | Medium | Autouse `clear_introspector_cache` fixture (mirrors test_introspection.py) |
| Broken strategy class crashes list request silently | Low | try/except per pipeline with explicit `logger.warning`; test case verifies error flag populated |

## Success Criteria
- [ ] `GET /api/pipelines` returns 200 with `{ "pipelines": [...] }` for empty and populated registries
- [ ] List items include: `name`, `strategy_count`, `step_count`, `has_input_schema`, `registry_model_count`, `error`
- [ ] Pipelines sorted alphabetically by name in list response
- [ ] Failed pipeline introspection results in list item with `error` non-null and counts null; request still returns 200
- [ ] `GET /api/pipelines/{name}` returns 200 with full introspector metadata for registered pipeline
- [ ] `GET /api/pipelines/{name}` returns 404 for unregistered name
- [ ] `GET /api/pipelines/{name}` returns 500 if introspection raises unexpectedly
- [ ] No changes required to `llm_pipeline/ui/app.py` (router already wired)
- [ ] All tests pass with `pytest`
- [ ] No warnings or linting issues in new files

## Phase Recommendation
**Risk Level:** low
**Reasoning:** All architectural decisions are CEO-approved with no ambiguity. The router is already wired, PipelineIntrospector is proven by 43 tests, and the pattern (sync endpoints, Pydantic models, Request for app.state) is well-established in the codebase. The only complexity is the has_input_schema derivation and per-pipeline error handling, both of which are straightforward list traversals.
**Suggested Exclusions:** testing, review
