"""Tests for ``llm_pipeline.cli.push``.

Covers wiring around ``yaml_sync.startup_sync`` (push direction):

- Discovery failures land in ``discovery_errors``.
- Phoenix-unreachable lands in ``discovery_errors``.
- A clean push (everything matches) returns ``is_clean`` True.
- A push WITH changes returns ``is_clean`` False.
- Per-prompt failures land in ``prompts_failed``.
- ``cli_main`` exit codes map cleanly.
- Datasets sync runs only when ``evals_dir`` exists.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_pipeline.cli.push import (
    PushConfig,
    PushResult,
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


def _stub_discovery_with_registry(monkeypatch):
    """Make discovery succeed with a non-empty introspection registry."""
    monkeypatch.setattr(
        "llm_pipeline.discovery.find_convention_dirs",
        lambda include_package=True: [],
    )
    monkeypatch.setattr(
        "llm_pipeline.discovery.discover_from_convention",
        lambda *a, **kw: ({}, {"fake": object()}),
    )


def _stub_phoenix_clients_ok(monkeypatch):
    """Make both Phoenix client constructors succeed silently."""
    from llm_pipeline.prompts import phoenix_client as pc_mod

    class _Stub:
        pass

    monkeypatch.setattr(
        pc_mod, "PhoenixPromptClient", lambda *a, **kw: _Stub(),
    )
    # The dataset client is imported lazily inside push.run; patch
    # the real module's attribute (rather than replacing the module
    # in sys.modules, which would drop the rest of its surface for
    # downstream imports — and break yaml_sync).
    from llm_pipeline.evals import phoenix_client as dc_mod
    monkeypatch.setattr(
        dc_mod, "PhoenixDatasetClient", lambda *a, **kw: _Stub(),
    )


# ---------------------------------------------------------------------------
# Discovery / pre-flight errors
# ---------------------------------------------------------------------------


class TestDiscoveryErrors:
    def test_no_pipelines_recorded_as_discovery_error(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        monkeypatch.setattr(
            "llm_pipeline.discovery.find_convention_dirs",
            lambda include_package=True: [],
        )

        result = run(PushConfig(prompts_dir=empty_prompts_dir))
        assert not result.is_clean
        assert any(
            "No pipelines discovered" in e for e in result.discovery_errors
        )

    def test_missing_prompts_dir_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            run(PushConfig(prompts_dir=tmp_path / "missing"))

    def test_phoenix_unreachable_recorded_as_discovery_error(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        _stub_discovery_with_registry(monkeypatch)

        from llm_pipeline.prompts import phoenix_client as pc_mod

        def _raise(*_a, **_kw):
            raise pc_mod.PhoenixError("simulated unreachable")

        monkeypatch.setattr(pc_mod, "PhoenixPromptClient", _raise)

        result = run(PushConfig(prompts_dir=empty_prompts_dir))
        assert not result.is_clean
        assert any(
            "Phoenix prompt client unavailable" in e
            for e in result.discovery_errors
        )


# ---------------------------------------------------------------------------
# Successful push paths (mock yaml_sync.startup_sync)
# ---------------------------------------------------------------------------


class TestPushSuccess:
    def test_clean_push_returns_is_clean_true(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        _stub_discovery_with_registry(monkeypatch)
        _stub_phoenix_clients_ok(monkeypatch)

        from llm_pipeline.yaml_sync import SyncReport

        def _fake_startup(**kwargs):
            return SyncReport(prompts_skipped=["topic_extraction"])

        monkeypatch.setattr(
            "llm_pipeline.yaml_sync.startup_sync", _fake_startup,
        )

        result = run(PushConfig(prompts_dir=empty_prompts_dir))
        assert result.is_clean
        assert result.prompts_unchanged == ["topic_extraction"]
        assert result.prompts_pushed == []

    def test_push_with_changes_not_clean(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        _stub_discovery_with_registry(monkeypatch)
        _stub_phoenix_clients_ok(monkeypatch)

        from llm_pipeline.yaml_sync import SyncReport

        def _fake_startup(**kwargs):
            return SyncReport(
                prompts_pushed=["topic_extraction"],
                prompts_skipped=["summary"],
            )

        monkeypatch.setattr(
            "llm_pipeline.yaml_sync.startup_sync", _fake_startup,
        )

        result = run(PushConfig(prompts_dir=empty_prompts_dir))
        assert not result.is_clean
        assert result.prompts_pushed == ["topic_extraction"]

    def test_per_prompt_failure_recorded(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        _stub_discovery_with_registry(monkeypatch)
        _stub_phoenix_clients_ok(monkeypatch)

        from llm_pipeline.yaml_sync import SyncReport

        def _fake_startup(**kwargs):
            return SyncReport(
                prompts_failed=[("topic_extraction", "phoenix: 500")],
            )

        monkeypatch.setattr(
            "llm_pipeline.yaml_sync.startup_sync", _fake_startup,
        )

        result = run(PushConfig(prompts_dir=empty_prompts_dir))
        assert not result.is_clean
        assert len(result.prompts_failed) == 1


class TestEvalsDirHandling:
    def test_evals_dir_skipped_when_missing(
        self, empty_prompts_dir: Path, tmp_path: Path, monkeypatch,
    ):
        """Push runs cleanly even with --evals-dir pointing nowhere."""
        _stub_discovery_with_registry(monkeypatch)
        _stub_phoenix_clients_ok(monkeypatch)

        from llm_pipeline.yaml_sync import SyncReport

        captured = {}

        def _fake_startup(**kwargs):
            captured.update(kwargs)
            return SyncReport()

        monkeypatch.setattr(
            "llm_pipeline.yaml_sync.startup_sync", _fake_startup,
        )

        result = run(
            PushConfig(
                prompts_dir=empty_prompts_dir,
                evals_dir=tmp_path / "no_such_evals_dir",
            ),
        )
        assert result.is_clean
        # Sync got None for datasets_dir / dataset_client.
        assert captured.get("datasets_dir") is None
        assert captured.get("dataset_client") is None


class TestDryRun:
    """Dry-run wraps startup_sync in ``dry_run_mode`` so Phoenix mutations no-op."""

    def test_dry_run_propagates_into_yaml_sync(
        self, empty_prompts_dir: Path, monkeypatch,
    ):
        _stub_discovery_with_registry(monkeypatch)
        _stub_phoenix_clients_ok(monkeypatch)

        from llm_pipeline._dry_run import is_dry_run
        from llm_pipeline.yaml_sync import SyncReport

        observed = {}

        def _fake_startup(**kwargs):
            observed["was_dry_run"] = is_dry_run()
            return SyncReport(prompts_pushed=["topic_extraction"])

        monkeypatch.setattr(
            "llm_pipeline.yaml_sync.startup_sync", _fake_startup,
        )

        run(PushConfig(prompts_dir=empty_prompts_dir, dry_run=True))
        assert observed["was_dry_run"] is True

    def test_cli_dry_run_returns_one_when_drift_present(
        self, empty_prompts_dir: Path, monkeypatch, capsys,
    ):
        _stub_discovery_with_registry(monkeypatch)
        _stub_phoenix_clients_ok(monkeypatch)

        from llm_pipeline.yaml_sync import SyncReport

        def _fake_startup(**kwargs):
            return SyncReport(prompts_pushed=["topic_extraction"])

        monkeypatch.setattr(
            "llm_pipeline.yaml_sync.startup_sync", _fake_startup,
        )

        rc = cli_main(
            ["--prompts-dir", str(empty_prompts_dir), "--dry-run"],
        )
        assert rc == 1
        captured = capsys.readouterr()
        assert "Would push" in captured.out


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
