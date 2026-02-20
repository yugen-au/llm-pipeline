# Step 2: FastAPI + Uvicorn Patterns Research

## 1. Existing App Factory (create_app)

`llm_pipeline/ui/app.py` already provides the factory. Key signature:

```python
def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None,
) -> FastAPI:
```

**CLI wiring**: CLI passes `args.db` as `db_path`. Other params use defaults (wildcard CORS, empty registries). The factory handles engine creation, CORS middleware, and router mounting internally.

**No modifications to create_app needed** for basic CLI support. For production static file serving, the factory needs a conditional `app.mount("/", StaticFiles(...), name="spa")` call -- see section 3.

## 2. Uvicorn Programmatic API

### 2a. uvicorn.run() -- Simple Blocking

```python
import uvicorn
uvicorn.run(app, host="0.0.0.0", port=8642)
```

- Blocking call, starts event loop internally
- Handles SIGINT/SIGTERM for graceful shutdown natively
- Configurable `timeout_graceful_shutdown` (seconds to wait before force-kill)
- `timeout_keep_alive` defaults to 5s
- Best for: production mode (single process, no subprocess coordination)

### 2b. uvicorn.Config + Server -- More Control

```python
config = uvicorn.Config(app, host="0.0.0.0", port=8642, log_level="info")
server = uvicorn.Server(config)
server.run()  # blocking
```

- `server.run()` is blocking (equivalent to `uvicorn.run()`)
- `await server.serve()` is async (for integration with existing event loop)
- Useful when needing pre-start configuration or async orchestration
- `server.should_exit` flag can be checked for coordinated shutdown

### 2c. Async Server (for advanced dev mode)

```python
async def main():
    config = uvicorn.Config(app, port=8642)
    server = uvicorn.Server(config)
    await server.serve()

asyncio.run(main())
```

- Runs inside existing async context
- Enables combining uvicorn with other async tasks (e.g., subprocess monitoring)
- Not needed for basic implementation -- `uvicorn.run()` suffices

### Recommendation

**Production**: `uvicorn.run(app, host="0.0.0.0", port=port)` -- simplest, handles signals.

**Dev mode**: `uvicorn.run(app, host="127.0.0.1", port=port)` with Vite subprocess started before the blocking call. `uvicorn.run` handles shutdown; subprocess cleanup via `atexit` + `try/finally`.

Binding to `127.0.0.1` in dev mode is intentional -- only Vite (on port+1) needs to reach FastAPI, not external clients.

## 3. Production Mode: Static File Serving

### Pattern: StaticFiles with html=True for SPA

```python
from fastapi.staticfiles import StaticFiles

# Mount AFTER all API/WS routes (catch-all at "/")
app.mount("/", StaticFiles(directory=dist_path, html=True), name="spa")
```

- `html=True` enables SPA behavior: serves `index.html` for directory requests and as fallback for paths not matching static files
- Must be mounted **last** -- "/" catches all unmatched routes
- Route priority: FastAPI routes (including `/api/*` and `/ws/*`) are checked before mounts

### Locating dist/ Directory

Options for finding the built frontend assets:

```python
import importlib.resources
# Option A: relative to ui package
ui_pkg_dir = Path(__file__).resolve().parent
dist_path = ui_pkg_dir / "frontend" / "dist"

# Option B: importlib.resources (Python 3.11+)
# More correct for installed packages but complex for directory access
```

**Recommendation**: `Path(__file__).resolve().parent / "frontend" / "dist"` -- simple, works for both editable installs and regular installs. Validate existence before mounting; skip with warning if dist/ not found (allows API-only mode).

### Integration with create_app

The factory currently has a commented-out static files mount. For CLI integration, two approaches:

**Option A**: Add `static_dir` parameter to `create_app()`:
```python
def create_app(db_path=None, ..., static_dir: Optional[str] = None):
    # ... existing setup ...
    if static_dir:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="spa")
    return app
```

**Option B**: Mount static files in CLI after `create_app()`:
```python
app = create_app(db_path=args.db)
if not args.dev:
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=dist_path, html=True), name="spa")
```

Option B keeps create_app() focused and puts mode-specific logic in the CLI. Slightly cleaner separation.

## 4. Dev Mode: Vite Subprocess Architecture

### Proxy Direction

- **User opens**: `http://localhost:{port+1}` (Vite dev server)
- **Vite serves**: frontend with HMR on port+1
- **Vite proxies**: `/api/*` and `/ws/*` requests to FastAPI on port
- **FastAPI runs**: on port, serving only API and WebSocket endpoints

This is the standard Vite dev proxy pattern. Users interact with Vite's port; API calls are transparently proxied.

### Vite Proxy Config (vite.config.ts -- frontend responsibility)

The frontend project (separate task) will have:
```ts
export default defineConfig({
  server: {
    port: parseInt(process.env.VITE_PORT || "8643"),
    proxy: {
      "/api": {
        target: `http://localhost:${process.env.VITE_API_PORT || "8642"}`,
        changeOrigin: true,
      },
      "/ws": {
        target: `http://localhost:${process.env.VITE_API_PORT || "8642"}`,
        ws: true,
      },
    },
  },
});
```

The CLI passes ports via environment variables to the Vite subprocess.

### Frontend Directory Location

Dev mode needs the Vite source project directory:
```python
frontend_dir = Path(__file__).resolve().parent / "frontend"
```

Expected structure (created by future frontend task):
```
llm_pipeline/ui/frontend/
  package.json
  vite.config.ts
  src/
  dist/          # built assets (production)
```

## 5. Subprocess Management

### Starting Vite

```python
import subprocess
import os

def _start_vite(frontend_dir: Path, vite_port: int, api_port: int) -> subprocess.Popen:
    env = {
        **os.environ,
        "VITE_PORT": str(vite_port),
        "VITE_API_PORT": str(api_port),
    }
    proc = subprocess.Popen(
        ["npx", "vite", "--port", str(vite_port)],
        cwd=str(frontend_dir),
        env=env,
        # stdout/stderr: let Vite output flow to terminal
    )
    return proc
```

**Command choice**: `npx vite` is universal (works without global install). Alternative: detect package manager from lock files (package-lock.json -> npm, pnpm-lock.yaml -> pnpm, yarn.lock -> yarn).

**Windows note**: On Windows, `npx` resolves to `npx.cmd`. Use `shell=True` or detect platform:
```python
import sys
cmd = ["npx", "vite", "--port", str(vite_port)]
if sys.platform == "win32":
    # subprocess needs shell=True on Windows for .cmd scripts
    # OR use shutil.which("npx") to find full path
    pass
```

Simplest cross-platform approach: `shell=True` on Windows only.

### Monitoring

```python
def _check_vite_alive(proc: subprocess.Popen) -> bool:
    return proc.poll() is None
```

Monitoring can be passive (check on shutdown) or active (background thread polling). Passive is sufficient for MVP -- if Vite crashes, API still works; user sees frontend error in browser.

### Cleanup

```python
import atexit
import signal

def _cleanup_vite(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

# Register cleanup
atexit.register(_cleanup_vite, vite_proc)
```

`atexit` handlers run on normal interpreter exit and SIGINT (KeyboardInterrupt). They do NOT run on SIGTERM or SIGKILL on Unix. For SIGTERM coverage:

```python
def _signal_handler(signum, frame):
    _cleanup_vite(vite_proc)
    sys.exit(0)

# Unix only (SIGTERM not available on Windows)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, _signal_handler)
```

On Windows, `atexit` + Ctrl+C (SIGINT/KeyboardInterrupt) covers the main shutdown path. No SIGTERM needed.

## 6. Signal Handling & Graceful Shutdown

### Production Mode

Uvicorn handles everything:
- SIGINT (Ctrl+C): triggers graceful shutdown
- SIGTERM: triggers graceful shutdown
- Configurable `timeout_graceful_shutdown` for maximum wait
- Existing connections are drained before exit

No custom signal handling needed.

### Dev Mode

```python
def start_dev_mode(app: FastAPI, port: int) -> None:
    frontend_dir = Path(__file__).resolve().parent / "frontend"
    if not frontend_dir.exists():
        print("Error: frontend directory not found at", frontend_dir, file=sys.stderr)
        sys.exit(1)

    vite_port = port + 1
    vite_proc = _start_vite(frontend_dir, vite_port, port)
    atexit.register(_cleanup_vite, vite_proc)

    print(f"Vite dev server: http://localhost:{vite_port}")
    print(f"FastAPI server:  http://localhost:{port}")
    print(f"Open http://localhost:{vite_port} in your browser")

    try:
        uvicorn.run(app, host="127.0.0.1", port=port)
    finally:
        _cleanup_vite(vite_proc)
```

The `try/finally` ensures Vite cleanup even if uvicorn exits abnormally. The `atexit` handler is a belt-and-suspenders backup.

### Shutdown Flow (Dev Mode)

1. User presses Ctrl+C
2. uvicorn catches SIGINT, begins graceful shutdown
3. uvicorn.run() returns
4. `finally` block calls `_cleanup_vite()`
5. Vite subprocess terminated via `proc.terminate()` + `proc.wait(5)`
6. Python interpreter exits
7. `atexit` handler fires (no-op since Vite already cleaned up via `proc.poll() is None` check)

## 7. Recommended CLI Structure

```python
# llm_pipeline/ui/cli.py

import argparse
import atexit
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="llm-pipeline",
        description="LLM Pipeline CLI",
    )
    sub = parser.add_subparsers(dest="command")

    ui_parser = sub.add_parser("ui", help="Start the UI server")
    ui_parser.add_argument("--dev", action="store_true", help="Dev mode with Vite HMR")
    ui_parser.add_argument("--port", type=int, default=8642, help="Server port (default: 8642)")
    ui_parser.add_argument("--db", type=str, default=None, help="SQLite database path")

    args = parser.parse_args()

    if args.command == "ui":
        _run_ui(args)
    else:
        parser.print_help()
        sys.exit(1)

def _run_ui(args) -> None:
    from llm_pipeline.ui.app import create_app
    app = create_app(db_path=args.db)

    if args.dev:
        _run_dev_mode(app, args.port)
    else:
        _run_prod_mode(app, args.port)

def _run_prod_mode(app, port: int) -> None:
    import uvicorn
    from fastapi.staticfiles import StaticFiles

    dist_dir = Path(__file__).resolve().parent / "frontend" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="spa")
    else:
        print(f"Warning: {dist_dir} not found, serving API only", file=sys.stderr)

    uvicorn.run(app, host="0.0.0.0", port=port)

def _run_dev_mode(app, port: int) -> None:
    import uvicorn

    frontend_dir = Path(__file__).resolve().parent / "frontend"
    if not frontend_dir.exists():
        print(f"Error: frontend directory not found: {frontend_dir}", file=sys.stderr)
        sys.exit(1)

    vite_port = port + 1
    vite_proc = _start_vite(frontend_dir, vite_port, port)
    atexit.register(_cleanup_vite, vite_proc)

    print(f"Vite dev server: http://localhost:{vite_port}")
    print(f"FastAPI server:  http://localhost:{port}")

    try:
        uvicorn.run(app, host="127.0.0.1", port=port)
    finally:
        _cleanup_vite(vite_proc)
```

### Why argparse with subparsers

- `llm-pipeline ui --dev --port 8642` reads naturally
- Subparsers allow future commands (`llm-pipeline run <pipeline>`, `llm-pipeline migrate`, etc.)
- No external dependencies (unlike click/typer)
- Matches task 27 specification

### pyproject.toml Entry Point (Task 28 scope)

```toml
[project.scripts]
llm-pipeline = "llm_pipeline.ui.cli:main"
```

Note: The `[project.scripts]` addition is task 28's responsibility, NOT task 27. Task 27 creates the cli.py module; task 28 wires it into pyproject.toml.

## 8. Lifespan Events (Alternative Pattern)

FastAPI's `lifespan` context manager could manage Vite subprocess lifecycle:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: Vite already started before app creation
    yield
    # shutdown: cleanup Vite
    _cleanup_vite(app.state.vite_proc)

app = FastAPI(lifespan=lifespan)
```

**Not recommended** for this use case because:
1. Vite subprocess is a CLI concern, not an app concern
2. Mixing subprocess management into the ASGI app makes testing harder
3. `try/finally` around `uvicorn.run()` is simpler and more explicit
4. Lifespan is better suited for app-level resources (DB connections, caches)

## 9. Cross-Platform Considerations

| Concern | Unix | Windows |
|---------|------|---------|
| SIGTERM handling | `signal.signal(signal.SIGTERM, handler)` | Not available |
| SIGINT (Ctrl+C) | Works | Works |
| atexit handlers | Run on SIGINT, normal exit | Run on SIGINT, normal exit |
| npx command | `npx` binary | `npx.cmd` -- needs `shell=True` or full path |
| Process termination | `proc.terminate()` sends SIGTERM | `proc.terminate()` calls TerminateProcess |
| Process kill | `proc.kill()` sends SIGKILL | `proc.kill()` same as terminate |

### Windows-safe subprocess launch:

```python
def _start_vite(frontend_dir: Path, vite_port: int, api_port: int) -> subprocess.Popen:
    env = {**os.environ, "VITE_PORT": str(vite_port), "VITE_API_PORT": str(api_port)}
    cmd = ["npx", "vite", "--port", str(vite_port)]
    return subprocess.Popen(
        cmd,
        cwd=str(frontend_dir),
        env=env,
        shell=(sys.platform == "win32"),
    )
```

## 10. Key Decisions Summary

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Uvicorn API | `uvicorn.run()` (blocking) | Simplest, handles signals, sufficient for both modes |
| Static files | `StaticFiles(html=True)` mounted after create_app | SPA support, clean separation from factory |
| Subprocess start | `subprocess.Popen` with `npx vite` | Universal, no global install required |
| Subprocess cleanup | `atexit` + `try/finally` | Belt-and-suspenders, covers SIGINT + normal exit |
| Dev mode binding | `127.0.0.1` | Only Vite needs access; user hits Vite's port |
| Prod mode binding | `0.0.0.0` | Accept external connections |
| CLI framework | argparse with subparsers | No deps, extensible, matches task spec |
| Frontend dir | `Path(__file__).parent / "frontend"` | Simple, works in editable + regular installs |
| Proxy direction | User -> Vite (port+1) -> FastAPI (port) | Standard Vite dev proxy pattern |

## Sources

- FastAPI docs: lifespan events, StaticFiles, CORSMiddleware (Context7 /websites/fastapi_tiangolo)
- Uvicorn docs: programmatic API, graceful shutdown, timeouts (Context7 /encode/uvicorn)
- Existing codebase: llm_pipeline/ui/app.py (create_app factory), llm_pipeline/ui/routes/websocket.py (WS pattern)
- Task 19 upstream summary: SUMMARY.md, VALIDATED_RESEARCH.md
- Task 27 specification: task master details
- Task 28 specification (downstream, out of scope): pyproject.toml entry point wiring
