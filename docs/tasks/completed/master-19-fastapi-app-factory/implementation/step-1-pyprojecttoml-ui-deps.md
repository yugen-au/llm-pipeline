# IMPLEMENTATION - STEP 1: PYPROJECT.TOML UI DEPS
**Status:** completed

## Summary
Added `ui` optional dependency group to pyproject.toml with fastapi and uvicorn packages.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added `ui` optional dependency group between `gemini` and `dev` groups.

```
# Before
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
dev = [

# After
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]
dev = [
```

## Decisions
None - step was prescriptive.

## Verification
[x] `ui` group present in `[project.optional-dependencies]`
[x] fastapi version constraint `>=0.100` matches plan
[x] uvicorn version constraint `>=0.20` with `[standard]` extras matches plan
[x] `gemini` group unchanged
[x] `dev` group unchanged - fastapi NOT added per scope instructions

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] Missing fastapi/uvicorn in dev dependencies - CI environments installing only `[dev]` would fail on UI tests

### Changes Made
#### File: `pyproject.toml`
Added fastapi and uvicorn to `dev` optional-dependencies so `pip install llm-pipeline[dev]` includes UI deps for testing.

```
# Before
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
]

# After
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
]
```

### Verification
[x] `dev` group now includes `fastapi>=0.100`
[x] `dev` group now includes `uvicorn[standard]>=0.20`
[x] Existing dev deps (pytest, pytest-cov, google-generativeai) unchanged
[x] `ui` and `gemini` groups unchanged
