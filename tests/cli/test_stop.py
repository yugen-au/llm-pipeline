"""Tests for ``llm_pipeline.cli.stop``.

The command is small but state-bearing: it reads a file in CWD,
calls into psutil to terminate process trees, and removes the file.
Tests cover the no-op (no PID file), happy path (PIDs read, kill
helper invoked, file removed), and the malformed-file failure.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from llm_pipeline.cli.stop import (
    StopConfig,
    StopResult,
    cli_main,
    run,
)


@pytest.fixture
def cwd_tmp(tmp_path: Path, monkeypatch):
    """Run each test from an isolated CWD so the PID file is scoped."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


@pytest.fixture
def pid_file(cwd_tmp: Path) -> Path:
    """The path stop reads — relative to CWD, mirrors production layout."""
    return cwd_tmp / ".llm_pipeline" / "ui.pid"


def _write_pid_file(path: Path, *, main_pid: int, vite_pid: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"main={main_pid}"]
    if vite_pid is not None:
        lines.append(f"vite={vite_pid}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# run()
# ---------------------------------------------------------------------------


class TestRunNoPidFile:
    def test_returns_was_running_false(self, cwd_tmp: Path):
        result = run(StopConfig())
        assert isinstance(result, StopResult)
        assert result.was_running is False
        assert result.killed == []
        assert result.errors == []


class TestRunWithPidFile:
    def test_main_only_kill_path(self, pid_file: Path):
        _write_pid_file(pid_file, main_pid=12345)

        with patch(
            "llm_pipeline.cli.stop._kill_process_tree",
        ) as mock_kill:
            result = run(StopConfig())

        assert result.was_running is True
        assert result.killed == [12345]
        assert result.errors == []
        mock_kill.assert_called_once_with(12345)
        # File cleaned up after kill.
        assert not pid_file.exists()

    def test_main_plus_vite_kills_both(self, pid_file: Path):
        _write_pid_file(pid_file, main_pid=12345, vite_pid=12346)

        with patch(
            "llm_pipeline.cli.stop._kill_process_tree",
        ) as mock_kill:
            result = run(StopConfig())

        assert result.was_running is True
        assert result.killed == [12345, 12346]
        assert mock_kill.call_count == 2
        mock_kill.assert_any_call(12345)
        mock_kill.assert_any_call(12346)


class TestRunMalformedPidFile:
    def test_missing_main_entry_records_error(self, pid_file: Path):
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("vite=999\n", encoding="utf-8")

        with patch(
            "llm_pipeline.cli.stop._kill_process_tree",
        ) as mock_kill:
            result = run(StopConfig())

        assert result.was_running is True
        assert result.killed == []
        assert any("main" in e for e in result.errors)
        mock_kill.assert_not_called()

    def test_non_integer_pid_records_error(self, pid_file: Path):
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("main=not-a-number\n", encoding="utf-8")

        with patch(
            "llm_pipeline.cli.stop._kill_process_tree",
        ) as mock_kill:
            result = run(StopConfig())

        assert result.was_running is True
        assert result.errors  # at least one error recorded
        mock_kill.assert_not_called()


# ---------------------------------------------------------------------------
# cli_main()
# ---------------------------------------------------------------------------


class TestCliMain:
    def test_returns_one_when_not_running(self, cwd_tmp: Path, capsys):
        rc = cli_main([])
        assert rc == 1
        captured = capsys.readouterr()
        assert "No running UI server" in captured.err

    def test_returns_zero_on_successful_stop(
        self, pid_file: Path, capsys,
    ):
        _write_pid_file(pid_file, main_pid=12345)

        with patch("llm_pipeline.cli.stop._kill_process_tree"):
            rc = cli_main([])

        assert rc == 0
        captured = capsys.readouterr()
        assert "Stopping UI server" in captured.out
        assert "Stopped." in captured.out

    def test_returns_one_on_malformed_pid_file(
        self, pid_file: Path, capsys,
    ):
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        pid_file.write_text("vite=999\n", encoding="utf-8")
        rc = cli_main([])
        assert rc == 1
        captured = capsys.readouterr()
        assert "ERROR" in captured.err
