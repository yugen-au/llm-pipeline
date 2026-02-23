# Testing Results

## Summary
**Status:** passed
Full test suite ran: 765/766 tests passed. 1 pre-existing failure in `tests/test_ui.py` (unrelated to pipelines implementation -- confirmed by verifying it fails identically with all new code stashed). All 19 new pipeline endpoint tests pass. No regressions in prompts or introspection tests.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| test_pipelines.py | Pipeline endpoint tests (list + detail) | tests/ui/test_pipelines.py |

### Test Execution
**Pass Rate:** 765/766 tests (19/19 pipeline tests)
```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2, pluggy-1.6.0
collected 766 items

tests/ui/test_pipelines.py::TestListPipelines::test_list_empty_registry_returns_200_empty_list PASSED
tests/ui/test_pipelines.py::TestListPipelines::test_list_populated_returns_all_pipelines_alphabetically PASSED
tests/ui/test_pipelines.py::TestListPipelines::test_list_all_count_fields_non_null_for_valid_pipeline PASSED
tests/ui/test_pipelines.py::TestListPipelines::test_list_item_has_expected_fields PASSED
tests/ui/test_pipelines.py::TestListPipelines::test_list_no_error_flag_for_valid_pipelines PASSED
tests/ui/test_pipelines.py::TestListPipelines::test_list_errored_pipeline_included_with_error_flag PASSED
tests/ui/test_pipelines.py::TestListPipelines::test_list_mixed_valid_and_errored_pipelines PASSED
tests/ui/test_pipelines.py::TestListPipelines::test_list_no_introspection_registry_returns_empty PASSED
tests/ui/test_pipelines.py::TestListPipelines::test_list_has_input_schema_true_for_pipeline_with_instructions PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_unknown_name_returns_404 PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_404_detail_message_contains_name PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_known_pipeline_returns_200 PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_known_pipeline_returns_metadata PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_pipeline_name_matches_introspector PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_response_shape_matches_introspector_output PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_strategies_list_non_empty PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_strategy_has_required_fields PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_execution_order_is_list_of_strings PASSED
tests/ui/test_pipelines.py::TestGetPipeline::test_detail_registry_models_is_list PASSED

============ 1 failed, 765 passed, 3 warnings in 120.14s ======================
```

### Failed Tests
#### TestRoutersIncluded::test_events_router_prefix
**Step:** pre-existing (not from this task)
**Error:** `AssertionError: assert '/runs/{run_id}/events' == '/events'` -- test_ui.py line 143 expects events router prefix `/events` but actual prefix is `/runs/{run_id}/events`. Confirmed pre-existing: test fails identically with all new code stashed.

## Build Verification
- [x] Import check: `from llm_pipeline.ui.routes.pipelines import router, PipelineListItem, PipelineListResponse, PipelineMetadata` resolves without error
- [x] No syntax errors in new files
- [x] No import errors in test collection (766 items collected cleanly)
- [x] app.py unchanged (router already wired at prefix /api)
- [x] Two DeprecationWarnings from fastapi internals (`HTTP_422_UNPROCESSABLE_ENTITY`) -- pre-existing, not introduced by this task
- [x] One PytestCollectionWarning for TestPipeline class in test_pipeline.py -- pre-existing

## Success Criteria (from PLAN.md)
- [x] `GET /api/pipelines` returns 200 with `{ "pipelines": [] }` for empty registry -- verified by `test_list_empty_registry_returns_200_empty_list`
- [x] `GET /api/pipelines` returns 200 with `{ "pipelines": [...] }` for populated registry -- verified by `test_list_populated_returns_all_pipelines_alphabetically`
- [x] List items include: `name`, `strategy_count`, `step_count`, `has_input_schema`, `registry_model_count`, `error` -- verified by `test_list_item_has_expected_fields`
- [x] Pipelines sorted alphabetically by name -- verified by `test_list_populated_returns_all_pipelines_alphabetically`
- [x] Failed pipeline introspection: error non-null, counts null, request still 200 -- verified by `test_list_errored_pipeline_included_with_error_flag`
- [x] `GET /api/pipelines/{name}` returns 200 with full introspector metadata -- verified by `test_detail_known_pipeline_returns_metadata` and `test_detail_response_shape_matches_introspector_output`
- [x] `GET /api/pipelines/{name}` returns 404 for unregistered name -- verified by `test_detail_unknown_name_returns_404`
- [x] `GET /api/pipelines/{name}` 404 detail message contains the name -- verified by `test_detail_404_detail_message_contains_name`
- [x] No changes to `llm_pipeline/ui/app.py` -- confirmed by git diff (only pipelines.py modified in implementation)
- [x] All pipeline tests pass with pytest (19/19)
- [x] No new warnings or linting issues introduced by new files

## Human Validation Required
### GET /api/pipelines live endpoint
**Step:** Step 1 (implement endpoints)
**Instructions:** Start UI server (`uv run llm-pipeline-ui` or equivalent), navigate to `GET /api/pipelines` in browser or curl. Register a real pipeline in the app.
**Expected Result:** JSON with `pipelines` key containing list of pipeline objects with `name`, `strategy_count`, `step_count`, `has_input_schema`, `registry_model_count`, `error` fields; alphabetically sorted.

### GET /api/pipelines/{name} live endpoint
**Step:** Step 1 (implement endpoints)
**Instructions:** With server running and pipeline registered, call `GET /api/pipelines/{name}` for a known pipeline name.
**Expected Result:** 200 with full introspection metadata including `pipeline_name`, `strategies`, `execution_order`, `registry_models`.

## Issues Found
### Pre-existing test failure: test_events_router_prefix
**Severity:** low
**Step:** not from this task (pre-existing)
**Details:** `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` expects events router prefix `/events` but actual is `/runs/{run_id}/events`. Stash verification confirms this failure exists before any changes from task 24. Not introduced by pipelines implementation.

## Recommendations
1. Fix `test_events_router_prefix` in a separate task -- the test assertion does not match the actual events router prefix set in `llm_pipeline/ui/routes/events.py`.
2. No action required for this task -- all 19 new tests pass, no regressions introduced.
