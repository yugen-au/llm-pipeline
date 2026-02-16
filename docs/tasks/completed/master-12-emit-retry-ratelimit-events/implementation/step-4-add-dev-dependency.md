# IMPLEMENTATION - STEP 4: ADD DEV DEPENDENCY
**Status:** completed

## Summary
Added google-generativeai to dev optional dependencies in pyproject.toml so tests can mock at Gemini API level.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added google-generativeai>=0.3.0 to dev optional deps list, after pytest-cov.

```
# Before
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
]

# After
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
]
```

## Decisions
### Version constraint
**Choice:** `>=0.3.0` matching gemini extra
**Rationale:** Consistency with existing `gemini = ["google-generativeai>=0.3.0"]` at line 20

## Verification
[x] gemini extra uses same version constraint (>=0.3.0) - confirmed at line 20
[x] dev list now includes google-generativeai for test mocking
