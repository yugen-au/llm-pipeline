# Task Summary

## Work Completed

Created the `llm_pipeline/ui/` package: FastAPI app factory with CORS middleware, DB engine wiring via `init_pipeline_db()`, module-level import guard, dependency injection module with `ReadOnlySession` wrapping, and 6 route stub modules (runs, steps, events, prompts, pipelines, websocket). Also updated `pyproject.toml` with new `ui` optional dependency group and added FastAPI to `dev` dependencies. 43 new tests written and passing. Full test suite (511/527) unaffected by task.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/__init__.py` | Module-level FastAPI import guard; re-exports `create_app` |
| `llm_pipeline/ui/app.py` | `create_app(db_path, cors_origins)` factory: CORS middleware, DB engine on `app.state`, mounts all 6 routers |
| `llm_pipeline/ui/deps.py` | `get_db()` DI generator yielding `ReadOnlySession`; `DBSession` type alias |
| `llm_pipeline/ui/routes/__init__.py` | Empty package marker |
| `llm_pipeline/ui/routes/runs.py` | Router stub: `prefix="/runs"`, `tags=["runs"]` |
| `llm_pipeline/ui/routes/steps.py` | Router stub: `prefix="/runs/{run_id}/steps"`, `tags=["steps"]` |
| `llm_pipeline/ui/routes/events.py` | Router stub: `prefix="/events"`, `tags=["events"]` |
| `llm_pipeline/ui/routes/prompts.py` | Router stub: `prefix="/prompts"`, `tags=["prompts"]` |
| `llm_pipeline/ui/routes/pipelines.py` | Router stub: `prefix="/pipelines"`, `tags=["pipelines"]` |
| `llm_pipeline/ui/routes/websocket.py` | Router stub: no prefix, `tags=["websocket"]` (bare minimum) |
| `tests/test_ui.py` | 43 tests: import guard, CORS config, DB engine wiring, router mounting, DI generator behavior |

### Modified

| File | Changes |
| --- | --- |
| `pyproject.toml` | Added `ui = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]` optional dep group; added same to `dev` group for CI test coverage |

## Commits Made

| Hash | Message |
| --- | --- |
| `d2da350` | `docs(validate-A): master-19-fastapi-app-factory` |
| `4d81fbf` | `docs(planning-A): master-19-fastapi-app-factory` |
| `62ee8a7` | `docs(implementation-A): master-19-fastapi-app-factory` |
| `0bbfa43` | `docs(implementation-B): master-19-fastapi-app-factory` |
| `7555871` | `docs(review-A): master-19-fastapi-app-factory` |
| `2782e33` | `docs(fixing-review-A): master-19-fastapi-app-factory` |
| `789d680` | `docs(fixing-review-B): master-19-fastapi-app-factory` |

Note: Code changes (pyproject.toml, all `llm_pipeline/ui/` files, `tests/test_ui.py`) are embedded in the implementation and fixing-review commits alongside their documentation. State transition commits (`chore(state): ...`) are workflow bookkeeping and not listed above.

## Deviations from Plan

- `app.py` uses lazy (inside `create_app()` body) router imports rather than module-level imports. Rationale: avoids circular import risk when route modules later import from `deps.py`. Not in PLAN.md but aligned with the intent.
- Test file named `tests/test_ui.py` rather than `tests/test_ui_app.py` as referenced in scope documentation. File is correct and comprehensive; documentation reference was a minor discrepancy.
- `fastapi` and `uvicorn[standard]` also added to `dev` optional-dependencies (not in original plan scope). Added during review-fix loop to ensure `pip install llm-pipeline[dev]` covers UI tests in CI.

## Issues Encountered

### Missing fastapi in dev dependencies
**Resolution:** Added `fastapi>=0.100` and `uvicorn[standard]>=0.20` to the `dev` optional-dependencies group in `pyproject.toml` during the review-fix loop. Version constraints mirror the `ui` group.

### create_engine import source inconsistency
`app.py` initially imported `create_engine` from `sqlalchemy`; the rest of the codebase imports it from `sqlmodel` (which re-exports it).
**Resolution:** Changed `app.py` import to `from sqlmodel import create_engine` for consistency.

### Global engine mutation side-effect (undocumented)
`init_pipeline_db()` sets a module-level `_engine` global in `llm_pipeline.db`. Multiple `create_app()` calls overwrite this global, meaning code that calls `get_engine()` from `llm_pipeline.db` will get whichever engine was last created. This is pre-existing behavior, not introduced by this task.
**Resolution:** Added inline comment in `app.py` documenting the side-effect. No code change required; the app correctly reads from `app.state.engine` via DI, not from the global.

## Success Criteria

- [x] `from llm_pipeline.ui import create_app` raises `ImportError` with install hint when FastAPI not installed - import guard in `__init__.py` verified via code inspection; module-level try/except raises with correct message
- [x] `from llm_pipeline.ui.app import create_app` returns `FastAPI` instance with CORS middleware - verified by `TestCreateApp` suite (10 tests)
- [x] `app.state.engine` set after `create_app()` call - verified by `TestAppStateEngine` suite (4 tests)
- [x] All 6 route modules importable - verified by `TestRouteModuleImports` suite (6 tests)
- [x] `from llm_pipeline.ui.deps import get_db, DBSession` succeeds - verified by `TestDeps` suite (7 tests)
- [x] `create_app()` with explicit `db_path` uses that path - verified by `test_db_path_used_in_engine_url`
- [x] `create_app()` without args uses `init_pipeline_db()` default - code path verified in `app.py` else branch
- [x] `pyproject.toml` has `[project.optional-dependencies] ui = [...]` section - verified by `TestPyprojectToml` suite (3 tests)
- [x] 43/43 new tests pass; full suite 511/527 (16 pre-existing failures in `test_retry_ratelimit_events.py` due to missing `google` module, unrelated to this task)
- [x] Architecture review passed (after fixing-review loop)

## Recommendations for Follow-up

1. Add `httpx` to `dev` optional-dependencies. `TestClient` in FastAPI requires `httpx` for endpoint integration tests; downstream tasks 20-25 adding actual endpoints will need it.
2. Downstream tasks 20, 22, 23, 25, 27 build directly on this foundation - each adds endpoints to the relevant router stub and response schemas.
3. WebSocket implementation approach (DB polling vs event bridge) is deferred to the downstream WebSocket task; both options were documented in research.
4. Production CORS origins: `create_app(cors_origins=[...])` parameter is ready for downstream configuration; wildcard default is intentional for development.
5. Verify import guard in a fresh venv: `python -c "from llm_pipeline.ui import create_app"` without FastAPI installed should raise `ImportError` with `pip install llm-pipeline[ui]` hint. This cannot be automated in-process.
6. Consider adding `ReadOnlySession.close()` as a no-op proxy method in a future refactor to eliminate the `session.close()` caveat in `deps.py`.
