"""CLI entry point for llm-pipeline."""
from __future__ import annotations

import argparse
import atexit
import os
import signal
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Parse arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(prog="llm-pipeline")
    sub = parser.add_subparsers(dest="command")

    ui_parser = sub.add_parser("ui", help="Start the UI server")
    ui_parser.add_argument(
        "--dev", action="store_true", help="Run in development mode"
    )
    ui_parser.add_argument(
        "--port", type=int, default=8642, help="Server port (default: 8642)"
    )
    ui_parser.add_argument(
        "--db", type=str, default=None, help="Path to SQLite database file"
    )

    args = parser.parse_args()

    if args.command == "ui":
        _run_ui(args)
    else:
        parser.print_help()
        sys.exit(1)


def _run_ui(args: argparse.Namespace) -> None:
    """Create the FastAPI app and dispatch to prod or dev mode."""
    try:
        if args.dev:
            _run_dev_mode(args)
        else:
            from llm_pipeline.ui.app import create_app

            app = create_app(db_path=args.db)
            _run_prod_mode(app, args.port)
    except ImportError as e:
        _ui_deps = {"fastapi", "uvicorn", "starlette", "multipart", "python_multipart"}
        if e.name and e.name.split(".")[0] not in _ui_deps:
            raise
        print(
            "ERROR: UI dependencies not installed. Run: pip install llm-pipeline[ui]",
            file=sys.stderr,
        )
        sys.exit(1)


def _run_prod_mode(app: object, port: int) -> None:
    """Run in production mode with optional static file serving."""
    import uvicorn
    from starlette.staticfiles import StaticFiles

    dist_dir = Path(__file__).resolve().parent / "frontend" / "dist"
    if dist_dir.exists():
        app.mount("/", StaticFiles(directory=str(dist_dir), html=True), name="spa")  # type: ignore[union-attr]
    else:
        print(
            "WARNING: frontend/dist/ not found; running in API-only mode",
            file=sys.stderr,
        )

    uvicorn.run(app, host="0.0.0.0", port=port)  # type: ignore[arg-type]


def _run_dev_mode(args: argparse.Namespace) -> None:
    """Run in dev mode: Vite + FastAPI if frontend/ exists, else reload-only."""
    frontend_dir = Path(__file__).resolve().parent / "frontend"
    if frontend_dir.exists():
        from llm_pipeline.ui.app import create_app

        app = create_app(db_path=args.db)
        _start_vite_mode(app, args.port, frontend_dir)
    else:
        print(
            "INFO: No frontend/ directory found; starting in headless reload mode",
            file=sys.stderr,
        )
        # Pass db_path via env var so the factory can pick it up on reload
        if args.db:
            os.environ["LLM_PIPELINE_DB"] = args.db

        import uvicorn

        uvicorn.run(
            "llm_pipeline.ui.cli:_create_dev_app",
            factory=True,
            host="127.0.0.1",
            port=args.port,
            reload=True,
        )


def _create_dev_app() -> object:
    """Factory for uvicorn reload mode; reads config from env vars."""
    from llm_pipeline.ui.app import create_app

    db_path = os.environ.get("LLM_PIPELINE_DB")
    return create_app(db_path=db_path)


def _start_vite_mode(app: object, port: int, frontend_dir: Path) -> None:
    """Start Vite dev server alongside FastAPI."""
    # Check npx availability
    try:
        subprocess.run(
            ["npx", "--version"],
            capture_output=True,
            shell=(sys.platform == "win32"),
        )
    except FileNotFoundError:
        print("ERROR: npx not found; install Node.js to use dev mode", file=sys.stderr)
        sys.exit(1)

    vite_port = port + 1
    vite_proc = _start_vite(frontend_dir, vite_port, port)

    atexit.register(_cleanup_vite, vite_proc)

    if hasattr(signal, "SIGTERM"):
        signal.signal(
            signal.SIGTERM,
            lambda s, f: (_cleanup_vite(vite_proc), sys.exit(0)),
        )

    print(
        f"Vite dev server: http://localhost:{vite_port}\n"
        f"FastAPI server:  http://127.0.0.1:{port}\n"
        f"Open the Vite URL in your browser.",
        file=sys.stderr,
    )

    import uvicorn

    try:
        uvicorn.run(app, host="127.0.0.1", port=port)  # type: ignore[arg-type]
    finally:
        _cleanup_vite(vite_proc)


def _start_vite(
    frontend_dir: Path, vite_port: int, api_port: int
) -> subprocess.Popen:  # type: ignore[type-arg]
    """Launch vite dev server as a subprocess."""
    env = {**os.environ, "VITE_PORT": str(vite_port), "VITE_API_PORT": str(api_port)}
    cmd = ["npx", "vite", "--port", str(vite_port)]
    return subprocess.Popen(
        cmd, cwd=str(frontend_dir), env=env, shell=(sys.platform == "win32")
    )


def _cleanup_vite(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Terminate vite subprocess if still running."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()
