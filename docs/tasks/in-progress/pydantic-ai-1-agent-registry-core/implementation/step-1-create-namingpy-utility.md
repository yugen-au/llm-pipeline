# IMPLEMENTATION - STEP 1: CREATE NAMING.PY UTILITY
**Status:** completed

## Summary
Created `llm_pipeline/naming.py` with `to_snake_case()` utility using the double-regex pattern. Correctly handles consecutive capitals (e.g. HTMLParser -> html_parser). Supports optional `strip_suffix` parameter for removing class suffixes before conversion.

## Files
**Created:** `llm_pipeline/naming.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/naming.py`
New module with `to_snake_case(name, strip_suffix=None)` function.

```python
# Core logic (double-regex pattern)
result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
return re.sub(r"([a-z\d])([A-Z])", r"\1_\2", result).lower()
```

Extracted from identical inline patterns in:
- `strategy.py` StepDefinition.create_step() (lines 59-61)
- `strategy.py` PipelineStrategy.__init_subclass__() (lines 189-191)
- `pipeline.py` StepKeyDict._normalize_key() (lines 66-68)

Fixes buggy single-regex in:
- `step.py` LLMStep.step_name (line 261): `re.sub('([a-z0-9])([A-Z])', ...)` misses consecutive-capital splitting

## Decisions
### Function signature includes strip_suffix parameter
**Choice:** `to_snake_case(name: str, strip_suffix: str | None = None) -> str`
**Rationale:** All 3 callsites strip a class suffix (Step, Strategy) before converting. Embedding this in the utility reduces boilerplate at each callsite. Steps 2-4 can use `to_snake_case(cls.__name__, strip_suffix='Step')`.

## Verification
[x] HTMLParser -> html_parser (consecutive capitals fixed)
[x] ConstraintExtraction -> constraint_extraction (normal CamelCase)
[x] strip_suffix='Step' correctly strips before converting
[x] strip_suffix='Strategy' correctly strips before converting
[x] Suffix not present in name -> no-op, converts normally
[x] IOError -> io_error (two-letter prefix)
[x] Module importable: `from llm_pipeline.naming import to_snake_case`
[x] `__all__` exports to_snake_case
