"""Tests for ``strict`` mode on ``llm_pipeline.discovery`` helpers.

Lenient mode (default) is exercised implicitly by the rest of the
suite — UI boot survives broken pipelines. Strict mode is the new
behavior for ``llm-pipeline build``: any module that fails to load
(including via an ``__init_subclass__`` validator rejecting one of
the user's classes) re-raises with file-path context, so the caller
can surface the failure rather than silently dropping the pipeline.
"""
from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

from llm_pipeline.discovery import (
    _load_subfolder,
    discover_from_convention,
    discover_from_entry_points,
)


# ---------------------------------------------------------------------------
# _load_subfolder
# ---------------------------------------------------------------------------


def _make_subfolder_with_bad_module(tmp_path: Path) -> Path:
    """Create a fake ``llm_pipelines/<sub>/`` with one broken file."""
    base = tmp_path / "llm_pipelines"
    base.mkdir()
    sub = base / "steps"
    sub.mkdir()
    (sub / "__init__.py").write_text("", encoding="utf-8")
    # Broken: raises during module body evaluation.
    (sub / "broken.py").write_text(
        textwrap.dedent(
            """
            raise ValueError("synthetic structural validation error")
            """,
        ).strip(),
        encoding="utf-8",
    )
    return base


class TestLoadSubfolderStrict:
    def test_lenient_default_swallows_failure(
        self, tmp_path: Path, caplog,
    ):
        base = _make_subfolder_with_bad_module(tmp_path)
        with caplog.at_level(logging.WARNING):
            modules = _load_subfolder(
                base, "steps", "_test_ns", pkg_name=None,
            )
        # Bad module dropped from result.
        assert modules == []
        # Failure logged.
        assert any("Failed to load" in rec.message for rec in caplog.records)

    def test_strict_propagates_failure(self, tmp_path: Path):
        base = _make_subfolder_with_bad_module(tmp_path)
        with pytest.raises(ValueError, match="synthetic structural"):
            _load_subfolder(
                base, "steps", "_test_ns", pkg_name=None, strict=True,
            )


# ---------------------------------------------------------------------------
# discover_from_convention strict pass-through
# ---------------------------------------------------------------------------


class TestDiscoverFromConventionStrict:
    def test_strict_propagates_subfolder_failure(
        self, tmp_path: Path, monkeypatch,
    ):
        """A broken module under ``llm_pipelines/<sub>/`` propagates."""
        base = _make_subfolder_with_bad_module(tmp_path)

        # Force the discovery walker to find ONLY our tmp dir (not the
        # repo's own llm_pipelines/).
        monkeypatch.setattr(
            "llm_pipeline.discovery.loading.find_convention_dirs",
            lambda include_package=True: [base],
        )

        with pytest.raises(ValueError, match="synthetic structural"):
            discover_from_convention(
                None, None, include_package=False, strict=True,
            )


# ---------------------------------------------------------------------------
# discover_from_entry_points strict pass-through
# ---------------------------------------------------------------------------


class _FakeEntryPoint:
    """Minimal stand-in for an importlib.metadata EntryPoint."""

    def __init__(self, name: str, payload):
        self.name = name
        self._payload = payload

    def load(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class TestDiscoverFromEntryPointsStrict:
    def test_strict_raises_on_load_failure(self, monkeypatch):
        bad = _FakeEntryPoint(
            "broken", payload=ImportError("synthetic load failure"),
        )

        monkeypatch.setattr(
            "llm_pipeline.discovery.entry_points.importlib.metadata.entry_points",
            lambda group=None: [bad],
        )
        with pytest.raises(RuntimeError, match="broken"):
            discover_from_entry_points(strict=True)

    def test_strict_raises_on_non_pipeline_class(self, monkeypatch):
        # Entry point loads cleanly but doesn't reference a Pipeline.
        bad = _FakeEntryPoint("not_a_pipeline", payload=int)

        monkeypatch.setattr(
            "llm_pipeline.discovery.entry_points.importlib.metadata.entry_points",
            lambda group=None: [bad],
        )
        with pytest.raises(TypeError, match="not a Pipeline|not_a_pipeline"):
            discover_from_entry_points(strict=True)

    def test_lenient_default_swallows_failure(self, monkeypatch, caplog):
        bad = _FakeEntryPoint(
            "broken", payload=ImportError("synthetic load failure"),
        )
        monkeypatch.setattr(
            "llm_pipeline.discovery.entry_points.importlib.metadata.entry_points",
            lambda group=None: [bad],
        )
        with caplog.at_level(logging.WARNING):
            pipeline_reg, intro_reg = discover_from_entry_points()
        assert pipeline_reg == {}
        assert intro_reg == {}
        assert any("Failed to load entry point" in rec.message
                   for rec in caplog.records)
