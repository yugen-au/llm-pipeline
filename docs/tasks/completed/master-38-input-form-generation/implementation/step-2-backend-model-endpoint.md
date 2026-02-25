# IMPLEMENTATION - STEP 2: BACKEND MODEL + ENDPOINT
**Status:** completed

## Summary
Extended backend to accept `input_data` in run triggers, thread it through to pipeline execution via factory kwargs and `pipeline.execute()` args, and added `pipeline_input_schema` stub to `PipelineMetadata`.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/runs.py, llm_pipeline/pipeline.py, llm_pipeline/ui/routes/pipelines.py, tests/ui/test_runs.py, tests/ui/test_integration.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/runs.py`
Added `Dict`, `Any` to typing imports. Added `input_data: Optional[Dict[str, Any]] = None` to `TriggerRunRequest`. Updated `run_pipeline()` closure to pass `input_data=body.input_data or {}` to factory and call `pipeline.execute(data=None, initial_context=body.input_data or {})`.

```
# Before
class TriggerRunRequest(BaseModel):
    pipeline_name: str

pipeline = factory(run_id=run_id, engine=engine, event_emitter=bridge)
pipeline.execute()

# After
class TriggerRunRequest(BaseModel):
    pipeline_name: str
    input_data: Optional[Dict[str, Any]] = None

pipeline = factory(run_id=run_id, engine=engine, event_emitter=bridge, input_data=body.input_data or {})
pipeline.execute(data=None, initial_context=body.input_data or {})
```

### File: `llm_pipeline/pipeline.py`
Made `data` and `initial_context` params optional with defaults (`None`). Added guard `if initial_context is None: initial_context = {}`.

```
# Before
def execute(self, data: Any, initial_context: Dict[str, Any], ...)

# After
def execute(self, data: Any = None, initial_context: Optional[Dict[str, Any]] = None, ...)
    if initial_context is None:
        initial_context = {}
```

### File: `llm_pipeline/ui/routes/pipelines.py`
Added `pipeline_input_schema: Optional[Any] = None` to `PipelineMetadata` model.

```
# Before
class PipelineMetadata(BaseModel):
    pipeline_name: str
    registry_models: List[str] = []
    strategies: List[StrategyMetadata] = []
    execution_order: List[str] = []

# After
class PipelineMetadata(BaseModel):
    pipeline_name: str
    registry_models: List[str] = []
    strategies: List[StrategyMetadata] = []
    execution_order: List[str] = []
    pipeline_input_schema: Optional[Any] = None
```

### File: `tests/ui/test_runs.py`
Updated mock pipeline `execute()` methods to accept `**kwargs` so they absorb the new keyword args from `run_pipeline()`.

### File: `tests/ui/test_integration.py`
Updated `_FailingPipeline.execute()` and `_NoOpPipeline.execute()` to accept `**kwargs`.

## Decisions
### Mock execute signatures
**Choice:** Updated test mock `execute()` methods to `execute(self, **kwargs)` rather than changing how the route calls execute.
**Rationale:** The route should pass explicit kwargs (`data=`, `initial_context=`) for clarity. Mock pipelines need `**kwargs` to absorb them, consistent with how real `PipelineConfig.execute()` accepts these params.

## Verification
[x] TriggerRunRequest accepts input_data field (Optional[Dict[str, Any]])
[x] pipeline.execute() callable with zero args (defaults to None/{})
[x] input_data forwarded to factory as kwarg
[x] PipelineMetadata has pipeline_input_schema field (defaults to None)
[x] All existing Python tests pass (79 passed in affected files)

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] No test coverage for input_data threading -- added test that verifies input_data from POST body reaches factory kwargs and pipeline.execute() initial_context

### Changes Made
#### File: `tests/ui/test_runs.py`
Added `test_input_data_threaded_to_factory_and_execute` to `TestTriggerRun`. Uses spy factory and spy pipeline that log kwargs. POSTs `{"pipeline_name": "spy", "input_data": {"foo": "bar", "count": 42}}` and asserts:
- `factory_kwargs["input_data"] == {"foo": "bar", "count": 42}`
- `execute_kwargs["initial_context"] == {"foo": "bar", "count": 42}`

```
# Added test
def test_input_data_threaded_to_factory_and_execute(self):
    factory_kwargs_log = []
    execute_kwargs_log = []

    class _SpyPipeline:
        def __init__(self, **kwargs):
            factory_kwargs_log.append(kwargs)
        def execute(self, **kwargs):
            execute_kwargs_log.append(kwargs)
        def save(self):
            pass

    def _spy_factory(run_id, engine, **kw):
        return _SpyPipeline(run_id=run_id, engine=engine, **kw)

    app = create_app(db_path=":memory:", pipeline_registry={"spy": _spy_factory})
    payload = {"foo": "bar", "count": 42}
    with TestClient(app) as client:
        resp = client.post("/api/runs", json={"pipeline_name": "spy", "input_data": payload})
        assert resp.status_code == 202
    assert factory_kwargs_log[0]["input_data"] == payload
    assert execute_kwargs_log[0]["initial_context"] == payload
```

### Verification
[x] New test passes in isolation (1 passed)
[x] All 24 tests in test_runs.py pass (no regressions)
