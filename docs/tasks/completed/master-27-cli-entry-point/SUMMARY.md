# Task Summary

## Work Completed

Created the `llm-pipeline` CLI entry point (`llm_pipeline/ui/cli.py`) with a `ui` subcommand that launches the FastAPI app via uvicorn. Supports production mode (binds `0.0.0.0`, mounts `StaticFiles` from `frontend/dist/` when present) and dev mode (auto-detects `frontend/` directory: if present starts Vite subprocess on `port+1` with FastAPI on `port`; if absent falls back to `uvicorn --reload` using `factory=True` import string via `_create_dev_app`). Subprocess lifecycle managed with `atexit` + `try/finally` + SIGTERM handler (Unix). Created full test suite with 42 tests covering all code paths.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/cli.py` | CLI entry point: `main()`, `_run_ui`, `_run_prod_mode`, `_run_dev_mode`, `_start_vite_mode`, `_start_vite`, `_cleanup_vite`, `_create_dev_app` factory |
| `tests/ui/test_cli.py` | 42 tests covering prod mode, dev mode (with/without frontend), cleanup, SIGTERM handler, `_create_dev_app` factory |
| `docs/tasks/in-progress/master-27-cli-entry-point/implementation/step-1-create-cli-module.md` | Implementation notes for cli.py (auto-generated) |
| `docs/tasks/in-progress/master-27-cli-entry-point/implementation/step-2-create-cli-tests.md` | Implementation notes for test_cli.py (auto-generated) |

### Modified
| File | Changes |
| --- | --- |
| None | No existing files modified |

## Commits Made

| Hash | Message |
| --- | --- |
| `2d801b6` | docs(implementation-A): master-27-cli-entry-point |
| `33d1d8d` | docs(implementation-B): master-27-cli-entry-point |
| `4700ac6` | docs(fixing-review-A): master-27-cli-entry-point |
| `ff8a055` | docs(fixing-review-B): master-27-cli-entry-point |

Note: Implementation code (`cli.py`, `test_cli.py`) was committed within the docs commits per the task workflow convention. No separate `feat:` commit was created for this task.

## Deviations from Plan

- `_run_dev_mode` signature changed from `(app, port)` to `(args)` after the reload fix -- the headless path no longer pre-creates the app; it defers to `_create_dev_app` factory. PLAN.md described the original signature; the fix required restructuring `_run_ui` dispatch logic accordingly.
- `_create_dev_app()` factory function added (not in PLAN.md) to support `uvicorn factory=True` reload mode; reads `db_path` from `LLM_PIPELINE_DB` env var (consistent with existing project convention).

## Issues Encountered

### uvicorn reload=True with app instance does not reload
**Resolution:** Changed headless dev mode to pass import string `"llm_pipeline.ui.cli:_create_dev_app"` with `factory=True` to `uvicorn.run`. `db_path` is threaded through via `LLM_PIPELINE_DB` env var set before uvicorn launch. Fix committed in `4700ac6`.

### Path.exists patch overly broad in tests
**Resolution:** Replaced global `patch("pathlib.Path.exists", return_value=...)` with a targeted `_path_exists_side_effect` helper that intercepts only `frontend/` and `dist/` path checks and delegates all others to the real `Path.exists`. Three named convenience constructors (`_only_frontend_missing`, `_only_dist_missing`, `_both_present`) used at call sites. Fixed in `ff8a055`.

### No test for SIGTERM handler registration
**Resolution:** Added `test_sigterm_handler_registered_on_unix` and `test_sigterm_handler_skipped_when_no_sigterm`. The latter uses `MagicMock(spec=["signal"])` to simulate a signal module without `SIGTERM`, exercising the Windows guard branch. Fixed in `ff8a055`.

### No test coverage for _create_dev_app factory
**Resolution:** Added `TestCreateDevApp` class with 3 tests (env var passthrough, None default, return value), plus `test_uvicorn_called_with_factory_true` and `test_uvicorn_first_arg_is_factory_import_string` in `TestDevModeNoFrontend`. Fixed in `ff8a055`.

## Success Criteria

- [x] `llm_pipeline/ui/cli.py` exists with `main()` callable -- confirmed
- [x] `main()` dispatches `ui` subcommand via subparsers; prints help and exits 1 with no subcommand -- covered by `TestMainNoSubcommand` (2 tests pass)
- [x] Prod mode: mounts StaticFiles from `frontend/dist/` when exists; stderr warning when absent -- covered by `TestProdModeNoStaticFiles` + `TestProdModeWithStaticFiles` (9 tests pass)
- [x] Prod mode: binds `0.0.0.0`, default port 8642 -- `test_host_is_0000` and `test_default_port_8642` pass
- [x] Dev mode with frontend/: starts Vite on `port+1`, FastAPI on `port` via `127.0.0.1`; cleanup via atexit + try/finally -- covered by `TestDevModeWithFrontend` (9 tests pass)
- [x] Dev mode without frontend/: falls back to `uvicorn --reload` headless mode with info message -- covered by `TestDevModeNoFrontend` (4 tests pass); reload uses `factory=True` with import string
- [x] `--db` flag passes path to `create_app(db_path=...)` -- `test_db_path_passed_to_create_app` and `test_db_none_by_default` pass
- [x] `--port` flag overrides default 8642 -- `test_custom_port_passed_to_uvicorn` and `test_custom_port_vite_port_incremented` pass
- [x] All FastAPI/uvicorn imports deferred to function bodies -- verified; module imports with stdlib only at top level
- [x] `tests/ui/test_cli.py` exists with tests for all code paths -- 42 tests in 9 classes, all pass
- [x] All existing tests continue to pass -- 675/676 pass; 1 pre-existing failure (`test_events_router_prefix`) unrelated to this task

## Recommendations for Follow-up

1. Add `[project.scripts]` entry in `pyproject.toml` mapping `llm-pipeline = "llm_pipeline.ui.cli:main"` (task 28 per PLAN.md scope note).
2. Fix pre-existing `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` -- router prefix changed in a prior task and the test expectation was not updated.
3. Fix flaky `tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal` -- SQLite WAL PRAGMA state bleed across 600+ tests; add engine teardown or `@pytest.mark.isolated`.
4. Replace `app: object` type annotations in `cli.py` with `TYPE_CHECKING`-guarded `FastAPI` import to eliminate `# type: ignore` comments (low-priority polish).
5. Add a `--host` CLI flag to allow callers to override the default host binding per mode (currently hardcoded to `0.0.0.0` / `127.0.0.1`).
