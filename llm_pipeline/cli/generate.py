"""``llm-pipeline generate`` — YAML → ``_variables/_*.py`` codegen.

Walks ``--prompts-dir`` for ``*.yaml`` files; for each, generates the
matching ``_<name>.py`` PromptVariables file in ``--output-dir``.
Idempotent: a file unchanged on disk is left alone (same mtime).

Public surface:

- :func:`run` — pure Python; pass a :class:`GenerateConfig`, get a
  :class:`GenerateResult`. Importable from anywhere (UI, tests).
- :func:`cli_main` — argparse-based CLI entry; called by the
  top-level dispatcher.
- :func:`add_subparser` — wires the subcommand into a parent
  argparse subparsers (for the eventual unified parser).

The function and CLI both read the same YAML schema:

    name: my_prompt
    metadata:
      variable_definitions:
        text:
          type: str
          description: Input text
        opts:
          type: str
          description: Allowed options
          auto_generate: enum_names(MyEnum)

``auto_generate`` keys go into the generated class's ``auto_vars``
``ClassVar`` dict; others become Pydantic fields with
``Field(description=...)``. See
:func:`llm_pipeline.codegen.generate_prompt_variables` for details.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from llm_pipeline.codegen import CodegenError, generate_prompt_variables


__all__ = [
    "GenerateConfig",
    "GenerateResult",
    "add_subparser",
    "cli_main",
    "run",
]


_DEFAULT_PROMPTS_DIR = Path("./llm-pipeline-prompts")
_DEFAULT_OUTPUT_DIR = Path("./llm_pipelines/_variables")


@dataclass(frozen=True)
class GenerateConfig:
    """Inputs to a generate run.

    ``prompts_dir`` is the directory of ``*.yaml`` source files.
    ``output_dir`` is where generated ``_<name>.py`` files are
    written; the directory is created if missing, and a empty
    ``__init__.py`` is added if absent (so Python sees it as a
    package).

    ``dry_run=True`` does the codegen + diff without writing — the
    result still surfaces "would-write" file paths in
    ``files_written`` so the UI startup gate can detect stale
    variables files without mutating the working tree.
    """

    prompts_dir: Path
    output_dir: Path
    dry_run: bool = False


@dataclass
class GenerateResult:
    """Outputs of a generate run.

    Each list contains absolute paths. ``files_failed`` pairs each
    failure with a human-readable reason so callers can render a
    full report without re-running.
    """

    files_written: list[Path] = field(default_factory=list)
    files_unchanged: list[Path] = field(default_factory=list)
    files_failed: list[tuple[Path, str]] = field(default_factory=list)


def run(config: GenerateConfig) -> GenerateResult:
    """Generate ``_<name>.py`` files from every YAML in ``prompts_dir``.

    Per-file errors are collected into the result, NOT raised — the
    caller can decide whether one bad YAML aborts the whole run.
    Top-level errors (missing prompts_dir, unwritable output_dir)
    raise :class:`FileNotFoundError` / :class:`OSError`.

    The codegen path-guard is satisfied by passing ``output_dir`` as
    the ``root`` to the codegen call — every generated file resolves
    under it.
    """
    result = GenerateResult()

    prompts_dir = config.prompts_dir.expanduser().resolve()
    if not prompts_dir.is_dir():
        raise FileNotFoundError(
            f"prompts directory not found: {prompts_dir}"
        )

    from llm_pipeline._dry_run import dry_run_mode

    output_dir = config.output_dir.expanduser().resolve()

    # Bookkeeping side-effects (mkdir, seed __init__.py) are skipped
    # in dry-run; the codegen leaf check handles file writes itself.
    if not config.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        init_file = output_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("", encoding="utf-8")

    with dry_run_mode(enabled=config.dry_run):
        for yaml_path in sorted(prompts_dir.glob("*.yaml")):
            prompt_name, var_defs, parse_error = _parse_yaml(yaml_path)
            if parse_error is not None:
                result.files_failed.append((yaml_path, parse_error))
                continue

            out = output_dir / f"_{prompt_name}.py"
            try:
                written = generate_prompt_variables(
                    prompt_name=prompt_name,
                    variable_definitions=var_defs,
                    output_path=out,
                    root=output_dir,
                )
            except CodegenError as exc:
                result.files_failed.append((out, str(exc)))
                continue

            if written:
                result.files_written.append(out)
            else:
                result.files_unchanged.append(out)

    return result


def add_subparser(subparsers: Any) -> None:
    """Wire the ``generate`` subcommand into a parent argparse parser."""
    p = subparsers.add_parser(
        "generate",
        help=(
            "Generate llm_pipelines/_variables/_*.py PromptVariables "
            "files from YAML prompts. Idempotent."
        ),
    )
    _add_arguments(p)
    p.set_defaults(func=_main)


def cli_main(argv: list[str]) -> int:
    """Standalone CLI entry. ``argv`` excludes the subcommand name."""
    parser = argparse.ArgumentParser(
        prog="llm-pipeline generate",
        description=(
            "Generate llm_pipelines/_variables/_*.py PromptVariables "
            "files from YAML prompts. Idempotent — re-runs are no-ops "
            "when nothing has changed."
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
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory for generated _*.py files. Defaults "
            f"to {_DEFAULT_OUTPUT_DIR}."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help=(
            "Report what would be written without writing. Exits "
            "non-zero if any file would change."
        ),
    )


def _main(args: argparse.Namespace) -> int:
    """Build a GenerateConfig from argparse args, run, print, return code."""
    prompts_dir = args.prompts_dir or _DEFAULT_PROMPTS_DIR
    output_dir = args.output_dir or _DEFAULT_OUTPUT_DIR

    config = GenerateConfig(
        prompts_dir=prompts_dir,
        output_dir=output_dir,
        dry_run=args.dry_run,
    )

    try:
        result = run(config)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _print_report(result, dry_run=config.dry_run)
    if result.files_failed:
        return 1
    # In dry-run mode, "would-write" is a non-zero — caller wants to
    # know if the working tree is stale.
    if config.dry_run and result.files_written:
        return 1
    return 0


def _parse_yaml(
    yaml_path: Path,
) -> tuple[str, dict | None, str | None]:
    """Return (prompt_name, variable_definitions, error).

    On parse / validation failure, returns ``("", None, error_message)``
    so the caller can append to ``files_failed`` without losing the
    file path context.
    """
    try:
        text = yaml_path.read_text(encoding="utf-8")
    except OSError as exc:
        return "", None, f"read failed: {exc}"

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        return "", None, f"YAML parse failed: {exc}"

    if not isinstance(data, dict):
        return "", None, "YAML root must be a dict"

    prompt_name = data.get("name")
    if not isinstance(prompt_name, str) or not prompt_name:
        return "", None, (
            "missing or invalid 'name' field (must be a non-empty "
            "string)"
        )

    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        return prompt_name, None, "metadata must be a dict if present"

    var_defs = metadata.get("variable_definitions")
    if var_defs is not None and not isinstance(var_defs, dict):
        return prompt_name, None, (
            "metadata.variable_definitions must be a dict if present"
        )

    return prompt_name, var_defs, None


def _print_report(result: GenerateResult, *, dry_run: bool = False) -> None:
    write_verb = "WOULD" if dry_run else "WROTE"
    if result.files_written:
        prefix = "Would generate" if dry_run else "Generated"
        print(f"{prefix} {len(result.files_written)} file(s):")
        for p in result.files_written:
            print(f"  {write_verb}   {p}")
    if result.files_unchanged:
        print(
            f"Unchanged: {len(result.files_unchanged)} file(s) "
            f"(content matched, skipped write)"
        )
    if result.files_failed:
        print(
            f"\nFailed: {len(result.files_failed)} file(s):",
            file=sys.stderr,
        )
        for p, reason in result.files_failed:
            print(f"  FAIL    {p}: {reason}", file=sys.stderr)
    if (
        not result.files_written
        and not result.files_unchanged
        and not result.files_failed
    ):
        print(
            "No YAML prompts found. Set --prompts-dir or place "
            "*.yaml under ./llm-pipeline-prompts."
        )
