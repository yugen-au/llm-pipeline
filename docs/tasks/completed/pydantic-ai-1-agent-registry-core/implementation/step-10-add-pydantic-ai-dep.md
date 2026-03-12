# IMPLEMENTATION - STEP 10: ADD PYDANTIC-AI DEP
**Status:** completed

## Summary
Added pydantic-ai>=1.0.5 as optional dependency and dev dependency in pyproject.toml.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added pydantic-ai optional dependency group and added pydantic-ai to dev dependencies.

```
# Before
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
dev = [
    ...
    "httpx>=0.24",
]

# After
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
pydantic-ai = ["pydantic-ai>=1.0.5"]
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
dev = [
    ...
    "httpx>=0.24",
    "pydantic-ai>=1.0.5",
]
```

## Decisions
None

## Verification
[x] pydantic-ai optional dep group added with >=1.0.5
[x] pydantic-ai added to dev dependencies list
[x] Version constraint matches plan (>=1.0.5, supports defer_model_check=True)
[x] Existing dependencies unchanged
