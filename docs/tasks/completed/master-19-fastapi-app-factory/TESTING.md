# Testing Results

## Summary
**Status:** passed
All 43 new ui tests pass. Existing test suite unchanged (16 pre-existing failures in test_retry_ratelimit_events.py due to missing `google` module - unrelated to this task, present before task 19).

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| test_ui.py | Full ui package coverage: import guard, app factory, CORS, engine wiring, route stubs, deps | tests/test_ui.py |

### Test Execution
**Pass Rate:** 43/43 new tests (468/484 overall - 16 pre-existing failures unrelated to task)
```
tests/test_ui.py::TestImportGuard::test_create_app_importable_from_package PASSED
tests/test_ui.py::TestImportGuard::test_import_guard_exports_create_app PASSED
tests/test_ui.py::TestCreateApp::test_returns_fastapi_instance PASSED
tests/test_ui.py::TestCreateApp::test_app_title PASSED
tests/test_ui.py::TestCreateApp::test_cors_middleware_attached PASSED
tests/test_ui.py::TestCreateApp::test_cors_default_origins_wildcard PASSED
tests/test_ui.py::TestCreateApp::test_cors_custom_origins PASSED
tests/test_ui.py::TestCreateApp::test_cors_credentials_false PASSED
tests/test_ui.py::TestCreateApp::test_cors_allow_all_methods PASSED
tests/test_ui.py::TestCreateApp::test_cors_allow_all_headers PASSED
tests/test_ui.py::TestAppStateEngine::test_engine_on_state_with_db_path PASSED
tests/test_ui.py::TestAppStateEngine::test_engine_is_sqlalchemy_engine PASSED
tests/test_ui.py::TestAppStateEngine::test_distinct_engines_per_app PASSED
tests/test_ui.py::TestAppStateEngine::test_db_path_used_in_engine_url PASSED
tests/test_ui.py::TestRoutersIncluded::test_six_routers_included PASSED
tests/test_ui.py::TestRoutersIncluded::test_runs_router_mounted_under_api PASSED
tests/test_ui.py::TestRoutersIncluded::test_steps_router_prefix PASSED
tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix PASSED
tests/test_ui.py::TestRoutersIncluded::test_prompts_router_prefix PASSED
tests/test_ui.py::TestRoutersIncluded::test_pipelines_router_prefix PASSED
tests/test_ui.py::TestRoutersIncluded::test_websocket_router_no_prefix PASSED
tests/test_ui.py::TestRoutersIncluded::test_runs_router_tag PASSED
tests/test_ui.py::TestRoutersIncluded::test_steps_router_tag PASSED
tests/test_ui.py::TestRoutersIncluded::test_events_router_tag PASSED
tests/test_ui.py::TestRoutersIncluded::test_prompts_router_tag PASSED
tests/test_ui.py::TestRoutersIncluded::test_pipelines_router_tag PASSED
tests/test_ui.py::TestRoutersIncluded::test_websocket_router_tag PASSED
tests/test_ui.py::TestRouteModuleImports::test_runs_importable PASSED
tests/test_ui.py::TestRouteModuleImports::test_steps_importable PASSED
tests/test_ui.py::TestRouteModuleImports::test_events_importable PASSED
tests/test_ui.py::TestRouteModuleImports::test_prompts_importable PASSED
tests/test_ui.py::TestRouteModuleImports::test_pipelines_importable PASSED
tests/test_ui.py::TestRouteModuleImports::test_websocket_importable PASSED
tests/test_ui.py::TestDeps::test_get_db_importable PASSED
tests/test_ui.py::TestDeps::test_dbsession_importable PASSED
tests/test_ui.py::TestDeps::test_deps_all_exports PASSED
tests/test_ui.py::TestDeps::test_get_db_is_generator PASSED
tests/test_ui.py::TestDeps::test_get_db_yields_readonly_session PASSED
tests/test_ui.py::TestDeps::test_get_db_closes_underlying_session PASSED
tests/test_ui.py::TestDeps::test_dbsession_annotated_with_depends PASSED
tests/test_ui.py::TestPyprojectToml::test_ui_optional_dep_group_exists PASSED
tests/test_ui.py::TestPyprojectToml::test_ui_group_contains_fastapi PASSED
tests/test_ui.py::TestPyprojectToml::test_ui_group_contains_uvicorn PASSED

43 passed in 1.94s
```

### Failed Tests
None

## Build Verification
- [x] Package imports without error (`from llm_pipeline.ui import create_app`)
- [x] `from llm_pipeline.ui.app import create_app` succeeds
- [x] All 6 route modules import cleanly
- [x] `from llm_pipeline.ui.deps import get_db, DBSession` succeeds
- [x] pyproject.toml parses correctly (tomllib round-trip in tests)
- [x] No import errors or warnings in test collection

## Success Criteria (from PLAN.md)
- [x] `from llm_pipeline.ui import create_app` raises ImportError when fastapi not installed, with install hint - import guard verified via __init__.py code inspection; guard is module-level try/except raising with correct message
- [x] `from llm_pipeline.ui.app import create_app` returns FastAPI instance with CORS middleware attached - verified by TestCreateApp suite
- [x] `app.state.engine` is set after `create_app()` call - verified by TestAppStateEngine suite
- [x] All 6 route modules importable: `from llm_pipeline.ui.routes.runs import router` etc. - verified by TestRouteModuleImports suite
- [x] `from llm_pipeline.ui.deps import get_db, DBSession` succeeds - verified by TestDeps suite
- [x] `create_app()` with explicit `db_path` uses that path (not env var default) - verified by test_db_path_used_in_engine_url
- [x] `create_app()` without args uses `init_pipeline_db()` default - code path verified in app.py (else branch calls init_pipeline_db() with no args)
- [x] pyproject.toml has `[project.optional-dependencies] ui = [...]` section - verified by TestPyprojectToml suite

## Human Validation Required
### Verify import guard fires when FastAPI absent
**Step:** Step 2
**Instructions:** Create a fresh venv without fastapi installed, then run `python -c "from llm_pipeline.ui import create_app"`. Should raise ImportError with message containing "pip install llm-pipeline[ui]".
**Expected Result:** ImportError with hint message. Cannot be automated in-process since fastapi is installed in the test environment.

### Verify create_app() default db_path uses env var / filesystem default
**Step:** Step 3
**Instructions:** In a shell with no LLM_PIPELINE_DB env var set, run `python -c "from llm_pipeline.ui.app import create_app; app = create_app(); print(app.state.engine.url)"`. Check URL points to `.llm_pipeline/pipeline.db` relative to cwd.
**Expected Result:** URL like `sqlite:///.../.llm_pipeline/pipeline.db`.

## Issues Found
None

## Recommendations
1. ~~Add fastapi and uvicorn to dev optional-dependencies~~ - done in review fixes (fastapi>=0.100 and uvicorn[standard]>=0.20 now in dev group).
2. Consider adding httpx as dev dep for future route endpoint tests (TestClient requires httpx).

---

## Re-run After Review Fixes (2026-02-19)

### Changes Verified
1. pyproject.toml: fastapi>=0.100 and uvicorn[standard]>=0.20 added to dev optional-dependencies group
2. llm_pipeline/ui/app.py: create_engine import changed from sqlalchemy to sqlmodel; comment added re: init_pipeline_db global side-effect

### Full Suite Results
**Pass Rate:** 511/527 (43 ui + 468 pre-existing passing; 16 pre-existing failures unchanged - all in test_retry_ratelimit_events.py due to missing google module, unrelated to task 19)
```
16 failed, 511 passed, 1 warning in 11.10s
```
All 43 ui tests still pass. No regressions introduced by review fixes.
