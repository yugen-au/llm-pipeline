"""``llm-pipeline push`` — YAML+code → Phoenix.

Publishes the local source-of-truth state to Phoenix:

- **Prompt message text + model** from YAML (these are
  ``Phoenix-owned`` at runtime, but YAML is the codebase-tracked
  declaration; pushing keeps Phoenix in sync with the committed YAML).
- **response_format / tools** derived from each step's
  ``INSTRUCTIONS`` / ``DEFAULT_TOOLS`` (code-owned).
- **variable_definitions** derived from the YAML's
  ``metadata.variable_definitions`` (matches what
  ``llm-pipeline generate`` consumed).
- **Eval datasets** when ``--evals-dir`` is set.

Push is **step-driven** for prompts (only steps registered in the
discovered pipelines get their prompts pushed). Phoenix-only or
orphan prompts in YAML are not pushed; they stay local artifacts.

Push auto-creates Phoenix records that don't yet exist — this is
how a fresh Phoenix is bootstrapped from the codebase.

No validation runs here; cross-checks live in ``build`` (offline)
and fire BEFORE push so structural drift is surfaced before any
Phoenix mutation.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


__all__ = [
    "PushConfig",
    "PushResult",
    "add_subparser",
    "cli_main",
    "run",
]


_DEFAULT_PROMPTS_DIR = Path("./llm-pipeline-prompts")
_DEFAULT_EVALS_DIR = Path("./llm-pipeline-evals")


@dataclass(frozen=True)
class PushConfig:
    """Inputs to a push run.

    ``prompts_dir`` is required. ``evals_dir`` is optional; if the
    directory doesn't exist on disk, dataset push is silently skipped
    (lets users keep eval YAMLs out of the repo).
    """

    prompts_dir: Path
    evals_dir: Path | None = None
    pipeline_modules: list[str] | None = None
    demo: bool = False


@dataclass
class PushResult:
    """Outputs of a push run.

    Each list contains the names of items affected:

    - ``prompts_pushed`` — Phoenix updated (or created) for these.
    - ``prompts_unchanged`` — YAML hash matched Phoenix; no write.
    - ``prompts_failed`` — per-prompt push failures.
    - ``datasets_created`` / ``datasets_diffed`` /
      ``datasets_unchanged`` / ``datasets_failed`` — same idea for
      eval datasets when ``evals_dir`` is set.
    - ``discovery_errors`` — pre-flight failures (broken module,
      Phoenix unreachable, no pipelines).

    ``is_clean`` is True only when *nothing changed* and *nothing
    failed*. The UI startup dry-run gate reads this property.
    """

    prompts_pushed: list[str] = field(default_factory=list)
    prompts_unchanged: list[str] = field(default_factory=list)
    prompts_failed: list[tuple[str, str]] = field(default_factory=list)
    datasets_created: list[str] = field(default_factory=list)
    datasets_diffed: list[str] = field(default_factory=list)
    datasets_unchanged: list[str] = field(default_factory=list)
    datasets_failed: list[tuple[str, str]] = field(default_factory=list)
    discovery_errors: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return (
            not self.prompts_pushed
            and not self.prompts_failed
            and not self.datasets_created
            and not self.datasets_diffed
            and not self.datasets_failed
            and not self.discovery_errors
        )


def run(config: PushConfig) -> PushResult:
    """Discover pipelines, construct Phoenix clients, push prompts + datasets.

    Top-level errors (missing prompts_dir) raise
    :class:`FileNotFoundError`. Discovery and Phoenix-construction
    failures are recorded as ``discovery_errors``; per-prompt /
    per-dataset failures land in their respective ``*_failed`` lists.
    """
    from llm_pipeline.discovery import (
        discover_from_convention,
        discover_from_entry_points,
        discover_from_modules,
    )

    result = PushResult()

    prompts_dir = config.prompts_dir.expanduser().resolve()
    if not prompts_dir.is_dir():
        raise FileNotFoundError(
            f"prompts directory not found: {prompts_dir}"
        )

    evals_dir: Path | None = None
    if config.evals_dir is not None:
        candidate = config.evals_dir.expanduser().resolve()
        if candidate.is_dir():
            evals_dir = candidate
        # else: silently skip dataset push — caller didn't write YAMLs.

    # Step-driven discovery (strict — broken modules are fatal).
    introspection_registry: dict = {}
    if config.demo:
        try:
            _, ep_intro = discover_from_entry_points(strict=True)
            introspection_registry.update(ep_intro)
        except Exception as exc:  # noqa: BLE001
            result.discovery_errors.append(
                f"Entry-point discovery failed: {exc}"
            )
    try:
        _, conv_intro = discover_from_convention(
            None, None, include_package=config.demo, strict=True,
        )
        introspection_registry.update(conv_intro)
    except Exception as exc:  # noqa: BLE001
        result.discovery_errors.append(
            f"Convention discovery failed: {exc}"
        )
    if config.pipeline_modules:
        try:
            _, mod_intro = discover_from_modules(config.pipeline_modules)
            introspection_registry.update(mod_intro)
        except ValueError as exc:
            result.discovery_errors.append(f"Module load failed: {exc}")

    if not introspection_registry:
        result.discovery_errors.append(
            "No pipelines discovered. Pass --pipelines, --demo, or "
            "ensure llm_pipelines/ is on the Python path."
        )
        return result

    # Phoenix prompt client — required for any push.
    from llm_pipeline.prompts.phoenix_client import (
        PhoenixError,
        PhoenixPromptClient,
    )
    try:
        prompt_client = PhoenixPromptClient()
    except PhoenixError as exc:
        result.discovery_errors.append(
            f"Phoenix prompt client unavailable: {exc}. Set "
            f"PHOENIX_BASE_URL / PHOENIX_API_KEY before running push."
        )
        return result

    # Phoenix dataset client — optional, only if evals_dir is set.
    dataset_client = None
    if evals_dir is not None:
        try:
            from llm_pipeline.evals.phoenix_client import PhoenixDatasetClient

            dataset_client = PhoenixDatasetClient()
        except Exception as exc:  # noqa: BLE001 — datasets are auxiliary
            result.discovery_errors.append(
                f"Phoenix dataset client unavailable: {exc}. "
                f"Datasets will not be pushed."
            )
            # Fall through; prompts can still push even if datasets can't.

    from llm_pipeline.yaml_sync import startup_sync

    sync_report = startup_sync(
        prompts_dir=prompts_dir,
        datasets_dir=evals_dir,
        prompt_client=prompt_client,
        dataset_client=dataset_client,
        introspection_registry=introspection_registry,
    )

    result.prompts_pushed = list(sync_report.prompts_pushed)
    result.prompts_unchanged = list(sync_report.prompts_skipped)
    result.prompts_failed = list(sync_report.prompts_failed)
    result.datasets_created = list(sync_report.datasets_created)
    result.datasets_diffed = list(sync_report.datasets_diffed)
    result.datasets_unchanged = list(sync_report.datasets_skipped)
    result.datasets_failed = list(sync_report.datasets_failed)
    return result


def add_subparser(subparsers: Any) -> None:
    """Wire the ``push`` subcommand into a parent argparse parser."""
    p = subparsers.add_parser(
        "push",
        help=(
            "Push YAML + code-derived fields to Phoenix. Step-driven "
            "for prompts; auto-creates Phoenix records for new steps."
        ),
    )
    _add_arguments(p)
    p.set_defaults(func=_main)


def cli_main(argv: list[str]) -> int:
    """Standalone CLI entry. ``argv`` excludes the subcommand name."""
    parser = argparse.ArgumentParser(
        prog="llm-pipeline push",
        description=(
            "Push YAML + code-derived fields to Phoenix for every "
            "discovered step. Auto-creates Phoenix records that don't "
            "exist yet. Exits non-zero on any discovery or transport "
            "failure."
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
            "Directory of YAML prompts (source). Defaults to "
            f"{_DEFAULT_PROMPTS_DIR}."
        ),
    )
    parser.add_argument(
        "--evals-dir",
        type=Path,
        default=None,
        help=(
            "Directory of YAML eval datasets. Defaults to "
            f"{_DEFAULT_EVALS_DIR}. Skipped if the directory doesn't "
            "exist."
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
        help="Include built-in demo pipelines/prompts in the push set.",
    )


def _main(args: argparse.Namespace) -> int:
    prompts_dir = args.prompts_dir or _DEFAULT_PROMPTS_DIR
    evals_dir = args.evals_dir or _DEFAULT_EVALS_DIR
    config = PushConfig(
        prompts_dir=prompts_dir,
        evals_dir=evals_dir,
        pipeline_modules=args.pipelines,
        demo=args.demo,
    )

    try:
        result = run(config)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_report(result)
    return 0 if (
        not result.discovery_errors
        and not result.prompts_failed
        and not result.datasets_failed
    ) else 1


def _print_report(result: PushResult) -> None:
    if result.discovery_errors:
        print(
            f"Push aborted ({len(result.discovery_errors)} pre-flight "
            f"error(s)):",
            file=sys.stderr,
        )
        for msg in result.discovery_errors:
            print(f"  - {msg}", file=sys.stderr)
        return

    if result.prompts_pushed:
        print(f"Pushed {len(result.prompts_pushed)} prompt(s) to Phoenix:")
        for name in result.prompts_pushed:
            print(f"  WROTE   {name}")
    if result.prompts_unchanged:
        print(
            f"Unchanged: {len(result.prompts_unchanged)} prompt(s) "
            f"(Phoenix hash matched)"
        )
    if result.prompts_failed:
        print(
            f"\nFailed: {len(result.prompts_failed)} prompt(s):",
            file=sys.stderr,
        )
        for name, reason in result.prompts_failed:
            print(f"  FAIL    {name}: {reason}", file=sys.stderr)

    if (
        result.datasets_created
        or result.datasets_diffed
        or result.datasets_unchanged
    ):
        print(
            f"Datasets: created={len(result.datasets_created)} "
            f"diffed={len(result.datasets_diffed)} "
            f"unchanged={len(result.datasets_unchanged)}"
        )
    if result.datasets_failed:
        print(
            f"\nDataset failures: {len(result.datasets_failed)}",
            file=sys.stderr,
        )
        for name, reason in result.datasets_failed:
            print(f"  FAIL    {name}: {reason}", file=sys.stderr)
