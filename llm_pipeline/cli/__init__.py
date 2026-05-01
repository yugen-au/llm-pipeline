"""Top-level ``llm-pipeline`` CLI dispatcher.

This package is the single entry point declared in
``pyproject.toml``. Each subcommand follows a five-element
protocol:

- A ``Config`` dataclass capturing inputs (parsed from CLI args).
- A ``Result`` dataclass capturing outputs (read by callers / tests).
- A pure ``run(config) -> Result`` function — importable from
  anywhere (UI, tests, scripts).
- An ``cli_main(argv) -> int`` standalone CLI entry — used by the
  dispatcher below.
- An ``add_subparser(subparsers)`` for the eventual unified parser
  (B.3c) when legacy commands migrate to the same protocol.

The dispatcher uses positional argv routing: the first non-flag
argument is the subcommand name. Currently only ``generate`` lives
in this package; everything else (``ui``, ``build``, ``eval``,
``stop``) is delegated to ``llm_pipeline.ui.cli:main`` until those
commands are migrated in B.3c.
"""
from __future__ import annotations

import sys


_LEGACY_COMMANDS = {"ui", "eval"}


def main() -> None:
    """Top-level entry point: dispatch to a subcommand."""
    argv = sys.argv[1:]

    if argv and argv[0] == "generate":
        from llm_pipeline.cli import generate

        sys.exit(generate.cli_main(argv[1:]))

    if argv and argv[0] == "build":
        from llm_pipeline.cli import build

        sys.exit(build.cli_main(argv[1:]))

    if argv and argv[0] == "pull":
        from llm_pipeline.cli import pull

        sys.exit(pull.cli_main(argv[1:]))

    if argv and argv[0] == "push":
        from llm_pipeline.cli import push

        sys.exit(push.cli_main(argv[1:]))

    if argv and argv[0] == "stop":
        from llm_pipeline.cli import stop

        sys.exit(stop.cli_main(argv[1:]))

    if not argv or argv[0] in ("-h", "--help"):
        # No subcommand or top-level help → show full subcommand list,
        # including both new and legacy commands.
        _print_top_level_help()
        return

    if argv[0] in _LEGACY_COMMANDS:
        from llm_pipeline.ui.cli import main as legacy_main

        legacy_main()
        return

    print(
        f"ERROR: unknown subcommand {argv[0]!r}. Run 'llm-pipeline "
        f"--help' for the list.",
        file=sys.stderr,
    )
    sys.exit(2)


def _print_top_level_help() -> None:
    print(
        "usage: llm-pipeline <subcommand> [options...]\n"
        "\n"
        "Subcommands:\n"
        "  generate  YAML -> llm_pipelines/_variables/_*.py codegen "
        "(idempotent)\n"
        "  build     Discover pipelines + offline code/YAML alignment "
        "validation\n"
        "  pull      Phoenix -> YAML for fields Phoenix owns "
        "(message text, model)\n"
        "  push      YAML + code-derived fields -> Phoenix "
        "(auto-creates new prompts)\n"
        "  ui        Start the UI server\n"
        "  eval      Run an evaluation dataset\n"
        "  stop      Stop a running UI server\n"
        "\n"
        "Typical workflow: pull -> generate -> build -> push.\n"
        "\n"
        "Run 'llm-pipeline <subcommand> --help' for subcommand-"
        "specific options."
    )


if __name__ == "__main__":
    main()
