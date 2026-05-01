"""``llm-pipeline pull`` — Phoenix → YAML for steps the codebase knows.

Brings down Phoenix-owned fields (message text, model) for every
prompt that has a paired step in the user's pipelines. Phoenix-only
prompts (no matching step) are deliberately ignored — Phoenix is
storage, the codebase is the source of truth for which prompts
exist.

Pull is **step-driven**: discovery runs first, then for each loaded
step the Phoenix prompt with the matching ``step_name()`` is
fetched and any drift between Phoenix and the local YAML is
written down to YAML.

Failure modes:

- Discovery error (broken module, missing variables file): pull
  cannot run — surfaced as ``discovery_errors`` and the result is
  not clean.
- Phoenix unreachable: surfaced as a ``discovery_errors`` entry
  (the Phoenix client construction failure is functionally a
  pre-flight check).
- Per-prompt fetch / write failures: surfaced as ``prompts_failed``.

No Phoenix-aware validation runs here. Cross-checks live in
``build`` (offline alignment after pull updates the YAML).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


__all__ = [
    "PullConfig",
    "PullResult",
    "add_subparser",
    "cli_main",
    "run",
]


_DEFAULT_PROMPTS_DIR = Path("./llm-pipeline-prompts")


@dataclass(frozen=True)
class PullConfig:
    """Inputs to a pull run.

    ``prompts_dir`` is the YAML directory pulled into.
    ``pipeline_modules`` is an optional ``--pipelines`` list of dotted
    module paths. ``demo`` enables entry-point + package-internal
    convention discovery for the bundled demo pipelines.
    """

    prompts_dir: Path
    pipeline_modules: list[str] | None = None
    demo: bool = False


@dataclass
class PullResult:
    """Outputs of a pull run.

    ``prompts_pulled`` lists prompt names where Phoenix had newer
    state and YAML was updated. ``prompts_unchanged`` lists prompts
    that already matched (no write). ``prompts_failed`` lists per-
    prompt failures (transport, parse, write). ``discovery_errors``
    captures pre-flight failures (discovery broke, Phoenix unreachable).

    ``is_clean`` is True only if nothing changed and nothing failed —
    used by the UI dry-run gate at startup.
    """

    prompts_pulled: list[str] = field(default_factory=list)
    prompts_unchanged: list[str] = field(default_factory=list)
    prompts_failed: list[tuple[str, str]] = field(default_factory=list)
    discovery_errors: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return (
            not self.prompts_pulled
            and not self.prompts_failed
            and not self.discovery_errors
        )


def run(config: PullConfig) -> PullResult:
    """Discover pipelines, construct Phoenix client, pull prompts.

    Top-level errors (missing prompts_dir) raise
    :class:`FileNotFoundError`. Discovery and Phoenix-construction
    failures are recorded as ``discovery_errors`` (not raised);
    per-prompt failures as ``prompts_failed``.
    """
    from llm_pipeline.discovery import (
        discover_from_convention,
        discover_from_entry_points,
        discover_from_modules,
    )

    result = PullResult()

    prompts_dir = config.prompts_dir.expanduser().resolve()
    if not prompts_dir.is_dir():
        raise FileNotFoundError(
            f"prompts directory not found: {prompts_dir}"
        )

    # Step-driven discovery (strict — broken modules are fatal here,
    # not silent log lines).
    introspection_registry: dict = {}
    if config.demo:
        try:
            _, ep_intro = discover_from_entry_points(strict=True)
            introspection_registry.update(ep_intro)
        except Exception as exc:  # noqa: BLE001 — surface uniformly
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
        # Without a step registry, step-driven pull has nothing to do.
        # Treat as a discovery error so the result isn't reported as
        # clean — the user almost certainly wanted to pull something.
        result.discovery_errors.append(
            "No pipelines discovered. Pass --pipelines, --demo, or "
            "ensure llm_pipelines/ is on the Python path."
        )
        return result

    # Phoenix client. Pull is online by definition — Phoenix-unreachable
    # is a pre-flight failure, not a per-prompt one.
    from llm_pipeline.prompts.phoenix_client import (
        PhoenixError,
        PhoenixPromptClient,
    )
    try:
        prompt_client = PhoenixPromptClient()
    except PhoenixError as exc:
        result.discovery_errors.append(
            f"Phoenix prompt client unavailable: {exc}. Set "
            f"PHOENIX_BASE_URL / PHOENIX_API_KEY before running pull."
        )
        return result

    from llm_pipeline.yaml_sync import pull_phoenix_to_yaml

    sync_report = pull_phoenix_to_yaml(
        prompts_dir=prompts_dir,
        prompt_client=prompt_client,
        introspection_registry=introspection_registry,
    )

    result.prompts_pulled = list(sync_report.prompts_pulled)
    result.prompts_unchanged = list(sync_report.prompts_pull_skipped)
    result.prompts_failed = list(sync_report.prompts_pull_failed)
    return result


def add_subparser(subparsers: Any) -> None:
    """Wire the ``pull`` subcommand into a parent argparse parser."""
    p = subparsers.add_parser(
        "pull",
        help=(
            "Pull Phoenix-owned fields (message text, model) for "
            "every step's matching prompt down to YAML on disk. "
            "Step-driven."
        ),
    )
    _add_arguments(p)
    p.set_defaults(func=_main)


def cli_main(argv: list[str]) -> int:
    """Standalone CLI entry. ``argv`` excludes the subcommand name."""
    parser = argparse.ArgumentParser(
        prog="llm-pipeline pull",
        description=(
            "Pull Phoenix-owned prompt fields (message text, model) "
            "into local YAML for every step's matching prompt. "
            "Phoenix-only prompts are ignored. Exits non-zero on any "
            "discovery / transport failure."
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
            "Directory of YAML prompts (target). Defaults to "
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
        help="Include built-in demo pipelines/prompts in the pull set.",
    )


def _main(args: argparse.Namespace) -> int:
    prompts_dir = args.prompts_dir or _DEFAULT_PROMPTS_DIR
    config = PullConfig(
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
    return 0 if (
        not result.discovery_errors and not result.prompts_failed
    ) else 1


def _print_report(result: PullResult) -> None:
    if result.discovery_errors:
        print(
            f"Pull aborted ({len(result.discovery_errors)} pre-flight "
            f"error(s)):",
            file=sys.stderr,
        )
        for msg in result.discovery_errors:
            print(f"  - {msg}", file=sys.stderr)
        return

    if result.prompts_pulled:
        print(f"Pulled {len(result.prompts_pulled)} prompt(s) from Phoenix:")
        for name in result.prompts_pulled:
            print(f"  WROTE   {name}.yaml")
    if result.prompts_unchanged:
        print(
            f"Unchanged: {len(result.prompts_unchanged)} prompt(s) "
            f"(YAML matched Phoenix)"
        )
    if result.prompts_failed:
        print(
            f"\nFailed: {len(result.prompts_failed)} prompt(s):",
            file=sys.stderr,
        )
        for name, reason in result.prompts_failed:
            print(f"  FAIL    {name}: {reason}", file=sys.stderr)
    if (
        not result.prompts_pulled
        and not result.prompts_unchanged
        and not result.prompts_failed
    ):
        print(
            "No prompts pulled. (No discoverable steps had matching "
            "Phoenix prompts to pull.)"
        )
