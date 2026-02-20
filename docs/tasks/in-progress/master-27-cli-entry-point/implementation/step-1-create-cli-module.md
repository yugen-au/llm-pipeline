# IMPLEMENTATION - STEP 1: CREATE CLI MODULE
**Status:** completed

## Summary
Created `llm_pipeline/ui/cli.py` with subparsers-based argparse CLI. Implements `main()` dispatching `ui` subcommand to prod or dev mode, with Vite subprocess management for frontend dev, static file serving for prod, and headless fallback when no frontend directory exists.

## Files
**Created:** `llm_pipeline/ui/cli.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/cli.py`
New file. Key functions:

- `main()` - argparse with `ui` subcommand (--dev, --port, --db). No subcommand prints help, exits 1.
- `_run_ui(args)` - deferred import of `create_app`, dispatches to prod/dev mode.
- `_run_prod_mode(app, port)` - mounts StaticFiles from `frontend/dist/` if exists, else stderr warning. Binds `0.0.0.0`.
- `_run_dev_mode(app, port)` - auto-detects `frontend/` dir. If present: Vite mode. If absent: uvicorn reload on `127.0.0.1`.
- `_start_vite_mode(app, port, frontend_dir)` - npx check, vite subprocess on port+1, atexit + SIGTERM + try/finally cleanup.
- `_start_vite(frontend_dir, vite_port, api_port)` - Popen with VITE_PORT/VITE_API_PORT env vars, `shell=(sys.platform == "win32")`.
- `_cleanup_vite(proc)` - terminate if alive, wait(5), kill on timeout.

All FastAPI/uvicorn imports deferred to function bodies. Only stdlib at module level.

## Decisions
### StaticFiles import source
**Choice:** Import `StaticFiles` from `starlette.staticfiles` instead of `fastapi.staticfiles`
**Rationale:** FastAPI re-exports from Starlette; importing directly avoids an unnecessary indirection layer. Both work identically since FastAPI depends on Starlette.

### type: ignore comments
**Choice:** Added `# type: ignore` for `uvicorn.run(app, ...)` and `app.mount(...)` calls
**Rationale:** The `app` parameter is typed as `object` in function signatures (to avoid importing FastAPI at module level). The actual runtime type is always `FastAPI` but mypy can't verify this with deferred imports.

## Verification
[x] Syntax check passes (`ast.parse`)
[x] Module imports without triggering FastAPI import guard
[x] `main` is callable
[x] All existing tests pass (1 pre-existing failure unrelated to this change: `test_events_router_prefix`)
[x] No FastAPI/uvicorn imports at module level
[x] All stdlib imports only at top of file
