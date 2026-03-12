# IMPLEMENTATION - STEP 1: ADD CONFIG FIELDS
**Status:** completed

## Summary
Added `array_field_name` field to `ArrayValidationConfig` and `not_found_indicators` field to `StepDefinition` to support pydantic-ai output validators downstream.

## Files
**Created:** none
**Modified:** `llm_pipeline/types.py`, `llm_pipeline/strategy.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/types.py`
Added `array_field_name: str = ""` to `ArrayValidationConfig` after `strip_number_prefix`.
```
# Before
    strip_number_prefix: bool = True

# After
    strip_number_prefix: bool = True
    array_field_name: str = ""
```

### File: `llm_pipeline/strategy.py`
Added `not_found_indicators: list[str] | None = None` to `StepDefinition` after `agent_name`.
```
# Before
    agent_name: str | None = None

# After
    agent_name: str | None = None
    not_found_indicators: list[str] | None = None
```

## Decisions
None

## Verification
[x] ArrayValidationConfig instantiates with default `array_field_name=''`
[x] StepDefinition has `not_found_indicators` in dataclass fields
[x] All 583 existing tests pass (1 pre-existing failure in test_ui.py unrelated)
[x] Uses built-in `list[str]` (Python 3.11+), no `List` import needed
