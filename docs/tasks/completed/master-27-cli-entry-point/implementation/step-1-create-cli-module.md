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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] HIGH: `uvicorn.run(app, reload=True)` with app instance doesn't reload - uvicorn needs import string

### Changes Made
#### File: `llm_pipeline/ui/cli.py`
Refactored `_run_dev_mode` and `_run_ui` to fix reload. Added `_create_dev_app` factory.

```
# Before
def _run_ui(args):
    app = create_app(db_path=args.db)
    if args.dev:
        _run_dev_mode(app, args.port)
    ...

def _run_dev_mode(app, port):
    ...
    uvicorn.run(app, host="127.0.0.1", port=port, reload=True)

# After
def _run_ui(args):
    if args.dev:
        _run_dev_mode(args)           # pass full args, no app creation yet
    else:
        app = create_app(db_path=args.db)
        _run_prod_mode(app, args.port)

def _run_dev_mode(args):
    ...
    # headless reload path: env var for db, import string + factory=True
    if args.db:
        os.environ["LLM_PIPELINE_DB"] = args.db
    uvicorn.run(
        "llm_pipeline.ui.cli:_create_dev_app",
        factory=True,
        host="127.0.0.1", port=args.port, reload=True,
    )

def _create_dev_app():
    """Factory for uvicorn reload mode; reads config from env vars."""
    db_path = os.environ.get("LLM_PIPELINE_DB")
    return create_app(db_path=db_path)
```

Key changes:
- `_run_dev_mode` now receives full `args` (not `app, port`) so it can defer app creation
- Headless reload path uses import string `"llm_pipeline.ui.cli:_create_dev_app"` with `factory=True`
- `--db` value passed via `LLM_PIPELINE_DB` env var so factory picks it up on each reload
- Vite dev path still creates app directly (no reload needed there)

### Verification
[x] Syntax check passes
[x] Module imports without triggering FastAPI guard
[x] `_create_dev_app` callable and importable by string
[x] 625 tests pass (pre-existing `test_events_router_prefix` excluded)
