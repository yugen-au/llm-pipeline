# Testing Results

## Summary
**Status:** passed

All 34 CLI tests pass. Full suite: 666/668 pass. Both non-CLI failures are pre-existing and unrelated to this task's changes.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| test_cli.py | Full coverage of cli.py - all prod/dev/cleanup code paths | tests/ui/test_cli.py |

### Test Execution
**Pass Rate:** 34/34 (CLI tests); 666/668 (full suite)

CLI-only run:
```
============================= test session starts =============================
platform win32 -- Python 3.13.3, pytest-9.0.2, pluggy-1.6.0
collected 34 items

tests/ui/test_cli.py::TestMainNoSubcommand::test_no_subcommand_exits_1 PASSED
tests/ui/test_cli.py::TestMainNoSubcommand::test_no_subcommand_calls_print_help PASSED
tests/ui/test_cli.py::TestProdModeNoStaticFiles::test_uvicorn_run_called PASSED
tests/ui/test_cli.py::TestProdModeNoStaticFiles::test_host_is_0000 PASSED
tests/ui/test_cli.py::TestProdModeNoStaticFiles::test_default_port_8642 PASSED
tests/ui/test_cli.py::TestProdModeNoStaticFiles::test_no_static_mount_without_dist PASSED
tests/ui/test_cli.py::TestProdModeNoStaticFiles::test_warning_printed_to_stderr PASSED
tests/ui/test_cli.py::TestProdModeWithStaticFiles::test_static_files_mounted_on_root PASSED
tests/ui/test_cli.py::TestProdModeWithStaticFiles::test_static_files_html_true PASSED
tests/ui/test_cli.py::TestProdModeWithStaticFiles::test_uvicorn_still_called PASSED
tests/ui/test_cli.py::TestProdModeWithStaticFiles::test_static_files_name_spa PASSED
tests/ui/test_cli.py::TestCustomPort::test_custom_port_passed_to_uvicorn PASSED
tests/ui/test_cli.py::TestDbFlag::test_db_path_passed_to_create_app PASSED
tests/ui/test_cli.py::TestDbFlag::test_db_none_by_default PASSED
tests/ui/test_cli.py::TestDevModeNoFrontend::test_uvicorn_called_with_reload PASSED
tests/ui/test_cli.py::TestDevModeNoFrontend::test_host_is_loopback PASSED
tests/ui/test_cli.py::TestDevModeNoFrontend::test_no_subprocess_popen_called PASSED
tests/ui/test_cli.py::TestDevModeNoFrontend::test_info_message_printed_to_stderr PASSED
tests/ui/test_cli.py::TestDevModeNpxMissing::test_exits_1_when_npx_missing PASSED
tests/ui/test_cli.py::TestDevModeNpxMissing::test_error_message_printed_to_stderr PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_popen_called PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_popen_env_contains_vite_port PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_popen_env_contains_vite_api_port PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_uvicorn_host_is_loopback PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_uvicorn_default_port PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_atexit_registered_with_cleanup_vite PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_cleanup_called_in_finally PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_custom_port_vite_port_incremented PASSED
tests/ui/test_cli.py::TestDevModeWithFrontend::test_uvicorn_no_reload_in_vite_mode PASSED
tests/ui/test_cli.py::TestCleanupVite::test_terminates_running_proc PASSED
tests/ui/test_cli.py::TestCleanupVite::test_waits_after_terminate PASSED
tests/ui/test_cli.py::TestCleanupVite::test_kills_on_timeout PASSED
tests/ui/test_cli.py::TestCleanupVite::test_no_op_if_proc_dead PASSED
tests/ui/test_cli.py::TestCleanupVite::test_no_kill_if_wait_succeeds PASSED

34 passed in 0.39s
```

Full suite run:
```
2 failed, 666 passed, 1 warning in 13.89s
FAILED tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix
FAILED tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal
```

### Failed Tests
#### test_events_router_prefix
**Step:** pre-existing (before task 27)
**Error:** `AssertionError: assert '/runs/{run_id}/events' == '/events'` - router prefix changed in a prior task; test not updated

#### test_file_based_sqlite_sets_wal
**Step:** pre-existing (environment-flaky in full suite; passes in isolation and at HEAD commit)
**Error:** `AssertionError: assert 'delete' == 'wal'` - SQLite WAL PRAGMA not persisting across engine instances when run after 600+ other tests; confirmed flaky by running test_wal.py in isolation (4/4 pass)

## Build Verification
- [x] `llm_pipeline/ui/cli.py` imports without error (stdlib-only at module level verified)
- [x] `python -c "from llm_pipeline.ui.cli import main, _cleanup_vite"` succeeds
- [x] No FastAPI/uvicorn imports at module level (verified in cli.py lines 1-11)
- [x] All unittest.mock patches target correct deferred import paths

## Success Criteria (from PLAN.md)
- [x] `llm_pipeline/ui/cli.py` exists with `main()` callable - confirmed, file at llm_pipeline/ui/cli.py
- [x] `main()` dispatches `ui` subcommand via subparsers; prints help and exits 1 with no subcommand - covered by TestMainNoSubcommand (2 tests pass)
- [x] Prod mode: mounts StaticFiles from `frontend/dist/` when exists; stderr warning when absent - covered by TestProdModeNoStaticFiles + TestProdModeWithStaticFiles (9 tests pass)
- [x] Prod mode: binds `0.0.0.0`, default port 8642 - test_host_is_0000 and test_default_port_8642 pass
- [x] Dev mode with frontend/: starts Vite on port+1, FastAPI on port via 127.0.0.1; cleanup via atexit + try/finally - covered by TestDevModeWithFrontend (9 tests pass)
- [x] Dev mode without frontend/: falls back to uvicorn --reload headless mode with info message - covered by TestDevModeNoFrontend (4 tests pass)
- [x] `--db` flag passes path to `create_app(db_path=...)` - test_db_path_passed_to_create_app and test_db_none_by_default pass
- [x] `--port` flag overrides default 8642 - test_custom_port_passed_to_uvicorn pass; test_custom_port_vite_port_incremented pass
- [x] All FastAPI/uvicorn imports deferred to function bodies - verified in cli.py, module imports cleanly
- [x] `tests/ui/test_cli.py` exists with tests for all code paths - 34 tests in 8 classes
- [x] All existing tests continue to pass - 2 failures are pre-existing (confirmed by git stash test); no new regressions

## Human Validation Required
### Live CLI invocation
**Step:** Step 1 (cli.py implementation)
**Instructions:** Run `python -m llm_pipeline.ui.cli --help` and `python -m llm_pipeline.ui.cli ui --help` from project root
**Expected Result:** Help text showing `ui` subcommand with `--dev`, `--port`, `--db` flags

## Issues Found
### test_events_router_prefix pre-existing failure
**Severity:** low
**Step:** pre-existing (predates task 27, documented in step-1 implementation notes)
**Details:** Router prefix changed in a prior task; test expectation not updated. Unrelated to CLI module.

### test_file_based_sqlite_sets_wal flaky in full suite
**Severity:** low
**Step:** pre-existing (passes in isolation; fails intermittently in full 668-test run)
**Details:** SQLite WAL PRAGMA silently ignored when engine is reused or test isolation breaks journal mode state. Passes 100% when run alone (`pytest tests/ui/test_wal.py`). No relation to CLI changes.

## Recommendations
1. Update `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` to match actual router prefix `/runs/{run_id}/events` (separate task)
2. Add `@pytest.mark.isolated` or engine teardown to `test_file_based_sqlite_sets_wal` to prevent cross-test WAL state bleed (separate task)
3. No changes required to `llm_pipeline/ui/cli.py` or `tests/ui/test_cli.py` - implementation is correct and complete
