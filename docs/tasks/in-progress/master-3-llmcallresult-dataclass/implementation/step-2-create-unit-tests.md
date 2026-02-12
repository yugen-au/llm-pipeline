# IMPLEMENTATION - STEP 2: CREATE UNIT TESTS
**Status:** completed

## Summary
Created tests/test_llm_call_result.py with 18 unit tests covering all LLMCallResult fields, helper methods, factory classmethods, immutability, equality, and repr.

## Files
**Created:** tests/test_llm_call_result.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/test_llm_call_result.py`
New file with 18 tests organized into 5 test classes:

- `TestInstantiation` (2 tests): defaults and all-fields
- `TestFactories` (4 tests): success, failure, failure-empty-errors, success-none-raises
- `TestSerialization` (3 tests): to_dict default, to_dict all-set, to_json round-trip
- `TestStatusProperties` (5 tests): is_success true/false, partial success, is_failure true/false
- `TestDataclassBehavior` (4 tests): frozen immutability, equality, inequality, repr

```python
# Import pattern - uses public re-export path
from llm_pipeline.llm import LLMCallResult

# FrozenInstanceError test
with pytest.raises(dataclasses.FrozenInstanceError):
    result.parsed = {"b": 2}

# Partial success test (CEO decision: validation_errors are diagnostic only)
result = LLMCallResult(parsed={"data": "ok"}, validation_errors=["prior attempt error"])
assert result.is_success is True
```

## Decisions
### Import path
**Choice:** Import via `llm_pipeline.llm` (public re-export) not `llm_pipeline.llm.result` (internal)
**Rationale:** Tests should exercise the public API surface, matching how consumers import

### Test organization
**Choice:** Class-based grouping by concern (instantiation, factories, serialization, status, dataclass behavior)
**Rationale:** Matches existing test_pipeline.py style, logical grouping aids readability

### FrozenInstanceError import
**Choice:** `dataclasses.FrozenInstanceError` (stdlib)
**Rationale:** Available in Python 3.11+ (project minimum), no need for generic AttributeError fallback

## Verification
[x] 18 tests created matching PLAN.md spec exactly
[x] All 18 tests pass (pytest tests/test_llm_call_result.py -v)
[x] All 50 tests pass (full suite, no regressions)
[x] Partial success case verified as is_success=True
[x] success(parsed=None) raises ValueError
[x] failure(validation_errors=[]) accepted
[x] Frozen immutability enforced via FrozenInstanceError

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] Fragile test_repr: used sentinel values and partial field-name assertions instead of exact string match
[x] Missing test_failure_factory_non_none_parsed_raises: added test covering failure() ValueError guard for non-None parsed

### Changes Made
#### File: `tests/test_llm_call_result.py`
Made test_repr resilient to formatting changes; added missing factory guard test.

```python
# Before - test_repr used short values that could false-positive match
assert "'k': 'v'" in r or '"k": "v"' in r or "k" in r
assert "raw" in r
assert "m" in r
assert "2" in r
assert "e" in r

# After - sentinel values, checks field name presence
assert "raw_resp_sentinel" in r
assert "model_sentinel" in r
assert "err_sentinel" in r
assert "attempt_count" in r
```

```python
# New test added
def test_failure_factory_non_none_parsed_raises(self):
    """failure(parsed=non-None) raises ValueError."""
    with pytest.raises(ValueError, match="parsed must be None"):
        LLMCallResult.failure(
            parsed={"data": "value"},
            raw_response="text",
            model_name="gemini-2.0-flash",
            attempt_count=1,
            validation_errors=[],
        )
```

### Verification
[x] test_repr passes with sentinel-based partial assertions
[x] test_failure_factory_non_none_parsed_raises passes
[x] 51 total tests pass (19 LLMCallResult + 32 existing), no regressions
