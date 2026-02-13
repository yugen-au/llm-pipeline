# IMPLEMENTATION - STEP 2: INTEGRATION TESTS
**Status:** completed

## Summary
Created integration tests for pipeline lifecycle events (PipelineStarted, PipelineCompleted, PipelineError) emitted by Pipeline.execute() using InMemoryEventHandler. 3 test cases verify success path, error path, and no-emitter path.

## Files
**Created:** tests/events/test_pipeline_lifecycle_events.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/events/test_pipeline_lifecycle_events.py`
Created comprehensive integration test suite with 3 test classes covering all lifecycle event scenarios.

```python
# Structure
- MockProvider for test LLM responses
- SimpleStep (success) and FailingStep (error) test steps with proper naming conventions
- SuccessPipeline and FailurePipeline configurations
- 3 test cases:
  1. test_pipeline_lifecycle_success: PipelineStarted + PipelineCompleted emitted
  2. test_pipeline_lifecycle_error: PipelineStarted + PipelineError emitted, no PipelineCompleted
  3. test_pipeline_lifecycle_no_emitter: executes successfully without events (zero overhead)
```

## Decisions
### Naming Convention Compliance
**Choice:** Created separate FailingInstructions class and SuccessRegistry/FailureRegistry classes
**Rationale:** PipelineConfig framework enforces naming conventions - instruction classes must match step names (FailingStep requires FailingInstructions), and registry classes must match pipeline names (SuccessPipeline requires SuccessRegistry). Violating these raises ValueError during class definition.

### Pipeline Instantiation Pattern
**Choice:** Direct instantiation `SuccessPipeline(session=..., provider=...)` not `.create()`
**Rationale:** Existing test_pipeline.py uses direct instantiation. PipelineConfig has no `.create()` classmethod. Pipeline takes `session` parameter and data via `execute(data=..., initial_context={})`.

### Expected Values Correction
**Choice:** Pipeline name is snake_case "success"/"failure" not class name; steps_executed=1 not 2
**Rationale:**
- `pipeline_name` is derived via snake_case conversion (SuccessPipeline -> "success")
- `_executed_steps` is a set of step CLASSES, not instances. Two SimpleStep instances = 1 unique class in set.
- PipelineCompleted.steps_executed uses `len(self._executed_steps)` which counts unique classes.

### Prompt Fixture Design
**Choice:** Seed prompts for both "simple" and "failing" step names in fixture
**Rationale:** Each step requires system/user prompts with matching step_name. FailingStep needs "failing.system" and "failing.user" prompts even though it errors before using them (validate_prompts runs during init).

## Verification
- [x] test_pipeline_lifecycle_success passes - PipelineStarted and PipelineCompleted emitted
- [x] test_pipeline_lifecycle_error passes - PipelineStarted and PipelineError emitted, traceback populated
- [x] test_pipeline_lifecycle_no_emitter passes - executes without event_emitter
- [x] All 34 event tests pass (31 existing + 3 new)
- [x] Verified execution_time_ms > 0 and is float type
- [x] Verified steps_executed count correct (1 unique class)
- [x] Verified PipelineError includes error_type="ValueError", error_message, traceback, step_name="failing"
- [x] Verified no PipelineCompleted on error path
- [x] Verified both success and error tests use InMemoryEventHandler correctly
