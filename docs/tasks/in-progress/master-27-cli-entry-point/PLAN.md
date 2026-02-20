# PLANNING

## Summary

Create `llm_pipeline/ui/cli.py` with a `main()` function providing a subparsers-based argparse CLI for the `llm-pipeline` command. The `ui` subcommand launches the FastAPI app via uvicorn in either production mode (static files from `frontend/dist/`, binds `0.0.0.0`) or dev mode (auto-detects `frontend/` directory; if present starts Vite on `port+1` as subprocess with HMR, FastAPI on `port`; if absent falls back to `uvicorn --reload` headless mode). Subprocess lifecycle is managed with `atexit` + `try/finally`. pyproject.toml `[project.scripts]` entry is out of scope (task 28).

## Plugin & Agents

**Plugin:** python-development, backend-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Implementation**: Create `llm_pipeline/ui/cli.py` with all production and dev mode logic
2. **Testing**: Create `tests/ui/test_cli.py` with mocked uvicorn and subprocess, covering all code paths

## Architecture Decisions

### argparse Subparsers

**Choice:** `parser.add_subparsers(dest="command")` with `sub.add_parser("ui")` for the `ui` subcommand
**Rationale:** CEO confirmed subparsers pattern. Extensible for future commands (`llm-pipeline run`, `llm-pipeline migrate`). Idiomatic Python CLI; no external dependencies.
**Alternatives:** Positional `command` argument (step-1 research proposed this; rejected as less extensible). click/typer (external deps, overkill for current scope).

### Static Files: Mount in CLI, Not in create_app

**Choice:** Mount `StaticFiles` in `_run_prod_mode()` in cli.py, after calling `create_app()`
**Rationale:** `create_app()` already has commented-out static mount. Mounting in CLI keeps factory focused on API concerns; mode-specific serving logic stays in the CLI layer. Validated in step-2 research (Option B preference).
**Alternatives:** Add `static_dir` param to `create_app()` (Option A, step-2 research). Rejected: adds CLI-specific concern to a library factory used by programmatic callers.

### Dev Mode: Auto-Detect Frontend Directory

**Choice:** Check `Path(__file__).resolve().parent / "frontend"` existence at runtime; if present launch Vite subprocess, otherwise fall back to `uvicorn --reload` (headless mode) with info message
**Rationale:** CEO confirmed auto-detect behavior. Headless/backend-only is a valid production use case (no frontend required). Avoids hard failure when frontend not yet built.
**Alternatives:** Hard error if `--dev` and no `frontend/` (rejected by CEO). Separate `--headless` flag (not in task spec).

### Subprocess Cleanup: atexit + try/finally

**Choice:** Register `atexit.register(_cleanup_vite, proc)` and wrap `uvicorn.run()` in `try/finally` calling `_cleanup_vite(proc)`
**Rationale:** Belt-and-suspenders. `atexit` fires on `SIGINT`/normal exit; `try/finally` covers any exception path from uvicorn. SIGTERM handler added for Unix only via `signal.signal(signal.SIGTERM, ...)`. Step-2 research confirms this is sufficient.
**Alternatives:** FastAPI lifespan context manager (rejected: subprocess is CLI concern, not app concern; harder to test).

### Windows Cross-Platform Subprocess

**Choice:** `shell=(sys.platform == "win32")` in `subprocess.Popen` for npx invocation
**Rationale:** `npx.cmd` on Windows requires shell resolution. `shell=True` on Windows only avoids security implications on Unix. Step-2 research documents this as the recommended approach.
**Alternatives:** `shutil.which("npx")` to resolve full path (more complex, unnecessary).

### Host Binding

**Choice:** `0.0.0.0` for production, `127.0.0.1` for dev mode
**Rationale:** In dev mode, only Vite (on `port+1`) needs to reach FastAPI; external clients connect to Vite's port. In production, external access is expected. Security-appropriate defaults. Validated in step-2 research and VALIDATED_RESEARCH.md.
**Alternatives:** Always bind `0.0.0.0` (security concern in dev). Configurable `--host` flag (not in task spec, noted as future extension).

## Implementation Steps

### Step 1: Create llm_pipeline/ui/cli.py

**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /encode/uvicorn, /fastapi/fastapi
**Group:** A

1. Create `llm_pipeline/ui/cli.py` with the following structure:
   - Module-level docstring: `"""CLI entry point for llm-pipeline."""`
   - Imports at top: `argparse`, `atexit`, `os`, `signal`, `subprocess`, `sys` from stdlib; `pathlib.Path` from stdlib. All FastAPI/uvicorn imports deferred to function bodies (due to `ui/__init__.py` import guard).
   - `main()` function: builds argparse parser with `prog="llm-pipeline"`, calls `add_subparsers(dest="command")`, creates `ui_parser = sub.add_parser("ui", help="Start the UI server")`, adds `--dev` (store_true), `--port` (int, default=8642), `--db` (str, default=None). Parses args. Dispatches to `_run_ui(args)` if `args.command == "ui"`, else prints help and exits with code 1.
   - `_run_ui(args)` function: imports `create_app` from `llm_pipeline.ui.app` (deferred), constructs `app = create_app(db_path=args.db)`. Dispatches to `_run_dev_mode(app, args.port)` if `args.dev`, else `_run_prod_mode(app, args.port)`.
   - `_run_prod_mode(app, port)` function: imports `uvicorn` and `fastapi.staticfiles.StaticFiles` (deferred). Resolves `dist_dir = Path(__file__).resolve().parent / "frontend" / "dist"`. If `dist_dir.exists()`: mounts `StaticFiles(directory=str(dist_dir), html=True)` on `"/"` with `name="spa"`. Else: prints warning to stderr that dist/ not found and API-only mode is active. Calls `uvicorn.run(app, host="0.0.0.0", port=port)`.
   - `_run_dev_mode(app, port)` function: resolves `frontend_dir = Path(__file__).resolve().parent / "frontend"`. If `frontend_dir.exists()`: calls `_start_vite_mode(app, port, frontend_dir)`. Else: prints info message to stderr that no frontend/ found, starting in headless reload mode. Imports `uvicorn` (deferred). Calls `uvicorn.run(app, host="127.0.0.1", port=port, reload=True)`.
   - `_start_vite_mode(app, port, frontend_dir)` function: checks Node.js/npx availability via `subprocess.run(["npx", "--version"], capture_output=True, shell=(sys.platform == "win32"))`. If check fails, prints error to stderr and exits code 1. Sets `vite_port = port + 1`. Calls `_start_vite(frontend_dir, vite_port, port)` to get `vite_proc`. Registers `atexit.register(_cleanup_vite, vite_proc)`. On Unix, sets SIGTERM handler via `signal.signal(signal.SIGTERM, lambda s, f: (_cleanup_vite(vite_proc), sys.exit(0)))` -- guard with `if hasattr(signal, "SIGTERM")`. Prints startup info: Vite URL on port+1, FastAPI URL on port, instruction to open browser. Imports `uvicorn` (deferred). Wraps `uvicorn.run(app, host="127.0.0.1", port=port)` in `try/finally` calling `_cleanup_vite(vite_proc)`.
   - `_start_vite(frontend_dir, vite_port, api_port)` function: builds `env = {**os.environ, "VITE_PORT": str(vite_port), "VITE_API_PORT": str(api_port)}`. Builds `cmd = ["npx", "vite", "--port", str(vite_port)]`. Returns `subprocess.Popen(cmd, cwd=str(frontend_dir), env=env, shell=(sys.platform == "win32"))`.
   - `_cleanup_vite(proc)` function: checks `proc.poll() is None`. If alive: calls `proc.terminate()`, wraps `proc.wait(timeout=5)` in try/except `subprocess.TimeoutExpired` which calls `proc.kill()`.

### Step 2: Create tests/ui/test_cli.py

**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create `tests/ui/test_cli.py` covering all code paths:
   - Fixture: `mock_create_app` that returns a MagicMock FastAPI app (avoids real DB init).
   - Test `test_no_subcommand_prints_help_and_exits`: patch `sys.argv = ["llm-pipeline"]`, assert `SystemExit(1)` raised.
   - Test `test_ui_subcommand_prod_mode_no_dist`: patch `sys.argv = ["llm-pipeline", "ui"]`, mock `create_app`, mock `uvicorn.run`, mock `Path.exists` to return False. Assert `uvicorn.run` called with `host="0.0.0.0"`, `port=8642`. Assert no `app.mount` called.
   - Test `test_ui_subcommand_prod_mode_with_dist`: as above but `Path.exists` returns True. Assert `app.mount` called once with `"/"` and `StaticFiles` instance with `html=True`.
   - Test `test_ui_subcommand_custom_port`: patch `sys.argv = ["llm-pipeline", "ui", "--port", "9000"]`, assert `uvicorn.run` called with `port=9000`.
   - Test `test_ui_subcommand_dev_no_frontend`: patch `sys.argv = ["llm-pipeline", "ui", "--dev"]`, mock `frontend_dir.exists()` to return False. Assert `uvicorn.run` called with `reload=True`, `host="127.0.0.1"`. Assert no `subprocess.Popen` called.
   - Test `test_ui_subcommand_dev_with_frontend_npx_missing`: mock `frontend_dir.exists()` True, mock `subprocess.run` (npx check) to raise `FileNotFoundError`. Assert `SystemExit(1)`.
   - Test `test_ui_subcommand_dev_with_frontend`: mock `frontend_dir.exists()` True, mock npx check success, mock `subprocess.Popen` returning mock proc with `poll()` returning None. Assert `subprocess.Popen` called with env containing `VITE_PORT` and `VITE_API_PORT`. Assert `uvicorn.run` called with `host="127.0.0.1"`, `port=8642`. Assert `atexit.register` called with `_cleanup_vite`.
   - Test `test_cleanup_vite_terminates_running_proc`: create mock proc with `poll()` returning None, `wait()` succeeding. Call `_cleanup_vite(proc)`. Assert `proc.terminate()` called. Assert `proc.wait(timeout=5)` called.
   - Test `test_cleanup_vite_kills_on_timeout`: mock proc, `wait()` raises `TimeoutExpired`. Assert `proc.kill()` called.
   - Test `test_cleanup_vite_no_op_if_proc_dead`: mock proc with `poll()` returning 0. Call `_cleanup_vite(proc)`. Assert `proc.terminate()` not called.
   - Test `test_db_flag_passed_to_create_app`: patch `sys.argv = ["llm-pipeline", "ui", "--db", "/tmp/test.db"]`, assert `create_app` called with `db_path="/tmp/test.db"`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `ui/__init__.py` import guard raises ImportError at module import time if FastAPI not installed | High | All FastAPI/uvicorn imports deferred to function bodies in cli.py; only stdlib at module level |
| `StaticFiles` mount must come after all API routes or it shadows them | High | Mount in `_run_prod_mode` after `create_app()` returns (routes already included); `"/"` catch-all is last |
| Vite subprocess not cleaned up if uvicorn crashes non-gracefully | Medium | Belt-and-suspenders: atexit + try/finally both call `_cleanup_vite`; `poll()` guard prevents double-terminate |
| Windows npx resolution failure (npx.cmd not found without shell=True) | Medium | `shell=(sys.platform == "win32")` in all subprocess calls |
| Test isolation: real filesystem checks for frontend/ and dist/ | Medium | Patch `Path.exists` or inject path via monkeypatching in tests |
| SIGTERM on Unix not handled by atexit | Low | Explicit `signal.signal(signal.SIGTERM, ...)` handler registered in `_start_vite_mode` (Unix only) |

## Success Criteria

- [ ] `llm_pipeline/ui/cli.py` exists with `main()` callable
- [ ] `main()` dispatches `ui` subcommand via subparsers; prints help and exits 1 with no subcommand
- [ ] Prod mode: mounts StaticFiles from `frontend/dist/` when directory exists; prints stderr warning and serves API-only when dist/ absent
- [ ] Prod mode: binds `0.0.0.0`, default port 8642
- [ ] Dev mode with frontend/: starts Vite subprocess on `port+1`, FastAPI on `port` via `127.0.0.1`; Vite subprocess cleaned up via atexit + try/finally on exit
- [ ] Dev mode without frontend/: falls back to `uvicorn --reload` headless mode with info message, no subprocess
- [ ] `--db` flag passes path to `create_app(db_path=...)`
- [ ] `--port` flag overrides default 8642
- [ ] All FastAPI/uvicorn imports deferred to function bodies (no top-level FastAPI import)
- [ ] `tests/ui/test_cli.py` exists with tests for all code paths
- [ ] All existing tests continue to pass (`pytest`)

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Single new file with no changes to existing modules. All architecture decisions validated by CEO. Patterns fully researched (step-2 research covers every code path). Failure modes are isolated to the CLI layer with no downstream impact on existing API functionality.
**Suggested Exclusions:** testing, review
