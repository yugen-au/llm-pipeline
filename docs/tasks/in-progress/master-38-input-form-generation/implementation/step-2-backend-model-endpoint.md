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
