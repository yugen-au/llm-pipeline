"""``llm-pipeline stop`` — kill a running UI server.

Reads the PID file written by ``_run_ui`` and terminates the main
uvicorn process tree (plus the optional Vite dev-server process tree
when running ``--dev``). Then removes the PID file.

The PID file path constant ``_PID_FILE`` and the
``_kill_process_tree`` helper live here because they're the
authoritative source for the stop semantics. The companion writer in
``llm_pipeline.ui.cli._run_ui`` imports them so that the file the UI
writes is the file stop reads.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


__all__ = [
    "StopConfig",
    "StopResult",
    "_PID_FILE",
    "_kill_process_tree",
    "add_subparser",
    "cli_main",
    "run",
]


_PID_FILE = Path(".llm_pipeline") / "ui.pid"


@dataclass(frozen=True)
class StopConfig:
    """Inputs to a stop run.

    No options today — the command reads ``_PID_FILE`` from the
    current working directory. Kept as a dataclass for protocol
    consistency and to make future flags (e.g. ``--force``) trivial
    to add.
    """


@dataclass
class StopResult:
    """Outputs of a stop run.

    ``was_running`` is False when no PID file existed (idempotent
    safety: the desired state was already met). ``killed`` lists the
    process-tree roots stop sent SIGTERM/SIGKILL to. ``errors`` is
    populated when the PID file is malformed or the kill ran into a
    permission issue.
    """

    was_running: bool = False
    killed: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run(config: StopConfig) -> StopResult:
    """Read the PID file, kill the recorded process trees, clean up.

    Idempotent re: a missing PID file — returns
    ``was_running=False`` without raising. Raising is reserved for
    truly unexpected failures (file is unreadable for reasons other
    than absence).
    """
    del config  # no inputs today

    result = StopResult()

    if not _PID_FILE.exists():
        return result

    result.was_running = True

    pids: dict[str, int] = {}
    try:
        for line in _PID_FILE.read_text().strip().splitlines():
            key, _, val = line.partition("=")
            if val:
                pids[key] = int(val)
    except (OSError, ValueError) as exc:
        result.errors.append(f"could not parse PID file: {exc}")
        return result

    main_pid = pids.get("main")
    if not main_pid:
        result.errors.append("PID file missing 'main' entry")
        return result

    _kill_process_tree(main_pid)
    result.killed.append(main_pid)

    vite_pid = pids.get("vite")
    if vite_pid:
        _kill_process_tree(vite_pid)
        result.killed.append(vite_pid)

    try:
        _PID_FILE.unlink(missing_ok=True)
    except OSError:
        # Cosmetic — server is dead either way; PID file is the
        # cookie, not the source of truth.
        pass

    return result


def add_subparser(subparsers: Any) -> None:
    """Wire the ``stop`` subcommand into a parent argparse parser."""
    p = subparsers.add_parser(
        "stop",
        help=(
            "Stop a running UI server (kills the process tree and "
            "removes the PID file)."
        ),
    )
    p.set_defaults(func=_main)


def cli_main(argv: list[str]) -> int:
    """Standalone CLI entry. ``argv`` excludes the subcommand name."""
    parser = argparse.ArgumentParser(
        prog="llm-pipeline stop",
        description=(
            "Stop a running UI server. Reads .llm_pipeline/ui.pid in "
            "the current directory; kills the recorded process tree "
            "(uvicorn + optional Vite) and removes the file. Exits "
            "non-zero when no UI is running."
        ),
    )
    args = parser.parse_args(argv)
    return _main(args)


# ---------------------------------------------------------------------------
# Internals — also imported by _run_ui in llm_pipeline.ui.cli
# ---------------------------------------------------------------------------


def _kill_process_tree(pid: int) -> None:
    """Kill ``pid`` and all descendants via psutil (cross-platform)."""
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


def _main(args: argparse.Namespace) -> int:
    del args  # no flags today
    result = run(StopConfig())

    if result.errors:
        for msg in result.errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        return 1

    if not result.was_running:
        print(
            "No running UI server found (no PID file)",
            file=sys.stderr,
        )
        return 1

    main_pid = result.killed[0] if result.killed else None
    if main_pid is not None:
        print(f"Stopping UI server (PID {main_pid})...")
    print("Stopped.")
    return 0
