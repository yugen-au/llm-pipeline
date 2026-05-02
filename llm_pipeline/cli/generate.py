"""``llm-pipeline generate`` — YAML → step-file ``XPrompt`` upsert.

Walks ``--prompts-dir`` for ``*.yaml`` files; for each, upserts the
matching ``XPrompt(PromptVariables)`` class inside the paired
``<steps-dir>/<prompt_name>.py`` file. Idempotent: a step file
whose existing ``XPrompt`` class matches the YAML is left alone.

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
_DEFAULT_STEPS_DIR = Path("./llm_pipelines/steps")


@dataclass(frozen=True)
class GenerateConfig:
    """Inputs to a generate run.

    ``prompts_dir`` is the directory of ``*.yaml`` source files.
    ``steps_dir`` is the directory holding the paired step files;
    each YAML's ``name`` field maps 1:1 to ``<steps_dir>/<name>.py``.
    The directory must already exist — generate doesn't scaffold
    new step files, only upserts the ``XPrompt`` class inside
    existing ones.

    ``dry_run=True`` does the codegen + diff without writing — the
    result still surfaces "would-write" file paths in
    ``files_written`` so the UI startup gate can detect stale step
    files without mutating the working tree.
    """

    prompts_dir: Path
    steps_dir: Path
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
    """Upsert ``XPrompt`` classes into step files for every YAML in ``prompts_dir``.

    Per-file errors are collected into the result, NOT raised — the
    caller can decide whether one bad YAML aborts the whole run.
    Top-level errors (missing prompts_dir, missing steps_dir) raise
    :class:`FileNotFoundError`.

    Each YAML's ``name`` field resolves to ``<steps_dir>/<name>.py``;
    that file must already exist — a YAML without a paired step is
    treated as stale and surfaced via ``files_failed``. The
    codegen path-guard uses the parent of ``steps_dir`` as the root
    so the upsert can read/write the step file itself.
    """
    result = GenerateResult()

    prompts_dir = config.prompts_dir.expanduser().resolve()
    if not prompts_dir.is_dir():
        raise FileNotFoundError(
            f"prompts directory not found: {prompts_dir}"
        )

    steps_dir = config.steps_dir.expanduser().resolve()
    if not steps_dir.is_dir():
        raise FileNotFoundError(
            f"steps directory not found: {steps_dir}. "
            f"Generate upserts into existing step files; create the "
            f"directory and at least one step before running generate."
        )

    # Path-guard root for codegen: the parent of ``steps_dir`` (the
    # convention dir, ``llm_pipelines/``). Lets each step file
    # resolve under root.
    codegen_root = steps_dir.parent

    from llm_pipeline._dry_run import dry_run_mode

    with dry_run_mode(enabled=config.dry_run):
        for yaml_path in sorted(prompts_dir.glob("*.yaml")):
            prompt_name, var_defs, parse_error = _parse_yaml(yaml_path)
            if parse_error is not None:
                result.files_failed.append((yaml_path, parse_error))
                continue

            step_file = steps_dir / f"{prompt_name}.py"
            try:
                written = generate_prompt_variables(
                    prompt_name=prompt_name,
                    variable_definitions=var_defs,
                    step_file=step_file,
                    root=codegen_root,
                )
            except CodegenError as exc:
                result.files_failed.append((step_file, str(exc)))
                continue

            if written:
                result.files_written.append(step_file)
            else:
                result.files_unchanged.append(step_file)

    return result


def add_subparser(subparsers: Any) -> None:
    """Wire the ``generate`` subcommand into a parent argparse parser."""
    p = subparsers.add_parser(
        "generate",
        help=(
            "Upsert XPrompt(PromptVariables) classes into step files "
            "from YAML prompts. Idempotent."
        ),
    )
    _add_arguments(p)
    p.set_defaults(func=_main)


def cli_main(argv: list[str]) -> int:
    """Standalone CLI entry. ``argv`` excludes the subcommand name."""
    parser = argparse.ArgumentParser(
        prog="llm-pipeline generate",
        description=(
            "Upsert XPrompt(PromptVariables) classes into step files "
            "from YAML prompts. Idempotent — re-runs are no-ops when "
            "the existing class already matches the YAML."
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
        "--steps-dir",
        type=Path,
        default=None,
        help=(
            "Directory holding paired step files. Each YAML's name "
            "field maps to <steps-dir>/<name>.py. Defaults to "
            f"{_DEFAULT_STEPS_DIR}."
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
    steps_dir = args.steps_dir or _DEFAULT_STEPS_DIR

    config = GenerateConfig(
        prompts_dir=prompts_dir,
        steps_dir=steps_dir,
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
