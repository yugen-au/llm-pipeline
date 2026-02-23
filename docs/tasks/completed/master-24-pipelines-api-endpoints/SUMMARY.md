# Task Summary

## Work Completed

Implemented two REST endpoints for pipeline introspection in the llm-pipeline UI layer. The router shell and app.py wiring were pre-existing; only endpoint logic, Pydantic response models, and tests were added.

- `GET /api/pipelines` - lists all pipelines registered in `app.state.introspection_registry`, returns summary metadata per pipeline with per-pipeline error handling so a single broken pipeline does not fail the whole request
- `GET /api/pipelines/{name}` - returns full `PipelineIntrospector.get_metadata()` output for a named pipeline; 404 if not registered, 500 if introspection raises unexpectedly
- 6 Pydantic response models added to `pipelines.py`: `PipelineListItem`, `PipelineListResponse`, `StepMetadata`, `StrategyMetadata`, `PipelineMetadata`
- 20 tests covering empty registry, populated registry, alphabetical sort, error flag, 404, 500, and full shape verification
- Review loop: removed unused `Dict` import, removed dead fixture, added missing 500 path test; second review approved clean

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `tests/ui/test_pipelines.py` | 20 tests for GET /api/pipelines and GET /api/pipelines/{name} |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/ui/routes/pipelines.py` | Replaced empty router shell with full endpoint implementation: 6 Pydantic models, 2 endpoint functions, imports |

## Commits Made

| Hash | Message |
| --- | --- |
| `0a168f3` | docs(implementation-A): master-24-pipelines-api-endpoints |
| `b010950` | docs(implementation-B): master-24-pipelines-api-endpoints |
| `8ec1383` | docs(fixing-review-A): master-24-pipelines-api-endpoints |
| `2a7c7e7` | docs(fixing-review-B): master-24-pipelines-api-endpoints |

Note: additional `chore(state)` commits exist for phase transitions; omitted above as they carry no code changes.

## Deviations from Plan

- The `introspection_client(pipeline_cls_map)` fixture called for in PLAN.md Step 2 was initially created but then removed in the review fix loop. Review identified it as a dead fixture (undefined `pipeline_cls_map` dependency, never used by any test). Removed rather than wired up, since `empty_introspection_client` and `populated_introspection_client` cover all test needs.
- Initial test count was 19 (not the 7 test cases listed in PLAN.md Step 2). Extra tests were added for additional field-level assertions (error flag absence, has_input_schema derivation, 404 detail message content, strategy/step field verification). A 20th test was added in the review fix loop for the detail 500 path.

## Issues Encountered

### PipelineIntrospector does not raise for broken input classes
**Resolution:** PLAN.md Step 2 suggested passing a plain class (no STRATEGIES) to trigger the list endpoint's except branch. In practice, `PipelineIntrospector` handles all input gracefully -- a class with no STRATEGIES returns empty metadata rather than raising. To test the except branch, `unittest.mock.patch.object(PipelineIntrospector, "get_metadata", side_effect=RuntimeError(...))` was used instead. Same technique applied for the detail 500 test.

### Detail endpoint 500 path not covered after initial implementation
**Resolution:** Identified during architecture review as a medium severity gap. Added `test_detail_introspection_failure_returns_500` in the fix-review iteration, using `patch.object` with `side_effect=Exception("boom")` and asserting status 500 and error message in detail field.

### Pre-existing test failure in test_ui.py
**Resolution:** `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` fails because the test expects prefix `/events` but the actual events router prefix is `/runs/{run_id}/events`. Confirmed pre-existing by stash verification. Not caused by or related to task 24 changes. No action taken; documented in TESTING.md.

## Success Criteria

- [x] `GET /api/pipelines` returns 200 with `{ "pipelines": [] }` for empty registry -- verified by `test_list_empty_registry_returns_200_empty_list`
- [x] `GET /api/pipelines` returns 200 with `{ "pipelines": [...] }` for populated registry -- verified by `test_list_populated_returns_all_pipelines_alphabetically`
- [x] List items include: `name`, `strategy_count`, `step_count`, `has_input_schema`, `registry_model_count`, `error` -- verified by `test_list_item_has_expected_fields`
- [x] Pipelines sorted alphabetically by name -- verified by `test_list_populated_returns_all_pipelines_alphabetically`
- [x] Failed pipeline introspection: error non-null, counts null, request still 200 -- verified by `test_list_errored_pipeline_included_with_error_flag` and `test_list_mixed_valid_and_errored_pipelines`
- [x] `GET /api/pipelines/{name}` returns 200 with full introspector metadata -- verified by `test_detail_known_pipeline_returns_metadata` and `test_detail_response_shape_matches_introspector_output`
- [x] `GET /api/pipelines/{name}` returns 404 for unregistered name -- verified by `test_detail_unknown_name_returns_404`
- [x] `GET /api/pipelines/{name}` returns 500 if introspection raises -- verified by `test_detail_introspection_failure_returns_500`
- [x] No changes to `llm_pipeline/ui/app.py` -- confirmed by git diff
- [x] All 20 pipeline tests pass with pytest
- [x] No new warnings or linting issues introduced

## Recommendations for Follow-up

1. Fix `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` in a separate task -- assertion expects `/events` but actual events router prefix is `/runs/{run_id}/events`. Either update the test or verify whether the prefix change was intentional.
2. Add live endpoint validation to CI or a smoke test suite -- TESTING.md documents manual validation steps for `GET /api/pipelines` and `GET /api/pipelines/{name}` with a real registered pipeline; automating this would prevent regressions when registry population logic changes.
3. Consider adding `description` or `display_name` to `PipelineListItem` if the UI needs human-readable pipeline labels -- the introspector already exposes `display_name` per strategy; a pipeline-level display name would require a convention in `PipelineConfig`.
4. The `has_input_schema` derivation (True if any step across any strategy has non-null `instructions_schema`) is implicit. If pipelines begin supporting per-strategy schema toggling, a dedicated field on `PipelineConfig` would be cleaner than traversing introspector output.
