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
