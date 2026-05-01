"""Tests for ``_preflight_check`` — the UI startup gate.

Validates prod/dev gating:

- Prod mode (``args.dev=False``) exits non-zero on detected drift.
- Dev mode (``args.dev=True``) prints a warning and returns.
- A non-existent prompts_dir is a no-op (greenfield project).
"""
from __future__ import annotations

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from llm_pipeline.ui.cli import _preflight_check


def _make_args(
    *,
    dev: bool,
    prompts_dir: Path | None,
    pipelines: list[str] | None = None,
    demo: bool = False,
    evals_dir: Path | None = None,
) -> argparse.Namespace:
    return SimpleNamespace(
        dev=dev,
        prompts_dir=str(prompts_dir) if prompts_dir is not None else None,
        evals_dir=str(evals_dir) if evals_dir is not None else None,
        pipelines=pipelines,
        demo=demo,
    )


class TestGreenfieldProject:
    def test_missing_prompts_dir_is_no_op(self, tmp_path: Path):
        # Empty tmp_path with no llm-pipeline-prompts subdir.
        args = _make_args(dev=False, prompts_dir=tmp_path / "no_such_dir")
        # No exit, no exception — pre-flight is best-effort.
        _preflight_check(args)


class TestProdGating:
    def test_prod_exits_on_discovery_failure(
        self, tmp_path: Path, monkeypatch, capsys,
    ):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        # Force discovery to find nothing → build will record "No
        # pipelines discovered" as an error.
        monkeypatch.setattr(
            "llm_pipeline.discovery.find_convention_dirs",
            lambda include_package=True: [],
        )

        args = _make_args(dev=False, prompts_dir=prompts_dir)
        with pytest.raises(SystemExit) as exc_info:
            _preflight_check(args)
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "UI pre-flight failed" in captured.err

    def test_dev_warns_on_discovery_failure(
        self, tmp_path: Path, monkeypatch, capsys,
    ):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()

        monkeypatch.setattr(
            "llm_pipeline.discovery.find_convention_dirs",
            lambda include_package=True: [],
        )

        args = _make_args(dev=True, prompts_dir=prompts_dir)
        # No SystemExit in dev mode — pre-flight just warns.
        _preflight_check(args)
        captured = capsys.readouterr()
        assert "WARNING" in captured.err
        assert "Continuing because --dev" in captured.err
