# Task Summary

## Work Completed

Implemented core pipeline auto-discovery and registration in `create_app()`. The app factory now scans the `llm_pipeline.pipelines` entry point group via `importlib.metadata` at startup, validates each loaded class as a `PipelineConfig` subclass, builds factory closures capturing the resolved model, and merges discovered entries into both `pipeline_registry` and `introspection_registry` with explicit overrides winning. Added a startup warning when no model is configured and an HTTP 422 guard in `trigger_run` that blocks execution when `default_model` is None. Fixed test fixtures that lacked `default_model` and added a new test covering the 422 path.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| None | No new source files created |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/ui/app.py` | Added `importlib.metadata`, `inspect`, `logging`, `os`, `Callable`, `Tuple` imports. Added module-level `logger`. Added `_make_pipeline_factory(cls, model)` private helper that returns a factory closure. Added `_discover_pipelines(engine, default_model)` private helper that scans entry points, validates classes, builds factories, calls `seed_prompts` in an isolated try/except, and returns both registry dicts. Extended `create_app()` with `auto_discover: bool = True` and `default_model: Optional[str] = None` params. Added model resolution (`param > env > None`) with startup warning. Added `app.state.default_model`. Added discovery merge block: `{**discovered, **(explicit or {})}` for both registries. |
| `llm_pipeline/ui/routes/runs.py` | Added model None guard in `trigger_run` after factory lookup (404 fires first) and before `run_id` generation. Returns HTTP 422 with detail message referencing `LLM_PIPELINE_MODEL` env var and `--model` flag when `app.state.default_model` is None. Uses `getattr` for defensive backward-compatible access. |
| `tests/ui/conftest.py` | Added `app.state.default_model = "test-model"` to `_make_app()` fixture so trigger-path tests receive 202 instead of 422. |
| `tests/ui/test_runs.py` | Added `default_model="test-model"` to all `create_app()` calls in `TestTriggerRun` (`_make_client_with_registry`, `test_run_id_is_valid_uuid`, `test_background_task_executes_pipeline`, `test_input_data_threaded_to_factory_and_execute`). Added new test `test_returns_422_when_no_model_configured` to `TestTriggerRun` verifying 422 status and message content when `default_model=None`. |

## Commits Made

| Hash | Message |
| --- | --- |
| `abdc09dd` | `docs(implementation-A): pipeline-discovery-1-auto-discovery` |
| `8efb8af8` | `docs(implementation-B): pipeline-discovery-1-auto-discovery` |
| `89bea6af` | `docs(fixing-tests-B): pipeline-discovery-1-auto-discovery` |
| `f7727652` | `docs(fixing-review-B): pipeline-discovery-1-auto-discovery` |

## Deviations from Plan

- Factory closure accepts `**kwargs` in addition to the planned positional params. `trigger_run` passes `input_data=body.input_data` as a keyword arg to the factory (runs.py L223); `PipelineConfig.__init__` does not accept `input_data`. The `**kwargs` absorbs it cleanly without modifying the constructor. This was identified during research validation and incorporated before implementation began, so it is not strictly a post-plan deviation but it was not explicit in the original plan steps.
- Plan specified HTTP 400 for missing model at execution time; implementation uses HTTP 422. CEO decision from VALIDATED_RESEARCH Q&A resolved the ambiguity in favor of 422 (Unprocessable Entity) as the more semantically correct status for a configuration validation failure.

## Issues Encountered

### Test fixture regression: 10 tests returning 422 instead of 202

The new `trigger_run` model guard fires before any pipeline execution. The existing test fixtures in `tests/ui/conftest.py` (`_make_app`) and `tests/ui/test_runs.py` (`_make_client_with_registry` and three inline `create_app()` calls) did not pass `default_model`, leaving `app.state.default_model` as None. All trigger-path tests received 422 instead of 202.

**Resolution:** Added `app.state.default_model = "test-model"` to `_make_app()` in conftest.py. Added `default_model="test-model"` to the four `create_app()` calls in `TestTriggerRun` in test_runs.py. No production code changed. All 10 regressions resolved; 952 tests passed.

### Missing test coverage for 422 model guard path

Architecture review identified that no test exercised the 422 guard directly. The two existing 404 tests omit `default_model` but the 404 fires before the model guard, so the 422 path was never reached in the test suite. Without a test, the guard could be removed or broken silently.

**Resolution:** Added `test_returns_422_when_no_model_configured` to `TestTriggerRun`. The test creates an app with a registered pipeline but `default_model=None`, POSTs to trigger that pipeline, and asserts HTTP 422 with detail message containing "No model configured" and "LLM_PIPELINE_MODEL". Final test count: 953 passed, 6 skipped, 1 warning.

## Success Criteria

- [x] `create_app()` accepts `auto_discover=True` and `default_model=None` without breaking existing call sites -- all three CLI call sites (cli.py L46, L82, L109) use positional `db_path` only; new params with defaults are backward-compatible
- [ ] Entry points in group `llm_pipeline.pipelines` are loaded and registered in both `app.state.pipeline_registry` and `app.state.introspection_registry` under `ep.name` key -- logic present and verified by code review; no entry points declared in this repo yet (task 3 adds the first); runtime registration cannot be verified until task 3 is complete
- [x] Explicit `pipeline_registry` / `introspection_registry` params override auto-discovered entries -- merge order `{**discovered, **(explicit or {})}` confirmed; explicit always wins
- [x] `seed_prompts(engine)` called on classes that have it; failure logs warning but does not unregister the pipeline -- isolated try/except block confirmed; pipeline appended to reg dicts before seed attempt
- [x] Load errors logged as `logger.warning`, not raised; app starts normally with zero entry points on error -- broad `except Exception` in `_discover_pipelines` with `logger.warning`; verified by startup log output in test runs
- [x] Startup warning logged when `default_model` is None and `LLM_PIPELINE_MODEL` not set -- captured in test output: `WARNING llm_pipeline.ui.app:app.py No default model configured...`
- [x] `trigger_run` returns HTTP 422 with actionable message when `default_model` is None at call time -- covered by `test_returns_422_when_no_model_configured`; message references both `LLM_PIPELINE_MODEL` and `--model` flag
- [x] `auto_discover=False` disables discovery; registries fall back to explicit params only -- else branch confirmed in app.py

## Recommendations for Follow-up

1. **Task 3 (demo pipeline)**: Declare the first `llm_pipeline.pipelines` entry point in pyproject.toml pointing to the demo `PipelineConfig` subclass. This will exercise the discovery path end-to-end for the first time and validate runtime registration, `seed_prompts` execution, and INFO log output.
2. **PipelineIntrospector naming bug**: `PipelineIntrospector._pipeline_name` uses a single regex (`([a-z0-9])([A-Z])`) while `PipelineConfig.pipeline_name` uses `to_snake_case()` double-regex. These diverge on consecutive-caps names (e.g. "HTTPProxyPipeline"). The current workaround (using `ep.name` as registry key) avoids the mismatch, but the underlying bug should be fixed in a separate task before edge-case pipeline names are registered.
3. **conftest `_make_app` introspection_registry**: `_make_app()` in `tests/ui/conftest.py` sets `app.state.pipeline_registry` and `app.state.default_model` but not `app.state.introspection_registry`. The routes safely default via `getattr(..., {})`, so there is no runtime error. Adding `app.state.introspection_registry = {}` would bring the fixture into alignment with the contract `create_app()` establishes and prevent silent empty-registry surprises in future introspection endpoint tests.
4. **Startup warning noise in 404 tests**: Two 404 tests in `test_runs.py` call `create_app(db_path=":memory:")` without `default_model`, which triggers the startup warning on every test run. Passing `default_model="test-model"` (or `auto_discover=False`) to those calls would suppress the warning without affecting their 404 assertions.
5. **Factory documentation**: The factory closure created by `_make_pipeline_factory` is only safe to call when a model is configured -- calling it directly (outside the HTTP layer) with a `None`-model app passes `model=None` to `PipelineConfig.__init__` which declares `model: str`. Add a docstring note to `_make_pipeline_factory` making this precondition explicit for future consumers (e.g. task 2 CLI runner).
