# IMPLEMENTATION - STEP 2: MODEL GUARD
**Status:** completed

## Summary
Added model None guard to trigger_run endpoint in runs.py. When no default model is configured (app.state.default_model is None), the endpoint returns HTTP 422 with an actionable error message before any pipeline execution attempt.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/runs.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/runs.py`
Added model None guard after factory lookup, before pipeline execution. Uses `getattr(request.app.state, "default_model", None)` to safely retrieve the model set by `create_app()` in step 1.

```
# Before (lines 207-209)
    run_id = str(uuid.uuid4())
    engine = request.app.state.engine

# After (lines 207-217)
    # Guard: model must be configured before pipeline execution
    default_model = getattr(request.app.state, "default_model", None)
    if default_model is None:
        raise HTTPException(
            status_code=422,
            detail="No model configured. Set LLM_PIPELINE_MODEL env var or pass --model flag.",
        )

    run_id = str(uuid.uuid4())
    engine = request.app.state.engine
```

## Decisions
### Guard placement after factory lookup
**Choice:** Guard placed after factory lookup (404 check) but before run_id generation and factory call
**Rationale:** Pipeline must exist before checking model config -- returning 422 for a nonexistent pipeline would be misleading. Guard sits at the execution boundary per CEO decision: missing model should not block UI startup/browsing, only fail at execution time.

### Use getattr with default None
**Choice:** `getattr(request.app.state, "default_model", None)` instead of direct attribute access
**Rationale:** Defensive access ensures backward compatibility if runs.py is used with an older create_app() that doesn't set default_model.

## Verification
[x] Guard is after factory lookup (404 for unknown pipeline takes priority)
[x] Guard is before factory call (no pipeline instantiation attempted without model)
[x] HTTP 422 status code matches PLAN.md specification
[x] Error message matches PLAN.md: actionable, references env var and --model flag
[x] app.state.default_model set by step 1 in create_app() (line 173 of app.py)

## Fix Iteration 0
**Issues Source:** TESTING.md
**Status:** fixed

### Issues Addressed
[x] Test fixture regression: conftest _make_app() missing default_model (6 tests)
[x] Test fixture regression: TestTriggerRun._make_client_with_registry and inline create_app() missing default_model (4 tests)

### Changes Made
#### File: `tests/ui/conftest.py`
Added `app.state.default_model = "test-model"` after `app.state.pipeline_registry` in `_make_app()`.
```
# Before
    app.state.engine = engine
    app.state.pipeline_registry = {}

# After
    app.state.engine = engine
    app.state.pipeline_registry = {}
    app.state.default_model = "test-model"
```

#### File: `tests/ui/test_runs.py`
Added `default_model="test-model"` to all 4 `create_app()` calls in TestTriggerRun:
- `_make_client_with_registry()` (affects test_returns_202_with_run_id_and_accepted)
- `test_run_id_is_valid_uuid` inline call
- `test_background_task_executes_pipeline` inline call
- `test_input_data_threaded_to_factory_and_execute` inline call
```
# Before
app = create_app(db_path=":memory:", pipeline_registry=registry)

# After
app = create_app(db_path=":memory:", pipeline_registry=registry, default_model="test-model")
```

### Verification
[x] All 10 previously failing tests now pass
[x] 2 tests that already passed (test_returns_404_for_unregistered_pipeline, test_returns_404_when_registry_empty) still pass -- 404 guard fires before model guard as intended
[x] No production code changed, only test fixtures

## Fix Iteration 1
**Issues Source:** ARCHITECTURE_REVIEW
**Status:** fixed

### Issues Addressed
[x] Missing test coverage: no test verifying 422 when default_model is None

### Changes Made
#### File: `tests/ui/test_runs.py`
Added `test_returns_422_when_no_model_configured` to TestTriggerRun. Creates app with a registered pipeline but `default_model=None`, asserts HTTP 422 and that the detail message contains "No model configured" and "LLM_PIPELINE_MODEL".
```python
def test_returns_422_when_no_model_configured(self):
    noop = lambda run_id, engine, **kw: None
    app = create_app(
        db_path=":memory:",
        pipeline_registry={"p": noop},
        default_model=None,
    )
    with TestClient(app) as client:
        resp = client.post("/api/runs", json={"pipeline_name": "p"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "No model configured" in detail
    assert "LLM_PIPELINE_MODEL" in detail
```

### Verification
[x] New test passes
[x] All 7 TestTriggerRun tests pass (no regressions)
[x] No production code changed
