"""``llm-pipeline build`` — discover pipelines + validate code↔YAML alignment.

Build is the offline gate. It does NOT touch Phoenix. Failures
indicate a problem with the user's source-of-truth files (code +
YAML); fixing them is on the dev. Phoenix-side reconciliation lives
in ``llm-pipeline pull`` / ``push``.

Public surface:

- :func:`run` — pure Python; pass a :class:`BuildConfig`, get a
  :class:`BuildResult`. Importable from anywhere (UI startup, tests).
- :func:`cli_main` — argparse-based CLI entry; called by the
  top-level dispatcher.
- :func:`add_subparser` — wires the subcommand into a parent
  argparse subparsers (for the eventual unified parser).

Failure modes captured into ``BuildResult.errors``:

- Pipeline discovery error (import failure, no pipelines found, etc.)
- Per-step alignment errors from
  :func:`validate_phoenix_alignment` — registry presence, YAML
  presence/shape, model recognised, placeholder bijection,
  auto_vars expressions, etc.

The single ``errors`` list intentionally collapses both source
categories into one — callers (CLI / UI startup) just want to know
"is anything wrong?", not where in the pipeline of checks the
breakage was. The error strings carry enough context to debug.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


__all__ = [
    "BuildConfig",
    "BuildResult",
    "add_subparser",
    "cli_main",
    "run",
]


_DEFAULT_PROMPTS_DIR = Path("./llm-pipeline-prompts")


@dataclass(frozen=True)
class BuildConfig:
    """Inputs to a build run.

    ``prompts_dir`` is the directory of YAML prompts the validator
    reads. ``pipeline_modules`` is an optional list of dotted module
    paths to import (mirrors the ``--pipelines`` flag). ``demo``
    enables both entry-point and package-internal convention discovery
    (the bundled demo pipeline and prompts).
    """

    prompts_dir: Path
    pipeline_modules: list[str] | None = None
    demo: bool = False


@dataclass
class BuildResult:
    """Outputs of a build run.

    ``pipelines`` lists the snake-cased names of every pipeline
    discovered (and validated). ``errors`` lists every failure —
    discovery failures + alignment failures — as pre-formatted human-
    readable strings. Empty ``errors`` means the build succeeded.
    """

    pipelines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.errors


def run(config: BuildConfig) -> BuildResult:
    """Discover pipelines + run offline alignment validation.

    Per-pipeline / per-step errors are collected into
    ``BuildResult.errors`` rather than raising — the caller decides
    whether one bad pipeline aborts the whole flow. Top-level errors
    (missing ``prompts_dir``) raise :class:`FileNotFoundError`.
    """
    from llm_pipeline.discovery import (
        discover_from_convention,
        discover_from_entry_points,
        discover_from_modules,
    )
    from llm_pipeline.prompts.phoenix_validator import (
        PhoenixValidationFailed,
        validate_phoenix_alignment,
    )

    result = BuildResult()

    prompts_dir = config.prompts_dir.expanduser().resolve()
    if not prompts_dir.is_dir():
        raise FileNotFoundError(
            f"prompts directory not found: {prompts_dir}"
        )

    introspection_registry: dict = {}

    # Discovery is strict in build mode: any import error (including a
    # node / pipeline / PromptVariables ``__init_subclass__`` validator
    # rejecting one of the user's classes) propagates here as a real
    # exception rather than being silently logged. We catch broadly so
    # all three sources contribute their failures to the result rather
    # than the first one short-circuiting.

    if config.demo:
        try:
            _, ep_intro = discover_from_entry_points(strict=True)
            introspection_registry.update(ep_intro)
        except Exception as exc:  # noqa: BLE001 — surface uniformly
            result.errors.append(f"Entry-point discovery failed: {exc}")

    try:
        _, conv_intro = discover_from_convention(
            None, None, include_package=config.demo, strict=True,
        )
        introspection_registry.update(conv_intro)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Convention discovery failed: {exc}")

    if config.pipeline_modules:
        try:
            _, mod_intro = discover_from_modules(config.pipeline_modules)
            introspection_registry.update(mod_intro)
        except ValueError as exc:
            result.errors.append(f"Module load failed: {exc}")

    if not introspection_registry:
        result.errors.append(
            "No pipelines discovered. Pass --pipelines, --demo, or "
            "ensure llm_pipelines/ is on the Python path."
        )
        return result

    result.pipelines = sorted(introspection_registry.keys())

    try:
        validate_phoenix_alignment(introspection_registry, prompts_dir)
    except PhoenixValidationFailed as exc:
        for err in exc.errors:
            result.errors.append(
                f"[{err.pipeline_name}/{err.step_name}] "
                f"{type(err).__name__}: {err}"
            )

    return result


def add_subparser(subparsers: Any) -> None:
    """Wire the ``build`` subcommand into a parent argparse parser."""
    p = subparsers.add_parser(
        "build",
        help=(
            "Discover pipelines and validate code↔YAML alignment. "
            "Offline — does not touch Phoenix."
        ),
    )
    _add_arguments(p)
    p.set_defaults(func=_main)


def cli_main(argv: list[str]) -> int:
    """Standalone CLI entry. ``argv`` excludes the subcommand name."""
    parser = argparse.ArgumentParser(
        prog="llm-pipeline build",
        description=(
            "Discover pipelines and validate code↔YAML alignment. "
            "Offline — does not touch Phoenix. Exits non-zero on any "
            "discovery or validation error."
        ),
    )
    _add_arguments(parser)
    args = parser.parse_args(argv)
    return _main(args)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=None,
        help=(
            "Directory of YAML prompts. Defaults to "
            f"{_DEFAULT_PROMPTS_DIR}."
        ),
    )
    parser.add_argument(
        "--pipelines",
        action="append",
        default=None,
        metavar="MODULE",
        help=(
            "Python module path to scan for Pipeline subclasses "
            "(repeatable). Combined with entry-point and convention "
            "discovery."
        ),
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        default=False,
        help="Include built-in demo pipelines/prompts in the build set.",
    )


def _main(args: argparse.Namespace) -> int:
    """Build a BuildConfig from argparse args, run, print, return code."""
    prompts_dir = args.prompts_dir or _DEFAULT_PROMPTS_DIR
    config = BuildConfig(
        prompts_dir=prompts_dir,
        pipeline_modules=args.pipelines,
        demo=args.demo,
    )

    try:
        result = run(config)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_report(result)
    return 0 if result.is_clean else 1


def _print_report(result: BuildResult) -> None:
    if result.is_clean:
        print(
            f"Build OK: validated {len(result.pipelines)} pipeline(s): "
            f"{', '.join(result.pipelines)}"
        )
        return
    print(
        f"\nBuild failed ({len(result.errors)} error(s)):",
        file=sys.stderr,
    )
    for msg in result.errors:
        print(f"  - {msg}", file=sys.stderr)
