# IMPLEMENTATION - STEP 2: CREATE CLI TESTS
**Status:** completed

## Summary
Created `tests/ui/test_cli.py` with 34 tests covering all code paths in `llm_pipeline/ui/cli.py`. Patch targets were the key challenge: all FastAPI/uvicorn imports in cli.py are deferred (inside function bodies), so patches must target source modules (`uvicorn.run`, `starlette.staticfiles.StaticFiles`, `llm_pipeline.ui.app.create_app`) rather than `llm_pipeline.ui.cli.*` attributes that don't exist at module level.

## Files
**Created:** `tests/ui/test_cli.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/ui/test_cli.py`
New file. 34 tests across 8 test classes.

```
# Before
(file did not exist)

# After
tests/ui/test_cli.py  - 34 tests, 0 failures
```

## Decisions
### Patch targets for deferred imports
**Choice:** Patch at source module (`uvicorn.run`, `starlette.staticfiles.StaticFiles`, `llm_pipeline.ui.app.create_app`) not at `llm_pipeline.ui.cli.*`
**Rationale:** cli.py does `import uvicorn` inside a function body; at that point Python resolves the name from `sys.modules`, so patching `uvicorn.run` intercepts the call. Patching `llm_pipeline.ui.cli.uvicorn` would fail with AttributeError since `uvicorn` is never bound as a module-level attribute of cli.

### subprocess and atexit patches
**Choice:** Patch `llm_pipeline.ui.cli.subprocess.run`, `llm_pipeline.ui.cli.subprocess.Popen`, and `llm_pipeline.ui.cli.atexit.register`
**Rationale:** `subprocess` and `atexit` ARE imported at module level in cli.py (`import subprocess`, `import atexit`), so they are attributes of the cli module and can be patched there directly.

### Path.exists patching
**Choice:** Patch `pathlib.Path.exists` globally for tests that need filesystem control
**Rationale:** `_run_prod_mode` and `_run_dev_mode` call `.exists()` on `Path` instances constructed inside the function; patching the method on the class intercepts all calls cleanly without needing to inject paths.

### _cleanup_vite patching in dev+vite tests
**Choice:** Patch `llm_pipeline.ui.cli._cleanup_vite` to verify finally-block execution without real subprocess calls
**Rationale:** The real `_cleanup_vite` is tested separately in `TestCleanupVite`; patching it in the full-dev tests isolates concerns and avoids side effects from the mock proc cleanup logic.

## Verification
- [x] 34/34 tests pass (`python -m pytest tests/ui/test_cli.py -q`)
- [x] Full suite: 667 pass, 1 pre-existing failure (`test_events_router_prefix` in `tests/test_ui.py`, unrelated)
- [x] All code paths from PLAN.md Step 2 checklist covered
- [x] No subcommand -> exits 1
- [x] Prod mode no dist/ -> no mount, WARNING to stderr, uvicorn host=0.0.0.0 port=8642
- [x] Prod mode with dist/ -> StaticFiles(html=True) mounted on "/", name="spa"
- [x] Custom --port -> uvicorn called with correct port
- [x] --db flag -> create_app(db_path=...) correct
- [x] Dev no frontend/ -> uvicorn(reload=True, host=127.0.0.1), no Popen, INFO to stderr
- [x] Dev frontend/ npx missing -> SystemExit(1), ERROR to stderr
- [x] Dev frontend/ npx ok -> Popen with VITE_PORT/VITE_API_PORT env, uvicorn 127.0.0.1, atexit registered, finally calls cleanup
- [x] _cleanup_vite: terminate+wait on alive proc, kill on timeout, no-op if dead

---

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
- [x] MEDIUM - Path.exists patch is overly broad (global True/False)
- [x] MEDIUM - No test for SIGTERM handler registration on Unix
- [x] LOW - No test for `_create_dev_app` factory or `factory=True` kwarg

### Changes Made
#### File: `tests/ui/test_cli.py`

**Issue 1: Targeted Path.exists patching**

Replaced all `patch("pathlib.Path.exists", return_value=True/False)` with `patch.object(Path, "exists", side_effect_fn)` where the side_effect checks the path suffix and delegates real behaviour for all other paths.

```
# Before
patch("pathlib.Path.exists", return_value=False)  # patches ALL Path.exists globally

# After
def _path_exists_side_effect(frontend_exists, dist_exists):
    real_exists = Path.exists
    def _side_effect(self):
        if path ends with "frontend": return frontend_exists
        if path ends with "dist": return dist_exists
        return real_exists(self)  # real behaviour for all other paths
    return _side_effect

patch.object(Path, "exists", _only_frontend_missing())  # targeted
```

Three named helpers: `_only_frontend_missing()`, `_only_dist_missing()`, `_both_present()`.

**Issue 2: SIGTERM handler tests**

Added two tests in `TestDevModeWithFrontend`:
- `test_sigterm_handler_registered_on_unix`: `_run_full_dev()` now patches `llm_pipeline.ui.cli.signal` with a `MagicMock` that has `SIGTERM = signal.SIGTERM`; asserts `mock_signal_mod.signal.assert_called_once()` with SIGTERM as first arg.
- `test_sigterm_handler_skipped_when_no_sigterm`: patches `llm_pipeline.ui.cli.signal` with `MagicMock(spec=["signal"])` — a mock with no `SIGTERM` attribute so `hasattr` returns False; asserts `mock_signal_mod.signal.assert_not_called()`.

```
# _run_full_dev now uses:
mock_signal_mod = MagicMock()
mock_signal_mod.SIGTERM = signal.SIGTERM
patch("llm_pipeline.ui.cli.signal", mock_signal_mod)

# skipped-test uses:
mock_signal_mod = MagicMock(spec=["signal"])  # no SIGTERM attr
patch("llm_pipeline.ui.cli.signal", mock_signal_mod)
```

**Issue 3: `_create_dev_app` and headless dev assertions**

- `TestCreateDevApp` (3 tests): verifies env var read, None fallback, return value.
- `TestDevModeNoFrontend` gained 3 new assertions:
  - `test_uvicorn_called_with_factory_true`: `kwargs.get("factory") is True`
  - `test_uvicorn_first_arg_is_factory_import_string`: `args[0] == "llm_pipeline.ui.cli:_create_dev_app"`
  - `test_db_flag_sets_env_var`: captures `os.environ["LLM_PIPELINE_DB"]` inside `patch.dict` context

Also removed `create_app` patch from headless dev tests (cli.py no longer calls `create_app` in that branch; it uses the factory string instead).

### Verification
- [x] 42/42 tests pass (`python -m pytest tests/ui/test_cli.py -q`)
- [x] Full suite: 675 pass, 1 pre-existing failure (unrelated)
