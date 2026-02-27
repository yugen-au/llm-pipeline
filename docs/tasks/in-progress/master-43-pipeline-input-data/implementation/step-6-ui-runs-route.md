# IMPLEMENTATION - STEP 6: UI RUNS ROUTE
**Status:** completed

## Summary
Updated trigger_run() in runs.py to pass input_data as separate param to execute() instead of through initial_context dict.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/runs.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/runs.py`
Changed execute() call in run_pipeline background function to use dedicated input_data kwarg.

```
# Before (L224)
pipeline.execute(data=None, initial_context=body.input_data or {})

# After (L224)
pipeline.execute(data=None, input_data=body.input_data)
```

Key: removed `or {}` default -- execute() Step 3 validation handles None vs missing input_data. Passing None when no input_data provided is correct; execute() only errors if INPUT_DATA schema is declared but input_data missing.

## Decisions
### Remove `or {}` fallback
**Choice:** Pass body.input_data directly (may be None) instead of `body.input_data or {}`
**Rationale:** execute() Step 3 validation already handles None case. Empty dict `{}` would bypass "input_data not provided" check for pipelines requiring input. Clean separation means execute() owns validation, not the route.

## Verification
[x] L224 now uses input_data= kwarg instead of initial_context=
[x] factory() call on L223 unchanged (passes input_data as constructor param -- different concern)
[x] No other references to initial_context in the execute call
[x] body.input_data passed directly without `or {}` coercion

## Fix Iteration 0
**Issues Source:** TESTING.md
**Status:** fixed

### Issues Addressed
[x] test_input_data_threaded_to_factory_and_execute fails with KeyError: 'initial_context' - test asserted execute_kwargs_log[0]["initial_context"] but Step 6 changed runs.py to pass input_data as separate param

### Changes Made
#### File: `tests/ui/test_runs.py`
Updated assertion and docstring to match new execute() call signature.

```
# Before
"""input_data from POST body reaches factory kwargs and pipeline.execute initial_context."""
# execute received initial_context matching input_data
assert execute_kwargs_log[0]["initial_context"] == payload

# After
"""input_data from POST body reaches factory kwargs and pipeline.execute input_data param."""
# execute received input_data as separate param
assert execute_kwargs_log[0]["input_data"] == payload
```

### Verification
[x] test_input_data_threaded_to_factory_and_execute passes
[x] Assertion checks execute_kwargs_log[0]["input_data"] matching new param name
