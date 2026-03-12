# IMPLEMENTATION - STEP 2: CREATE VALIDATORS.PY
**Status:** completed

## Summary
Created `llm_pipeline/validators.py` with two validator factory functions (`not_found_validator`, `array_length_validator`) and a `DEFAULT_NOT_FOUND_INDICATORS` constant for pydantic-ai output validators.

## Files
**Created:** `llm_pipeline/validators.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/validators.py`
New file containing:

1. `DEFAULT_NOT_FOUND_INDICATORS` - list of 8 common LLM evasion phrases
2. `_strip_number_prefix(value)` - private helper using compiled regex `^\d+\.\s*`
3. `not_found_validator(indicators=None)` - factory returning async validator that checks string outputs for evasion phrases, raises `ModelRetry` on match, passes non-strings through unchanged
4. `array_length_validator()` - factory (no config arg) returning async validator that reads `ctx.deps.array_validation` at runtime; no-op when None; validates length (ModelRetry on mismatch); silently reorders via `model_copy(update={...})` when `allow_reordering=True`
5. `_reorder_items()` - private helper for match_field-based reordering with optional number prefix stripping
6. `__all__` exports

## Decisions
### array_length_validator takes no config arg
**Choice:** Factory takes zero arguments; reads config from `ctx.deps.array_validation` at call time
**Rationale:** Per PLAN.md correction: agent built once per step, validator registered once, but per-call config varies. No-op when deps.array_validation is None.

### Validators are async
**Choice:** Both validator functions are async
**Rationale:** pydantic-ai output validators support both sync and async; async is forward-compatible with any future I/O needs. Context7 docs confirm async validators work with `agent.output_validator()`.

### Unmatched items appended during reorder
**Choice:** Items not matched by input_array are appended at end rather than dropped
**Rationale:** Defensive -- avoids silently losing LLM output data. Length check already passed, so all items are present; reorder just fixes ordering.

## Verification
[x] File imports successfully (`from llm_pipeline.validators import ...`)
[x] Factory functions instantiate and return callables with correct `__name__`
[x] All 583 existing tests pass (1 pre-existing failure in test_ui.py unrelated)
[x] DEFAULT_NOT_FOUND_INDICATORS contains 8 phrases per spec
[x] not_found_validator guards non-string outputs (returns unchanged)
[x] array_length_validator no-ops when ctx.deps.array_validation is None
[x] array_field_name validated non-empty at call time (raises ValueError)
