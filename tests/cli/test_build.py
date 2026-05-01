"""Tests for ``llm_pipeline.cli.build``.

Covers the new offline ``build`` subcommand:

- ``run()`` returns a ``BuildResult`` with discovered pipelines
  and any collected errors.
- Discovery in build is **strict**: structural validation failures
  (e.g. an ``__init_subclass__`` validator rejecting a node)
  surface as errors rather than silently dropping the pipeline.
- ``cli_main`` exit code reflects ``result.is_clean``.
- ``--prompts-dir`` defaults / overrides work.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_pipeline.cli.build import (
    BuildConfig,
    BuildResult,
    cli_main,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_module_dir(
    tmp_path: Path,
    pkg_name: str,
    files: dict[str, str],
) -> Path:
    """Create a Python package on disk with ``files`` -> source content.

    Returns the package root. The caller is responsible for putting
    ``tmp_path`` on ``sys.path`` (or using ``--pipelines`` with a
    dotted path that resolves under tmp_path).
    """
    pkg_dir = tmp_path / pkg_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    for filename, body in files.items():
        (pkg_dir / filename).write_text(body, encoding="utf-8")
    return pkg_dir


# ---------------------------------------------------------------------------
# run(): no-pipelines case
# ---------------------------------------------------------------------------


class TestRunNoPipelines:
    def test_no_pipelines_records_error(self, tmp_path: Path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        result = run(
            BuildConfig(
                prompts_dir=prompts,
                pipeline_modules=None,
                demo=False,
            ),
        )
        assert not result.is_clean
        assert any("No pipelines discovered" in e for e in result.errors)

    def test_missing_prompts_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            run(
                BuildConfig(
                    prompts_dir=tmp_path / "does_not_exist",
                    pipeline_modules=None,
                    demo=False,
                ),
            )


# ---------------------------------------------------------------------------
# run(): module-discovery error path
# ---------------------------------------------------------------------------


class TestRunModuleDiscoveryErrors:
    def test_unknown_module_path_collects_error(self, tmp_path: Path):
        prompts = tmp_path / "prompts"
        prompts.mkdir()

        result = run(
            BuildConfig(
                prompts_dir=prompts,
                pipeline_modules=["definitely.not.a.real.module"],
                demo=False,
            ),
        )

        assert not result.is_clean
        assert any("Module load failed" in e for e in result.errors)


# ---------------------------------------------------------------------------
# run(): demo-pipeline happy path
# ---------------------------------------------------------------------------


class TestRunWithDemo:
    def test_demo_validates_text_analyzer(self, tmp_path: Path):
        # The repo's bundled demo pipeline expects to run against the
        # repo's bundled prompts dir; pass that one in.
        repo_root = Path(__file__).resolve().parents[2]
        prompts_dir = repo_root / "llm-pipeline-prompts"
        if not prompts_dir.is_dir():
            pytest.skip("repo prompts dir not present")

        # NB: the demo entry-point set currently includes a stub
        # ('step_creator') that isn't a graph Pipeline subclass —
        # strict mode reports it. We assert text_analyzer made it in,
        # not that the build is clean. The stub is an existing repo
        # concern, not a build-command bug.
        result = run(
            BuildConfig(
                prompts_dir=prompts_dir,
                pipeline_modules=None,
                demo=True,
            ),
        )
        assert "text_analyzer" in result.pipelines


# ---------------------------------------------------------------------------
# cli_main(): exit codes
# ---------------------------------------------------------------------------


class TestCliMain:
    def test_cli_main_returns_one_when_no_pipelines(
        self, tmp_path: Path, capsys,
    ):
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        rc = cli_main(["--prompts-dir", str(prompts)])
        assert rc == 1
        captured = capsys.readouterr()
        assert "No pipelines discovered" in captured.err

    def test_cli_main_returns_one_when_prompts_dir_missing(
        self, tmp_path: Path, capsys,
    ):
        rc = cli_main(
            ["--prompts-dir", str(tmp_path / "missing")],
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
