# Testing Results

## Summary
**Status:** failed
10 existing tests regress because `tests/ui/conftest.py` `_make_app()` and several `create_app()` call sites in `test_runs.py` do not set `default_model`, causing the new `trigger_run` model guard (Step 2) to return HTTP 422 where tests expect 202. The implementation logic in `app.py` and `runs.py` is correct; the test fixtures need updating to supply a non-None model.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| n/a | Existing pytest suite | `tests/` |

### Test Execution
**Pass Rate:** 942/952 tests (6 skipped, 10 failed)
```
ssssss...........................................................................
...........................................................................
(truncated -- all non-trigger tests pass)
============================== FAILURES ===========================
FAILED tests/ui/test_integration.py::TestE2ETriggerWebSocket::test_trigger_then_ws_receives_pipeline_started
FAILED tests/ui/test_integration.py::TestE2ETriggerWebSocket::test_trigger_then_ws_receives_pipeline_completed
FAILED tests/ui/test_integration.py::TestE2ETriggerWebSocket::test_trigger_ws_stream_complete_sent_on_finish
FAILED tests/ui/test_integration.py::TestTriggerRunErrorHandling::test_trigger_failing_pipeline_sets_status_failed
FAILED tests/ui/test_integration.py::TestTriggerRunErrorHandling::test_trigger_failing_pipeline_sets_completed_at
FAILED tests/ui/test_integration.py::TestTriggerRunErrorHandling::test_trigger_failing_pipeline_completed_at_is_datetime
FAILED tests/ui/test_runs.py::TestTriggerRun::test_returns_202_with_run_id_and_accepted
FAILED tests/ui/test_runs.py::TestTriggerRun::test_run_id_is_valid_uuid
FAILED tests/ui/test_runs.py::TestTriggerRun::test_background_task_executes_pipeline
FAILED tests/ui/test_runs.py::TestTriggerRun::test_input_data_threaded_to_factory_and_execute
10 failed, 942 passed, 6 skipped, 1 warning in 107.39s
```

### Failed Tests
#### tests/ui/test_runs.py::TestTriggerRun (4 tests)
**Step:** 2 (model None guard in trigger_run)
**Error:** `assert 422 == 202` -- `create_app()` called without `default_model` arg; `app.state.default_model` is `None`; guard fires before pipeline executes.

Root cause: `_make_client_with_registry()` calls `create_app(db_path=":memory:", pipeline_registry=registry)` with no `default_model`.

#### tests/ui/test_integration.py::TestE2ETriggerWebSocket (3 tests)
**Step:** 2 (model None guard in trigger_run)
**Error:** `assert 422 == 202` -- `_make_app()` in conftest.py builds app manually, never sets `app.state.default_model`; guard fires.

Root cause: `_make_app()` sets `app.state.pipeline_registry = {}` but omits `app.state.default_model`.

#### tests/ui/test_integration.py::TestTriggerRunErrorHandling (3 tests)
**Step:** 2 (model None guard in trigger_run)
**Error:** `assert 422 == 202` and `KeyError: 'run_id'` -- same root cause as above; 422 is returned before run_id is generated.

## Build Verification
- [x] `python -c "from llm_pipeline.ui.app import create_app"` -- imports cleanly, no errors
- [x] `python -c "from llm_pipeline.ui.routes.runs import router"` -- imports cleanly
- [x] Syntax check: no SyntaxError in `app.py` or `runs.py`
- [x] Type annotations: `Callable`, `Tuple`, `Optional`, `Type` all imported correctly
- [x] `importlib.metadata`, `inspect`, `logging`, `os` all standard-library imports -- no missing deps

## Success Criteria (from PLAN.md)
- [x] `create_app()` accepts `auto_discover=True` and `default_model=None` without breaking existing call sites -- new params have defaults; no positional signature change
- [ ] Entry points in group `llm_pipeline.pipelines` are loaded and registered -- logic present and correct in `_discover_pipelines()`; no entry points registered in this repo yet so cannot verify runtime registration (no regression)
- [x] Explicit `pipeline_registry` / `introspection_registry` params override auto-discovered entries -- merge order `{**discovered, **(explicit or {})}` confirmed in code
- [x] `seed_prompts(engine)` called on classes that have it; failure logs warning but does not unregister -- separate try/except block confirmed in code
- [x] Load errors logged as `logger.warning`, not raised; app starts normally with zero entry points -- confirmed in `_discover_pipelines` except block
- [x] Startup warning logged when `default_model` is None and `LLM_PIPELINE_MODEL` not set -- log output confirmed in failed test captured log: `WARNING llm_pipeline.ui.app:app.py:169 No default model configured...`
- [ ] `trigger_run` returns HTTP 422 with actionable message when `default_model` is None -- CRITERION MET by implementation, but 10 existing tests now regress because their fixtures do not set a model
- [x] `auto_discover=False` disables discovery; registries fall back to explicit params only -- else branch confirmed in code

## Human Validation Required
### Manual trigger with no model configured
**Step:** 2
**Instructions:** Start server without `LLM_PIPELINE_MODEL` env var and without `--model` flag. POST to `/api/runs` with a valid pipeline name.
**Expected Result:** HTTP 422 response with body `{"detail": "No model configured. Set LLM_PIPELINE_MODEL env var or pass --model flag."}`

### Entry point discovery
**Step:** 1
**Instructions:** Install a package that declares `llm_pipeline.pipelines` entry point pointing to a `PipelineConfig` subclass. Start the app. Check startup logs.
**Expected Result:** `INFO llm_pipeline.ui.app Discovered 1 pipeline(s): <name>` log line; pipeline appears in `/api/pipelines` response.

## Issues Found
### Test fixture regression: conftest _make_app() missing default_model
**Severity:** high
**Step:** 2
**Details:** `tests/ui/conftest.py` `_make_app()` builds app manually and never sets `app.state.default_model`. All trigger tests that use this helper (TestE2ETriggerWebSocket, TestTriggerRunErrorHandling) now get 422 instead of 202.

Fix: add `app.state.default_model = "test-model"` to `_make_app()` in `tests/ui/conftest.py`.

### Test fixture regression: TestTriggerRun._make_client_with_registry missing default_model
**Severity:** high
**Step:** 2
**Details:** `tests/ui/test_runs.py` `_make_client_with_registry()` calls `create_app(db_path=":memory:", pipeline_registry=registry)` without `default_model`. The 4 trigger tests in `TestTriggerRun` get 422 instead of 202.

Fix: add `default_model="test-model"` to the `create_app()` call in `_make_client_with_registry()`, and to the inline `create_app()` calls in `test_run_id_is_valid_uuid`, `test_background_task_executes_pipeline`, `test_input_data_threaded_to_factory_and_execute`.

## Recommendations
1. Fix both test fixtures (conftest.py and test_runs.py) to supply a non-None `default_model` (any sentinel string like `"test-model"` suffices since tests use fake pipelines that never call pydantic-ai).
2. After fixing fixtures, re-run `pytest` to confirm 952/952 pass.
3. Consider whether `test_returns_404_when_registry_empty` (currently passing, expects 404) could race with the 422 guard -- it does not set a model either, but the 404 guard fires first (pipeline not found before model check), so it still passes. Verify this ordering is intentional and document in `trigger_run` docstring.

---

## Re-run After Fixture Fixes

## Summary
**Status:** passed
All 10 regressions resolved. 952 passed, 6 skipped, 1 warning. Fixes confirmed working.

## Automated Testing
### Test Execution
**Pass Rate:** 952/952 tests (6 skipped)
```
ssssss.................................................................................
(all tests pass -- full output truncated)
============================== warnings summary ===============================
tests\test_pipeline.py:114
  PytestCollectionWarning: cannot collect test class 'TestPipeline' because it has a __init__ constructor

952 passed, 6 skipped, 1 warning in 119.74s (0:01:59)
```

### Failed Tests
None

## Success Criteria (from PLAN.md)
- [x] `create_app()` accepts `auto_discover=True` and `default_model=None` without breaking existing call sites
- [ ] Entry points in group `llm_pipeline.pipelines` are loaded and registered -- no entry points in this repo; logic verified by code review only
- [x] Explicit `pipeline_registry` / `introspection_registry` params override auto-discovered entries
- [x] `seed_prompts(engine)` failure logs warning but does not unregister
- [x] Load errors logged as `logger.warning`, not raised
- [x] Startup warning logged when `default_model` is None and `LLM_PIPELINE_MODEL` not set
- [x] `trigger_run` returns HTTP 422 with actionable message when `default_model` is None -- test_returns_404_when_registry_empty passes (404 guard fires first as expected)
- [x] `auto_discover=False` disables discovery; registries fall back to explicit params only

## Issues Found
None

---

## Re-run After Review Fix (new test added)

## Summary
**Status:** passed
New test `test_returns_422_when_no_model_configured` passes. 953 passed, 6 skipped, 1 warning. Full suite clean.

## Automated Testing
### Test Execution
**Pass Rate:** 953/953 tests (6 skipped)
```
ssssss.................................................................................
(all tests pass)
============================== warnings summary ===============================
tests\test_pipeline.py:114
  PytestCollectionWarning: cannot collect test class 'TestPipeline' because it has a __init__ constructor

953 passed, 6 skipped, 1 warning in 121.09s (0:02:01)
```

### Failed Tests
None

## Issues Found
None
