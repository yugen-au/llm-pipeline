# IMPLEMENTATION - STEP 2: ADD STEPDEPS FIELDS
**Status:** completed

## Summary
Added two forward-compatibility fields (array_validation, validation_context) to StepDeps dataclass for Task 3 output_validators. Both default to None, unused in Task 2.

## Files
**Created:** none
**Modified:** llm_pipeline/agent_builders.py
**Deleted:** none

## Changes
### File: `llm_pipeline/agent_builders.py`
Added two optional fields after `variable_resolver` and updated docstring with Task 3 reservation note.

```
# Before
    # Optional deps
    event_emitter: Any | None = None  # PipelineEventEmitter
    variable_resolver: Any | None = None  # VariableResolver

# After
    # Optional deps
    event_emitter: Any | None = None  # PipelineEventEmitter
    variable_resolver: Any | None = None  # VariableResolver

    # Forward-compat: Task 3 output_validators (unused in Task 2)
    array_validation: Any | None = None
    validation_context: Any | None = None
```

## Decisions
None

## Verification
[x] `Any` already imported from `typing` (line 11)
[x] Fields placed after `variable_resolver` (last optional fields)
[x] Both fields default to None
[x] Docstring updated with Task 3 reservation note
[x] `__all__` unchanged (no new exports)
