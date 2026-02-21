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

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] Test assertions use loose version checks -- `any("fastapi" in dep ...)` without checking version bound; same for uvicorn. No assertions for python-multipart or [dev] group bounds.

### Changes Made
#### File: `tests/test_ui.py`
Replaced loose `any("fastapi" in dep ...)` / `any("uvicorn" in dep ...)` assertions with exact string membership checks. Added 4 new tests for python-multipart in [ui], and all 3 deps in [dev] group.

```
# Before
assert any("fastapi" in dep for dep in ui_deps)
assert any("uvicorn" in dep for dep in ui_deps)

# After
assert "fastapi>=0.115.0" in ui_deps
assert "uvicorn[standard]>=0.32.0" in ui_deps
# + test_ui_group_contains_python_multipart
# + test_dev_group_contains_fastapi
# + test_dev_group_contains_uvicorn
# + test_dev_group_contains_python_multipart
```

### Verification
[x] All 7 TestPyprojectToml tests pass (was 3, now 7)
[x] Assertions check exact version bound strings, not just package name presence
