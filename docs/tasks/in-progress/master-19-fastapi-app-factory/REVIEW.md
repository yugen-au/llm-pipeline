# Architecture Review

## Overall Assessment
**Status:** complete

Solid foundational implementation. App factory, DI, import guard, and route stubs all follow the PLAN.md decisions faithfully. Code is minimal, well-documented, and correctly scoped for infrastructure-only (no endpoint logic). Tests are comprehensive (43 pass) covering imports, CORS config, DB wiring, router mounting, and DI generator behavior. No critical or high issues found.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | No features used beyond 3.11; `typing.Optional` used (valid) |
| Pydantic v2 | pass | Not directly used yet (stubs only); no conflicts |
| SQLModel / SQLAlchemy 2.0 | pass | `deps.py` uses `sqlmodel.Session`, `app.py` uses `sqlalchemy.create_engine` |
| Hatchling build | pass | `pyproject.toml` unchanged beyond adding `ui` optional dep |
| Tests with pytest | pass | 43 tests in `tests/test_ui.py`, all pass |
| No hardcoded values | pass | DB path parameterized, CORS origins parameterized, no magic strings |
| Error handling present | pass | Import guard with helpful message, `get_db` finally block for session cleanup |

## Issues Found
### Critical
None

### High
None

### Medium
#### Global engine mutation side-effect in create_app
**Step:** 3
**Details:** `init_pipeline_db(engine)` sets module-level `_engine` global in `llm_pipeline.db`. Each `create_app()` call mutates this shared state. In test scenarios this is benign (each app stores its own engine on `app.state.engine`), but in production if code elsewhere calls `get_engine()` from `llm_pipeline.db`, it will get whichever engine was last set by `create_app()`. This is an inherent characteristic of `init_pipeline_db()`'s current design, not something introduced by this task - but worth documenting. No code change needed now; the app correctly reads from `app.state.engine` via DI, not from the global.

#### Missing fastapi/uvicorn in dev dependencies
**Step:** 1
**Details:** The `dev` optional-dependencies group does not include `fastapi` or `uvicorn`. Tests in `test_ui.py` import `fastapi` directly. Currently tests pass because fastapi happens to be installed in the dev environment, but `pip install llm-pipeline[dev]` alone won't install it. Risk: CI environments installing only `[dev]` will fail on UI tests. PLAN.md risk table noted this. Fix: either add `fastapi` to dev deps, or add a pytest marker to skip UI tests when fastapi is not installed.

### Low
#### create_engine import source inconsistency
**Step:** 3
**Details:** `app.py` imports `create_engine` from `sqlalchemy` while the canonical `db/__init__.py` imports it from `sqlmodel`. Both are functionally identical (SQLModel re-exports it), and the broader codebase uses both interchangeably. No functional impact. Mentioned for consistency awareness only.

#### Test file naming mismatch with scope doc
**Step:** N/A (testing)
**Details:** Scope document references `tests/test_ui_app.py` but actual file is `tests/test_ui.py`. Minor documentation discrepancy; the file itself is correct and comprehensive.

## Review Checklist
[x] Architecture patterns followed - app factory, DI via FastAPI Depends, per-router prefixes, ReadOnlySession wrapper
[x] Code quality and maintainability - clean, minimal, well-documented docstrings
[x] Error handling present - import guard, session cleanup in finally
[x] No hardcoded values - all configurable via params
[x] Project conventions followed - consistent with existing codebase patterns (SQLModel, ReadOnlySession, init_pipeline_db reuse)
[x] Security considerations - allow_credentials=False with wildcard origins (CORS spec compliant), ReadOnlySession prevents writes via API
[x] Properly scoped (DRY, YAGNI, no over-engineering) - bare stubs, no premature endpoint logic, no unnecessary abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| pyproject.toml | pass | `ui` optional dep group correctly added with fastapi>=0.100, uvicorn[standard]>=0.20 |
| llm_pipeline/ui/__init__.py | pass | Module-level import guard, re-exports create_app, __all__ defined |
| llm_pipeline/ui/app.py | pass | Clean factory, CORS wired, DB engine on app.state, lazy router imports, all 6 routers mounted |
| llm_pipeline/ui/deps.py | pass | Generator DI, ReadOnlySession wrap, explicit session.close() in finally, DBSession type alias |
| llm_pipeline/ui/routes/__init__.py | pass | Empty file as expected |
| llm_pipeline/ui/routes/runs.py | pass | Stub with prefix="/runs", tags=["runs"] |
| llm_pipeline/ui/routes/steps.py | pass | Stub with prefix="/runs/{run_id}/steps", tags=["steps"] |
| llm_pipeline/ui/routes/events.py | pass | Stub with prefix="/events", tags=["events"] |
| llm_pipeline/ui/routes/prompts.py | pass | Stub with prefix="/prompts", tags=["prompts"] |
| llm_pipeline/ui/routes/pipelines.py | pass | Stub with prefix="/pipelines", tags=["pipelines"] |
| llm_pipeline/ui/routes/websocket.py | pass | Stub with tags=["websocket"], no prefix |
| tests/test_ui.py | pass | 43 tests, all pass, covers imports/CORS/DB/routers/DI |

## New Issues Introduced
- Global `_engine` mutation via `init_pipeline_db()` is pre-existing behavior, not new
- Missing dev dep for fastapi is a test environment gap (documented in PLAN.md risks)
- None of the new code introduces regressions - existing 347 tests unaffected

## Recommendation
**Decision:** APPROVE
Implementation is clean, minimal, and faithfully follows all PLAN.md architectural decisions. The two medium issues are both pre-existing constraints (global engine design) or known risks already documented in the plan (dev deps gap). Neither blocks downstream tasks 20-25. The dev deps gap should be addressed before CI integration but is not blocking for this foundational task.

---

# Architecture Re-Review (Post-Fix)

## Overall Assessment
**Status:** complete

All 4 issues from the initial review have been addressed. Fixes are correct, minimal, and introduce no new issues. 43 tests pass.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| SQLModel / SQLAlchemy 2.0 | pass | `app.py` now imports `create_engine` from `sqlmodel`, matching `db/__init__.py` |
| Tests with pytest | pass | 43 tests pass; dev deps now include fastapi so `pip install llm-pipeline[dev]` covers UI tests |

## Fix Verification

### MEDIUM - Missing fastapi in dev deps (Step 1)
**Status:** RESOLVED
**Evidence:** `pyproject.toml` dev group now includes `"fastapi>=0.100"` and `"uvicorn[standard]>=0.20"` (lines 26-27). Version constraints match the `ui` group exactly. CI environments installing `[dev]` will now get FastAPI.

### MEDIUM - Global engine mutation (Step 3)
**Status:** RESOLVED
**Evidence:** `app.py` lines 39-41 now contain a comment documenting the `init_pipeline_db()` global side-effect. No behavioral change needed -- the app correctly reads from `app.state.engine` via DI. Comment is accurate and concise.

### LOW - create_engine import source (Step 3)
**Status:** RESOLVED
**Evidence:** `app.py` line 6 changed from `from sqlalchemy import create_engine` to `from sqlmodel import create_engine`. Now consistent with `llm_pipeline/db/__init__.py` line 12 which uses the same import. Functionally identical but improves codebase consistency.

### LOW - Test file naming mismatch
**Status:** ACKNOWLEDGED
**Evidence:** Documentation-only discrepancy. No code change needed; actual file `tests/test_ui.py` is correct and comprehensive.

## Issues Found
### Critical
None

### High
None

### Medium
None

### Low
None

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| pyproject.toml | pass | dev deps now include fastapi>=0.100 and uvicorn[standard]>=0.20 |
| llm_pipeline/ui/app.py | pass | `create_engine` import from sqlmodel; global engine side-effect documented |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE
All previously identified issues resolved. No new issues introduced. Implementation is clean and ready for downstream tasks 20-25.
