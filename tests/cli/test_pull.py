"""Tests for ``llm_pipeline.cli.pull``.

Covers wiring around the existing ``yaml_sync.pull_phoenix_to_yaml``:

- Discovery failures land in ``discovery_errors``.
- Phoenix-unreachable lands in ``discovery_errors`` (pre-flight).
- A successful pull with no drift returns ``is_clean`` True.
- A successful pull WITH drift returns ``is_clean`` False (changes
  brought down from Phoenix).
- ``cli_main`` exit codes map cleanly.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_pipeline.cli.pull import (
    PullConfig,
    PullResult,
    cli_main,
    run,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_prompts_dir(tmp_path: Path) -> Path:
    p = tmp_path / "prompts"
    p.mkdir()
    return p


# ---------------------------------------------------------------------------
# Discovery / pre-flight errors
# ---------------------------------------------------------------------------


class TestDiscoveryErrors:
    def test_no_pipelines_recorded_as_discovery_error(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        # Force discovery to return an empty registry from all sources.
        monkeypatch.setattr(
            "llm_pipeline.discovery.find_convention_dirs",
            lambda include_package=True: [],
        )

        result = run(PullConfig(prompts_dir=empty_prompts_dir))
        assert not result.is_clean
        assert any(
            "No pipelines discovered" in e for e in result.discovery_errors
        )

    def test_missing_prompts_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            run(PullConfig(prompts_dir=tmp_path / "missing"))

    def test_phoenix_unreachable_recorded_as_discovery_error(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        # Stub discovery to populate a non-empty registry.
        monkeypatch.setattr(
            "llm_pipeline.discovery.find_convention_dirs",
            lambda include_package=True: [],
        )
        monkeypatch.setattr(
            "llm_pipeline.discovery.discover_from_convention",
            lambda *a, **kw: ({}, {"fake": object()}),
        )

        # Phoenix client construction blows up.
        from llm_pipeline.prompts import phoenix_client as pc_mod

        class _Boom(pc_mod.PhoenixError):
            pass

        def _raise(*_a, **_kw):
            raise _Boom("simulated unreachable")

        monkeypatch.setattr(
            "llm_pipeline.cli.pull.__name__",  # noqa: S105 - dummy
            "llm_pipeline.cli.pull",
        )
        monkeypatch.setattr(
            pc_mod, "PhoenixPromptClient", _raise,
        )

        result = run(PullConfig(prompts_dir=empty_prompts_dir))
        assert not result.is_clean
        assert any(
            "Phoenix prompt client unavailable" in e
            for e in result.discovery_errors
        )


# ---------------------------------------------------------------------------
# Successful pull paths (mock yaml_sync.pull_phoenix_to_yaml)
# ---------------------------------------------------------------------------


class TestPullSuccess:
    @staticmethod
    def _stub_discovery_and_client(monkeypatch):
        """Make discovery succeed with a non-empty registry + client construct."""
        monkeypatch.setattr(
            "llm_pipeline.discovery.find_convention_dirs",
            lambda include_package=True: [],
        )
        monkeypatch.setattr(
            "llm_pipeline.discovery.discover_from_convention",
            lambda *a, **kw: ({}, {"fake": object()}),
        )

        class _StubClient:
            pass

        from llm_pipeline.prompts import phoenix_client as pc_mod
        monkeypatch.setattr(
            pc_mod, "PhoenixPromptClient", lambda *a, **kw: _StubClient(),
        )

    def test_clean_pull_returns_is_clean_true(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        self._stub_discovery_and_client(monkeypatch)

        # Simulate "everything matches" — no pulled, no failed.
        from llm_pipeline.yaml_sync import SyncReport

        def _fake_pull(*, prompts_dir, prompt_client, introspection_registry):
            return SyncReport(prompts_pull_skipped=["topic_extraction"])

        monkeypatch.setattr("llm_pipeline.yaml_sync.pull_phoenix_to_yaml", _fake_pull)

        result = run(PullConfig(prompts_dir=empty_prompts_dir))
        assert result.is_clean
        assert result.prompts_unchanged == ["topic_extraction"]
        assert result.prompts_pulled == []

    def test_drift_pull_records_pulled_and_not_clean(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        self._stub_discovery_and_client(monkeypatch)

        from llm_pipeline.yaml_sync import SyncReport

        def _fake_pull(*, prompts_dir, prompt_client, introspection_registry):
            return SyncReport(
                prompts_pulled=["topic_extraction"],
                prompts_pull_skipped=["summary"],
            )

        monkeypatch.setattr("llm_pipeline.yaml_sync.pull_phoenix_to_yaml", _fake_pull)

        result = run(PullConfig(prompts_dir=empty_prompts_dir))
        assert not result.is_clean  # drift means not clean
        assert result.prompts_pulled == ["topic_extraction"]
        assert result.prompts_unchanged == ["summary"]

    def test_per_prompt_failure_recorded(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        self._stub_discovery_and_client(monkeypatch)

        from llm_pipeline.yaml_sync import SyncReport

        def _fake_pull(*, prompts_dir, prompt_client, introspection_registry):
            return SyncReport(
                prompts_pull_failed=[("topic_extraction", "phoenix: 500")],
            )

        monkeypatch.setattr("llm_pipeline.yaml_sync.pull_phoenix_to_yaml", _fake_pull)

        result = run(PullConfig(prompts_dir=empty_prompts_dir))
        assert not result.is_clean
        assert len(result.prompts_failed) == 1
        name, reason = result.prompts_failed[0]
        assert name == "topic_extraction"
        assert "phoenix: 500" in reason


# ---------------------------------------------------------------------------
# cli_main exit codes
# ---------------------------------------------------------------------------


class TestCliMain:
    def test_cli_main_returns_one_when_no_pipelines(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        monkeypatch.setattr(
            "llm_pipeline.discovery.find_convention_dirs",
            lambda include_package=True: [],
        )
        rc = cli_main(["--prompts-dir", str(empty_prompts_dir)])
        assert rc == 1

    def test_cli_main_returns_one_when_prompts_dir_missing(self, tmp_path: Path):
        rc = cli_main(["--prompts-dir", str(tmp_path / "missing")])
        assert rc == 1
