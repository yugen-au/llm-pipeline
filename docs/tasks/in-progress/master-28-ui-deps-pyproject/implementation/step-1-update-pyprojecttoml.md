# IMPLEMENTATION - STEP 1: UPDATE PYPROJECT.TOML
**Status:** completed

## Summary
Updated pyproject.toml with [project.scripts] CLI entry point, bumped [ui] optional deps to fastapi>=0.115.0/uvicorn[standard]>=0.32.0/python-multipart>=0.0.9, and synced [dev] group to match.

## Files
**Created:** none
**Modified:** pyproject.toml
**Deleted:** none

## Changes
### File: `pyproject.toml`
Added `[project.scripts]` section, updated `[ui]` deps, bumped `[dev]` deps.

```
# Before
[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
    "httpx>=0.24",
]

# After
[project.scripts]
llm-pipeline = "llm_pipeline.ui.cli:main"

[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = ["fastapi>=0.115.0", "uvicorn[standard]>=0.32.0", "python-multipart>=0.0.9"]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "google-generativeai>=0.3.0",
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "python-multipart>=0.0.9",
    "httpx>=0.24",
]
```

## Decisions
None -- all changes specified by CEO in plan.

## Verification
[x] `[project.scripts]` contains `llm-pipeline = "llm_pipeline.ui.cli:main"`
[x] `[ui]` group has fastapi>=0.115.0, uvicorn[standard]>=0.32.0, python-multipart>=0.0.9
[x] `[dev]` group has bumped fastapi/uvicorn and added python-multipart>=0.0.9
[x] Tests pass (675 passed, 1 pre-existing failure in test_events_router_prefix unrelated to this change)
[x] No hatch build config added (per plan)
