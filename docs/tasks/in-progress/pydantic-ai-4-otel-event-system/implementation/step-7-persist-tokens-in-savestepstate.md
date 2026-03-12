# IMPLEMENTATION - STEP 7: PERSIST TOKENS IN _SAVE_STEP_STATE
**Status:** completed

## Summary
Updated `_save_step_state()` to accept explicit token keyword parameters and pass them to `PipelineStepState()` constructor. Added guard to compute `total_tokens` when caller provides input/output but not total. Fixed test mock helpers that lacked `.usage()` setup, which caused DB insert failures once token values flowed through.

## Files
**Created:** `docs/tasks/in-progress/pydantic-ai-4-otel-event-system/implementation/step-7-persist-tokens-in-savestepstate.md`
**Modified:** `llm_pipeline/pipeline.py`, `tests/events/conftest.py`, `tests/events/test_ctx_state_events.py`, `tests/events/test_extraction_events.py`, `tests/test_pipeline.py`, `tests/test_pipeline_run_tracking.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Replaced `**kwargs` with explicit keyword parameters and passed them to PipelineStepState constructor. Added total_tokens guard.

```python
# Before
def _save_step_state(self, step, step_number, instructions, input_hash, execution_time_ms=None, model_name=None, **kwargs):
    ...
    state = PipelineStepState(
        ...existing fields...,
    )

# After
def _save_step_state(self, step, step_number, instructions, input_hash, execution_time_ms=None, model_name=None,
                     input_tokens=None, output_tokens=None, total_tokens=None, total_requests=None):
    ...
    # compute total_tokens if caller provided input/output but not total
    if total_tokens is None and (input_tokens is not None or output_tokens is not None):
        total_tokens = (input_tokens or 0) + (output_tokens or 0)

    state = PipelineStepState(
        ...existing fields...,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        total_requests=total_requests,
    )
```

### File: `tests/events/conftest.py`
Added `_mock_usage()` helper returning MagicMock with `input_tokens=10, output_tokens=5, requests=1`. Applied to all three `make_*_run_result` helpers via `mock_result.usage.return_value`.

### File: `tests/events/test_ctx_state_events.py`
Added `.usage()` mock setup to `_make_empty_ctx_run_result()`.

### File: `tests/events/test_extraction_events.py`
Added `.usage()` mock setup to `_make_failing_run_result()`.

### File: `tests/test_pipeline.py`
Added `.usage()` mock setup to `make_run_result()`.

### File: `tests/test_pipeline_run_tracking.py`
Added `.usage()` mock setup to `_make_run_result()`.

## Decisions
### Replace **kwargs with explicit params
**Choice:** Explicit keyword params instead of keeping **kwargs
**Rationale:** Steps 5-6 already pass these kwargs; explicit params make the contract clear and enable IDE support. **kwargs was silently swallowing values without using them.

### Fix test mocks in same commit
**Choice:** Fix all test mock helpers to include `.usage()` return values
**Rationale:** Steps 5-6 added token accumulation code that reads `run_result.usage()`. With `**kwargs`, mock values were silently dropped. Now that values flow to DB, MagicMock auto-generated values cause SQLite type errors. Fixing mocks is required for backward compat.

## Verification
[x] `_save_step_state` accepts input_tokens, output_tokens, total_tokens, total_requests
[x] All four fields passed to PipelineStepState constructor
[x] total_tokens guard: computed from input+output when caller passes None for total but provides components
[x] total_tokens NOT overridden when caller provides explicit value
[x] All 588 tests pass (1 pre-existing UI test failure unrelated)
[x] Backward compat: all params default to None
