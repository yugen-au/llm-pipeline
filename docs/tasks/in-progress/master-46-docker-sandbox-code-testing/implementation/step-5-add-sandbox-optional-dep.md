# IMPLEMENTATION - STEP 5: ADD SANDBOX OPTIONAL-DEP
**Status:** completed

## Summary
Added `sandbox = ["docker>=7.0"]` as separate optional-dependency group in pyproject.toml.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added sandbox optional-dependency after creator line.
```
# Before
[project.optional-dependencies]
creator = ["jinja2>=3.0"]
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]

# After
[project.optional-dependencies]
creator = ["jinja2>=3.0"]
sandbox = ["docker>=7.0"]
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
```

## Decisions
None -- plan was explicit.

## Verification
[x] sandbox group added after creator line
[x] docker>=7.0 is sole dependency in group
[x] not added to creator or dev groups
[x] install path: pip install llm-pipeline[sandbox]
