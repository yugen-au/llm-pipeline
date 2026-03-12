# IMPLEMENTATION - STEP 2: TOKEN FIELDS ON EVENTS
**Status:** completed

## Summary
Added three optional token usage fields (input_tokens, output_tokens, total_tokens) to LLMCallCompleted and StepCompleted event dataclasses. Fields default to None for full backward compatibility.

## Files
**Created:** none
**Modified:** llm_pipeline/events/types.py
**Deleted:** none

## Changes
### File: `llm_pipeline/events/types.py`
Added 3 optional `int | None` fields to both `LLMCallCompleted` and `StepCompleted` dataclasses, placed after existing fields with defaults.

```
# Before (LLMCallCompleted)
    attempt_count: int
    validation_errors: list[str] = field(default_factory=list)

# After (LLMCallCompleted)
    attempt_count: int
    validation_errors: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
```

```
# Before (StepCompleted)
    step_number: int
    execution_time_ms: float

# After (StepCompleted)
    step_number: int
    execution_time_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
```

## Decisions
### Field placement after existing defaults
**Choice:** Place token fields after `validation_errors` (LLMCallCompleted) and `execution_time_ms` (StepCompleted)
**Rationale:** Both dataclasses use `kw_only=True` so field ordering with defaults is unrestricted. Placing after last existing field keeps logical grouping.

### No __all__ changes needed
**Choice:** No modification to `__all__` exports
**Rationale:** Both `LLMCallCompleted` and `StepCompleted` are already exported. New fields are instance attributes, not new types.

## Verification
[x] Import succeeds after changes
[x] All 384 existing event tests pass (backward compatible)
[x] Dataclass construction works without token fields (defaults to None)
[x] Dataclass construction works with token fields
[x] Serialization (to_dict/to_json) includes token fields
[x] Frozen constraint preserved (fields immutable after creation)
