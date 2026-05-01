"""CLI entry point for llm-pipeline."""
from __future__ import annotations

import argparse
import atexit
import os
import signal
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


_PID_FILE = Path(".llm_pipeline") / "ui.pid"


def main() -> None:
    load_dotenv()
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
    ui_parser.add_argument(
        "--model", type=str, default=None, help="Default LLM model string"
    )
    ui_parser.add_argument(
        "--pipelines",
        action="append",
        default=None,
        metavar="MODULE",
        help="Python module path to scan for PipelineConfig subclasses (repeatable)",
    )
    ui_parser.add_argument(
        "--prompts-dir",
        type=str,
        default=None,
        help=(
            "Directory of YAML prompt files synced bidirectionally with "
            "Phoenix on boot and after every UI save. Defaults to "
            "./llm-pipeline-prompts (skipped if missing)."
        ),
    )
    ui_parser.add_argument(
        "--evals-dir",
        type=str,
        default=None,
        help=(
            "Directory of YAML eval-dataset files synced bidirectionally "
            "with Phoenix on boot and after every UI save. Defaults to "
            "./llm-pipeline-evals (skipped if missing)."
        ),
    )
    ui_parser.add_argument(
        "--demo",
        action="store_true",
        default=False,
        help="Enable demo mode (load built-in demo pipelines and prompts)",
    )

    sub.add_parser("stop", help="Stop a running UI server")

    build_parser = sub.add_parser(
        "build",
        help=(
            "Validate code/YAML/Phoenix alignment + push code-derived "
            "fields. Run from CI / pre-commit / pre-deploy. Exits non-zero "
            "on misalignment."
        ),
    )
    build_parser.add_argument(
        "--db", type=str, default=None, help="Path to SQLite database file",
    )
    build_parser.add_argument(
        "--pipelines",
        action="append",
        default=None,
        metavar="MODULE",
        help=(
            "Python module path to scan for Pipeline subclasses (repeatable). "
            "Combined with entry-point and convention discovery."
        ),
    )
    build_parser.add_argument(
        "--prompts-dir",
        type=str,
        default=None,
        help=(
            "Directory of YAML prompt files. Defaults to "
            "./llm-pipeline-prompts."
        ),
    )
    build_parser.add_argument(
        "--evals-dir",
        type=str,
        default=None,
        help=(
            "Directory of YAML eval-dataset files. Defaults to "
            "./llm-pipeline-evals."
        ),
    )
    build_parser.add_argument(
        "--demo",
        action="store_true",
        default=False,
        help="Include built-in demo pipelines/prompts in the build set",
    )

    eval_parser = sub.add_parser("eval", help="Run an evaluation dataset")
    eval_parser.add_argument(
        "dataset_name", help="Name of the evaluation dataset to run"
    )
    eval_parser.add_argument(
        "--db", type=str, default=None, help="Path to SQLite database file"
    )
    eval_parser.add_argument(
        "--model", type=str, default=None, help="LLM model string"
    )
    eval_parser.add_argument(
        "--pipelines",
        action="append",
        default=None,
        metavar="MODULE",
        help="Python module path to scan for PipelineConfig subclasses (repeatable)",
    )

    args = parser.parse_args()

    if args.command == "ui":
        _run_ui(args)
    elif args.command == "stop":
        _stop_ui()
    elif args.command == "build":
        _run_build(args)
    elif args.command == "eval":
        _run_eval(args)
    else:
        parser.print_help()
        sys.exit(1)


def _write_pid_file(vite_pid: int | None = None) -> None:
    """Write main + vite PIDs to file for stop command."""
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    pids = {"main": os.getpid()}
    if vite_pid:
        pids["vite"] = vite_pid
    _PID_FILE.write_text(
        "\n".join(f"{k}={v}" for k, v in pids.items()) + "\n"
    )
    atexit.register(_remove_pid_file)


def _remove_pid_file() -> None:
    """Clean up PID file on exit."""
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _kill_process_tree(pid: int) -> None:
    """Kill a process and all its children using psutil (cross-platform)."""
    import psutil
    try:
        proc = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    children = proc.children(recursive=True)
    for child in children:
        try:
            child.terminate()
        except psutil.NoSuchProcess:
            pass
    try:
        proc.terminate()
    except psutil.NoSuchProcess:
        pass
    _, alive = psutil.wait_procs(children + [proc], timeout=3)
    for p in alive:
        try:
            p.kill()
        except psutil.NoSuchProcess:
            pass


def _stop_ui() -> None:
    """Stop a running UI server by reading the PID file."""
    if not _PID_FILE.exists():
        print("No running UI server found (no PID file)", file=sys.stderr)
        sys.exit(1)

    pids = {}
    for line in _PID_FILE.read_text().strip().splitlines():
        key, _, val = line.partition("=")
        if val:
            pids[key] = int(val)

    main_pid = pids.get("main")
    if not main_pid:
        print("Invalid PID file", file=sys.stderr)
        sys.exit(1)

    print(f"Stopping UI server (PID {main_pid})...")

    # Kill main process tree (uvicorn reloader + worker)
    _kill_process_tree(main_pid)

    # Kill vite process tree
    vite_pid = pids.get("vite")
    if vite_pid:
        _kill_process_tree(vite_pid)

    # Clean up PID file
    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        pass

    print("Stopped.")


def _run_ui(args: argparse.Namespace) -> None:
    """Create the FastAPI app and dispatch to prod or dev mode."""
    try:
        if args.dev:
            _run_dev_mode(args)
        else:
            from llm_pipeline.ui.app import create_app

            app = create_app(
                db_path=args.db,
                default_model=args.model,
                pipeline_modules=args.pipelines,
                demo_mode=args.demo,
                prompts_dir=args.prompts_dir,
                datasets_dir=args.evals_dir,
            )
            _write_pid_file()
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
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
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
    """Run in dev mode with hot reload for both frontend (Vite) and backend (uvicorn)."""
    # Pass config via env vars so the factory can pick them up on reload
    if args.db:
        os.environ["LLM_PIPELINE_DB"] = args.db
    if args.model:
        os.environ["LLM_PIPELINE_MODEL"] = args.model
    if args.pipelines:
        os.environ["LLM_PIPELINE_PIPELINES"] = ",".join(args.pipelines)
    prompts_dir = getattr(args, "prompts_dir", None)
    if isinstance(prompts_dir, str) and prompts_dir:
        os.environ["LLM_PIPELINE_PROMPTS_DIR"] = prompts_dir
    evals_dir = getattr(args, "evals_dir", None)
    if isinstance(evals_dir, str) and evals_dir:
        os.environ["LLM_PIPELINE_EVALS_DIR"] = evals_dir
    if getattr(args, "demo", False):
        os.environ["LLM_PIPELINE_DEMO_MODE"] = "true"

    frontend_dir = Path(__file__).resolve().parent / "frontend"
    vite_proc = None

    if frontend_dir.exists():
        # Check npx availability
        npx = _resolve_npx()
        try:
            subprocess.run([npx, "--version"], capture_output=True)
        except FileNotFoundError:
            print("ERROR: npx not found; install Node.js to use dev mode", file=sys.stderr)
            sys.exit(1)

        # Auto-install deps if node_modules missing or lockfile changed
        import shutil
        npm = shutil.which("npm") or shutil.which("npm.cmd") or "npm"
        node_modules = frontend_dir / "node_modules"
        lock_file = frontend_dir / "package-lock.json"
        stamp_file = node_modules / ".install_hash"
        lock_hash = ""
        if lock_file.exists():
            import hashlib
            lock_hash = hashlib.sha256(lock_file.read_bytes()).hexdigest()[:16]
        existing_hash = stamp_file.read_text().strip() if stamp_file.exists() else ""
        if not node_modules.exists() or lock_hash != existing_hash:
            print("Installing frontend dependencies...", file=sys.stderr)
            subprocess.run(
                [npm, "install"],
                cwd=str(frontend_dir),
                check=True,
            )
            if lock_hash:
                stamp_file.write_text(lock_hash)

        vite_port = args.port + 1
        vite_proc = _start_vite(frontend_dir, vite_port, args.port)
        _write_pid_file(vite_pid=vite_proc.pid)
        atexit.register(_cleanup_vite, vite_proc)

        if hasattr(signal, "SIGTERM"):
            signal.signal(
                signal.SIGTERM,
                lambda s, f: (_cleanup_vite(vite_proc), sys.exit(0)),
            )

        print(
            f"Vite dev server: http://localhost:{vite_port}\n"
            f"FastAPI server:  http://127.0.0.1:{args.port}\n"
            f"Open the Vite URL in your browser.",
            file=sys.stderr,
        )
    else:
        print(
            "INFO: No frontend/ directory found; starting in headless reload mode",
            file=sys.stderr,
        )

    import uvicorn

    try:
        uvicorn.run(
            "llm_pipeline.ui.cli:_create_dev_app",
            factory=True,
            host="127.0.0.1",
            port=args.port,
            reload=True,
            reload_dirs=[str(Path(__file__).resolve().parent.parent)],
        )
    finally:
        if vite_proc is not None:
            _cleanup_vite(vite_proc)


def _create_dev_app() -> object:
    """Factory for uvicorn reload mode; reads config from env vars."""
    from llm_pipeline.ui.app import create_app

    db_path = os.environ.get("LLM_PIPELINE_DB")
    database_url = os.environ.get("LLM_PIPELINE_DATABASE_URL")
    model = os.environ.get("LLM_PIPELINE_MODEL")
    pipeline_modules_raw = os.environ.get("LLM_PIPELINE_PIPELINES")
    pipeline_modules = pipeline_modules_raw.split(",") if pipeline_modules_raw else None
    return create_app(
        db_path=db_path,
        database_url=database_url,
        default_model=model,
        pipeline_modules=pipeline_modules,
    )



def _run_eval(args: argparse.Namespace) -> None:
    """Run an evaluation dataset by id (Phoenix-backed).

    Phase-3 of the evals migration moved datasets/experiments to
    Phoenix. The CLI here is a thin convenience wrapper around
    ``llm_pipeline.evals.run_dataset``; the dataset lookup is now by
    Phoenix dataset id, not local YAML/DB name.
    """
    import asyncio

    from llm_pipeline.db import init_pipeline_db
    from llm_pipeline.evals import Variant, run_dataset

    if args.db:
        from sqlalchemy import create_engine
        engine = init_pipeline_db(create_engine(f"sqlite:///{args.db}"))
    else:
        engine = init_pipeline_db()

    pipeline_registry: dict = {}
    if args.pipelines:
        from llm_pipeline.discovery import discover_from_modules
        pipeline_registry, _ = discover_from_modules(args.pipelines)

    from llm_pipeline.discovery import discover_from_convention
    conv_pipeline, _ = discover_from_convention(
        engine, args.model, include_package=False,
    )
    pipeline_registry = {**conv_pipeline, **pipeline_registry}

    try:
        report = asyncio.run(run_dataset(
            args.dataset_name,
            Variant(),
            pipeline_registry=pipeline_registry,
            model=args.model,
            engine=engine,
        ))
    except Exception as exc:
        print(f"ERROR: eval run failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Eval report: {report.name}")
    print(f"  Cases:    {len(report.cases)}")
    print(f"  Failures: {len(report.failures)}")


def _run_build(args: argparse.Namespace) -> None:
    """Validate code/YAML/Phoenix alignment and push code-owned fields.

    Build is the gate that runs in CI / pre-commit / pre-deploy. It:

    1. Discovers pipelines (entry points + convention + ``--pipelines``).
    2. Resolves the YAML directories.
    3. Pushes YAML → Phoenix for messages / model / response_format /
       tools (``yaml_sync.startup_sync``).
    4. Validates code↔YAML↔Phoenix alignment in build mode
       (``phoenix_validator.validate_phoenix_alignment``). Throws
       ``PhoenixValidationFailed`` on any error; build exits non-zero.

    Phoenix unreachable is fatal in build mode by design.
    """
    import os
    from pathlib import Path

    from sqlalchemy import create_engine

    from llm_pipeline.db import init_pipeline_db

    if args.db:
        engine = init_pipeline_db(create_engine(f"sqlite:///{args.db}"))
    else:
        engine = init_pipeline_db()

    # Discover pipelines using the same merge order as create_app:
    # entry points (when --demo) < convention < --pipelines modules.
    from llm_pipeline.discovery import discover_from_convention
    from llm_pipeline.discovery import (
        discover_from_entry_points,
        discover_from_modules,
    )

    introspection_registry: dict = {}
    if args.demo:
        _, ep_intro = discover_from_entry_points()
        introspection_registry.update(ep_intro)

    _, conv_intro = discover_from_convention(
        engine, None, include_package=args.demo,
    )
    introspection_registry.update(conv_intro)

    if args.pipelines:
        _, mod_intro = discover_from_modules(args.pipelines)
        introspection_registry.update(mod_intro)

    if not introspection_registry:
        print(
            "ERROR: no pipelines discovered. Pass --pipelines, --demo, or "
            "ensure your llm_pipelines/ folder is on the Python path.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve YAML directories.
    def _resolve_dir(arg_value: str | None, env_var: str, default: str) -> Path | None:
        raw = arg_value if arg_value is not None else os.environ.get(env_var)
        if raw is None:
            raw = default
        raw = raw.strip()
        if not raw:
            return None
        return Path(raw).expanduser()

    prompts_dir = _resolve_dir(
        args.prompts_dir, "LLM_PIPELINE_PROMPTS_DIR", "./llm-pipeline-prompts",
    )
    datasets_dir = _resolve_dir(
        args.evals_dir, "LLM_PIPELINE_EVALS_DIR", "./llm-pipeline-evals",
    )

    if prompts_dir is None:
        print(
            "ERROR: prompts_dir is required for build (set --prompts-dir or "
            "LLM_PIPELINE_PROMPTS_DIR).",
            file=sys.stderr,
        )
        sys.exit(1)

    # Construct Phoenix clients eagerly. Build is fatal if Phoenix is
    # unreachable.
    from llm_pipeline.prompts.phoenix_client import PhoenixError, PhoenixPromptClient

    try:
        prompt_client = PhoenixPromptClient()
    except PhoenixError as exc:
        print(
            f"ERROR: Phoenix prompt client unavailable: {exc}\n"
            f"Set PHOENIX_BASE_URL / PHOENIX_API_KEY before running build.",
            file=sys.stderr,
        )
        sys.exit(1)

    dataset_client = None
    if datasets_dir is not None:
        try:
            from llm_pipeline.evals.phoenix_client import PhoenixDatasetClient

            dataset_client = PhoenixDatasetClient()
        except Exception as exc:
            print(
                f"WARNING: Phoenix dataset client unavailable, dataset "
                f"sync will be skipped: {exc}",
                file=sys.stderr,
            )
            dataset_client = None

    # Step 1: yaml_sync push (prompts + datasets). YAML is the codebase
    # declaration; this propagates edits to Phoenix.
    from llm_pipeline.yaml_sync import startup_sync

    sync_report = startup_sync(
        prompts_dir=prompts_dir,
        datasets_dir=datasets_dir,
        prompt_client=prompt_client,
        dataset_client=dataset_client,
        introspection_registry=introspection_registry,
    )

    if sync_report.prompts_pushed or sync_report.datasets_created or sync_report.datasets_diffed:
        print(
            f"YAML → Phoenix: prompts pushed={len(sync_report.prompts_pushed)} "
            f"skipped={len(sync_report.prompts_skipped)} "
            f"failed={len(sync_report.prompts_failed)}; "
            f"datasets created={len(sync_report.datasets_created)} "
            f"diffed={len(sync_report.datasets_diffed)} "
            f"skipped={len(sync_report.datasets_skipped)} "
            f"failed={len(sync_report.datasets_failed)}",
        )

    if sync_report.prompts_failed or sync_report.datasets_failed:
        for name, msg in sync_report.prompts_failed:
            print(
                f"ERROR: YAML prompt {name} sync failed: {msg}",
                file=sys.stderr,
            )
        for name, msg in sync_report.datasets_failed:
            print(
                f"ERROR: YAML dataset {name} sync failed: {msg}",
                file=sys.stderr,
            )
        sys.exit(1)

    # Step 2: offline alignment validator. Throws on any code↔YAML
    # misalignment.
    from llm_pipeline.prompts.phoenix_validator import (
        PhoenixValidationFailed,
        validate_phoenix_alignment,
    )

    try:
        validate_phoenix_alignment(
            introspection_registry,
            prompts_dir,
        )
    except PhoenixValidationFailed as exc:
        print(f"\n{exc}\n", file=sys.stderr)
        sys.exit(1)

    print(
        f"Build OK: validated {len(introspection_registry)} pipeline(s).",
    )


def _resolve_npx() -> str:
    """Return full path to npx to avoid needing shell=True."""
    import shutil
    npx = shutil.which("npx")
    if npx:
        return npx
    # Windows: npx.cmd is on PATH but shutil.which may need the extension
    if sys.platform == "win32":
        npx = shutil.which("npx.cmd")
        if npx:
            return npx
    return "npx"


def _start_vite(
    frontend_dir: Path, vite_port: int, api_port: int
) -> subprocess.Popen:  # type: ignore[type-arg]
    """Launch vite dev server as a subprocess.

    Avoids shell=True so proc.terminate() kills node directly
    (no wrapper sh/cmd.exe process to orphan children).
    """
    env = {**os.environ, "VITE_PORT": str(vite_port), "VITE_API_PORT": str(api_port)}
    npx = _resolve_npx()
    cmd = [npx, "vite", "--host", "127.0.0.1", "--port", str(vite_port)]
    return subprocess.Popen(cmd, cwd=str(frontend_dir), env=env)


def _cleanup_vite(proc: subprocess.Popen) -> None:  # type: ignore[type-arg]
    """Terminate vite subprocess if still running."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


if __name__ == "__main__":
    main()
