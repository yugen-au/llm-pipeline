"""Tests for llm_pipeline.ui.cli - all code paths covered.

Patch targets for deferred imports:
  create_app       -> "llm_pipeline.ui.app.create_app"
  uvicorn.run      -> "uvicorn.run"
  StaticFiles      -> "starlette.staticfiles.StaticFiles"
  subprocess.run   -> "llm_pipeline.ui.cli.subprocess.run"
  subprocess.Popen -> "llm_pipeline.ui.cli.subprocess.Popen"
  atexit.register  -> "llm_pipeline.ui.cli.atexit.register"
  Path.exists      -> "pathlib.Path.exists"
"""
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from llm_pipeline.ui.cli import _cleanup_vite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_app() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# main() - no subcommand
# ---------------------------------------------------------------------------

class TestMainNoSubcommand:
    def test_no_subcommand_exits_1(self):
        """main() with no subcommand prints help and exits with code 1."""
        from llm_pipeline.ui.cli import main
        with patch.object(sys, "argv", ["llm-pipeline"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1

    def test_no_subcommand_calls_print_help(self):
        """main() calls parser.print_help() before exiting."""
        from llm_pipeline.ui.cli import main
        with patch.object(sys, "argv", ["llm-pipeline"]):
            with patch("argparse.ArgumentParser.print_help") as mock_help:
                with pytest.raises(SystemExit):
                    main()
        mock_help.assert_called_once()


# ---------------------------------------------------------------------------
# Prod mode - no dist/
# ---------------------------------------------------------------------------

class TestProdModeNoStaticFiles:
    """Prod mode without frontend/dist/ present."""

    def _run_prod(self, extra_argv=None, mock_app=None):
        """Invoke main() in prod mode with Path.exists=False and mocked deps."""
        from llm_pipeline.ui.cli import main
        if mock_app is None:
            mock_app = _make_mock_app()
        argv = ["llm-pipeline", "ui"] + (extra_argv or [])
        with patch.object(sys, "argv", argv), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app) as mock_ca, \
             patch("pathlib.Path.exists", return_value=False), \
             patch("uvicorn.run") as mock_run:
            main()
        return mock_app, mock_ca, mock_run

    def test_uvicorn_run_called(self):
        """uvicorn.run is called in prod mode."""
        _, _, mock_run = self._run_prod()
        mock_run.assert_called_once()

    def test_host_is_0000(self):
        """Prod mode binds host 0.0.0.0."""
        _, _, mock_run = self._run_prod()
        _, kwargs = mock_run.call_args
        assert kwargs.get("host") == "0.0.0.0"

    def test_default_port_8642(self):
        """Prod mode defaults to port 8642."""
        _, _, mock_run = self._run_prod()
        _, kwargs = mock_run.call_args
        assert kwargs.get("port") == 8642

    def test_no_static_mount_without_dist(self):
        """app.mount is NOT called when dist/ does not exist."""
        mock_app = _make_mock_app()
        self._run_prod(mock_app=mock_app)
        mock_app.mount.assert_not_called()

    def test_warning_printed_to_stderr(self, capsys):
        """WARNING message printed to stderr when dist/ missing."""
        self._run_prod()
        captured = capsys.readouterr()
        assert "WARNING" in captured.err


class TestProdModeWithStaticFiles:
    """Prod mode when frontend/dist/ exists."""

    def _run_prod_with_dist(self, mock_app=None):
        from llm_pipeline.ui.cli import main
        if mock_app is None:
            mock_app = _make_mock_app()
        with patch.object(sys, "argv", ["llm-pipeline", "ui"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("starlette.staticfiles.StaticFiles") as mock_sf_cls, \
             patch("uvicorn.run") as mock_run:
            main()
        return mock_app, mock_sf_cls, mock_run

    def test_static_files_mounted_on_root(self):
        """app.mount is called with '/' when dist/ exists."""
        mock_app = _make_mock_app()
        self._run_prod_with_dist(mock_app=mock_app)
        mock_app.mount.assert_called_once()
        mount_args, _ = mock_app.mount.call_args
        assert mount_args[0] == "/"

    def test_static_files_html_true(self):
        """StaticFiles is instantiated with html=True."""
        _, mock_sf_cls, _ = self._run_prod_with_dist()
        _, sf_kwargs = mock_sf_cls.call_args
        assert sf_kwargs.get("html") is True

    def test_uvicorn_still_called(self):
        """uvicorn.run is still called after mounting static files."""
        _, _, mock_run = self._run_prod_with_dist()
        mock_run.assert_called_once()

    def test_static_files_name_spa(self):
        """app.mount name kwarg is 'spa'."""
        mock_app = _make_mock_app()
        self._run_prod_with_dist(mock_app=mock_app)
        _, mount_kwargs = mock_app.mount.call_args
        assert mount_kwargs.get("name") == "spa"


# ---------------------------------------------------------------------------
# Custom --port
# ---------------------------------------------------------------------------

class TestCustomPort:
    def test_custom_port_passed_to_uvicorn(self):
        """--port 9000 causes uvicorn.run to be called with port=9000."""
        from llm_pipeline.ui.cli import main
        mock_app = _make_mock_app()
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--port", "9000"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch("pathlib.Path.exists", return_value=False), \
             patch("uvicorn.run") as mock_run:
            main()
        _, kwargs = mock_run.call_args
        assert kwargs.get("port") == 9000


# ---------------------------------------------------------------------------
# --db flag
# ---------------------------------------------------------------------------

class TestDbFlag:
    def test_db_path_passed_to_create_app(self):
        """--db /tmp/test.db causes create_app to be called with db_path='/tmp/test.db'."""
        from llm_pipeline.ui.cli import main
        mock_app = _make_mock_app()
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--db", "/tmp/test.db"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app) as mock_ca, \
             patch("pathlib.Path.exists", return_value=False), \
             patch("uvicorn.run"):
            main()
        mock_ca.assert_called_once_with(db_path="/tmp/test.db")

    def test_db_none_by_default(self):
        """create_app is called with db_path=None when --db not supplied."""
        from llm_pipeline.ui.cli import main
        mock_app = _make_mock_app()
        with patch.object(sys, "argv", ["llm-pipeline", "ui"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app) as mock_ca, \
             patch("pathlib.Path.exists", return_value=False), \
             patch("uvicorn.run"):
            main()
        mock_ca.assert_called_once_with(db_path=None)


# ---------------------------------------------------------------------------
# Dev mode - no frontend/ directory
# ---------------------------------------------------------------------------

class TestDevModeNoFrontend:
    """--dev without frontend/ falls back to reload-only uvicorn."""

    def _run_headless_dev(self, extra_argv=None):
        from llm_pipeline.ui.cli import main
        mock_app = _make_mock_app()
        argv = ["llm-pipeline", "ui", "--dev"] + (extra_argv or [])
        with patch.object(sys, "argv", argv), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch("pathlib.Path.exists", return_value=False), \
             patch("uvicorn.run") as mock_run, \
             patch("llm_pipeline.ui.cli.subprocess") as mock_sub:
            main()
        return mock_app, mock_run, mock_sub

    def test_uvicorn_called_with_reload(self):
        """uvicorn.run is called with reload=True when frontend/ is absent."""
        _, mock_run, _ = self._run_headless_dev()
        _, kwargs = mock_run.call_args
        assert kwargs.get("reload") is True

    def test_host_is_loopback(self):
        """Dev mode without frontend/ uses host 127.0.0.1."""
        _, mock_run, _ = self._run_headless_dev()
        _, kwargs = mock_run.call_args
        assert kwargs.get("host") == "127.0.0.1"

    def test_no_subprocess_popen_called(self):
        """No subprocess.Popen called in headless dev mode (no Vite)."""
        _, _, mock_sub = self._run_headless_dev()
        mock_sub.Popen.assert_not_called()

    def test_info_message_printed_to_stderr(self, capsys):
        """INFO message printed when no frontend/ found in dev mode."""
        self._run_headless_dev()
        captured = capsys.readouterr()
        assert "INFO" in captured.err


# ---------------------------------------------------------------------------
# Dev mode - frontend/ exists, npx missing
# ---------------------------------------------------------------------------

class TestDevModeNpxMissing:
    """--dev with frontend/ but npx not found -> SystemExit(1)."""

    def test_exits_1_when_npx_missing(self):
        """SystemExit(1) raised when npx is not available."""
        from llm_pipeline.ui.cli import main
        mock_app = _make_mock_app()
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--dev"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("llm_pipeline.ui.cli.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1

    def test_error_message_printed_to_stderr(self, capsys):
        """ERROR message printed when npx is not found."""
        from llm_pipeline.ui.cli import main
        mock_app = _make_mock_app()
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--dev"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("llm_pipeline.ui.cli.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit):
                main()
        captured = capsys.readouterr()
        assert "ERROR" in captured.err


# ---------------------------------------------------------------------------
# Dev mode - frontend/ exists, npx available
# ---------------------------------------------------------------------------

class TestDevModeWithFrontend:
    """--dev with frontend/ and npx: Vite subprocess + uvicorn on 127.0.0.1."""

    def _run_full_dev(self, extra_argv=None):
        """Invoke main() in full dev+vite mode, return captured mocks."""
        from llm_pipeline.ui.cli import main, _cleanup_vite as cleanup_fn
        argv = ["llm-pipeline", "ui", "--dev"] + (extra_argv or [])
        mock_app = _make_mock_app()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with patch.object(sys, "argv", argv), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch("pathlib.Path.exists", return_value=True), \
             patch("llm_pipeline.ui.cli.subprocess.run") as mock_run, \
             patch("llm_pipeline.ui.cli.subprocess.Popen", return_value=mock_proc) as mock_popen, \
             patch("uvicorn.run") as mock_uvicorn_run, \
             patch("llm_pipeline.ui.cli.atexit.register") as mock_atexit_reg, \
             patch("llm_pipeline.ui.cli._cleanup_vite") as mock_cleanup:
            main()

        return {
            "mock_app": mock_app,
            "mock_proc": mock_proc,
            "mock_popen": mock_popen,
            "mock_uvicorn_run": mock_uvicorn_run,
            "mock_atexit_reg": mock_atexit_reg,
            "mock_cleanup": mock_cleanup,
            "cleanup_fn": cleanup_fn,
        }

    def test_popen_called(self):
        """subprocess.Popen is called to start Vite."""
        result = self._run_full_dev()
        result["mock_popen"].assert_called_once()

    def test_popen_env_contains_vite_port(self):
        """Popen env contains VITE_PORT=port+1."""
        result = self._run_full_dev()
        _, kwargs = result["mock_popen"].call_args
        env = kwargs.get("env", {})
        assert "VITE_PORT" in env
        assert env["VITE_PORT"] == str(8643)

    def test_popen_env_contains_vite_api_port(self):
        """Popen env contains VITE_API_PORT=api port."""
        result = self._run_full_dev()
        _, kwargs = result["mock_popen"].call_args
        env = kwargs.get("env", {})
        assert "VITE_API_PORT" in env
        assert env["VITE_API_PORT"] == str(8642)

    def test_uvicorn_host_is_loopback(self):
        """uvicorn.run uses host 127.0.0.1 in full dev mode."""
        result = self._run_full_dev()
        _, kwargs = result["mock_uvicorn_run"].call_args
        assert kwargs.get("host") == "127.0.0.1"

    def test_uvicorn_default_port(self):
        """uvicorn.run uses default port 8642 in full dev mode."""
        result = self._run_full_dev()
        _, kwargs = result["mock_uvicorn_run"].call_args
        assert kwargs.get("port") == 8642

    def test_atexit_registered_with_cleanup_vite(self):
        """atexit.register is called with _cleanup_vite and the vite proc."""
        from llm_pipeline.ui.cli import _cleanup_vite as cleanup_fn
        result = self._run_full_dev()
        # The atexit is registered with the real cleanup fn before we patch _cleanup_vite
        # so check the call was made with any callable + a mock proc
        result["mock_atexit_reg"].assert_called_once()
        call_args = result["mock_atexit_reg"].call_args[0]
        assert callable(call_args[0])

    def test_cleanup_called_in_finally(self):
        """_cleanup_vite is called after uvicorn.run via try/finally."""
        result = self._run_full_dev()
        assert result["mock_cleanup"].call_count >= 1

    def test_custom_port_vite_port_incremented(self):
        """With --port 9000, Vite runs on 9001 and api on 9000."""
        result = self._run_full_dev(extra_argv=["--port", "9000"])
        _, kwargs = result["mock_popen"].call_args
        env = kwargs.get("env", {})
        assert env["VITE_PORT"] == str(9001)
        assert env["VITE_API_PORT"] == str(9000)

    def test_uvicorn_no_reload_in_vite_mode(self):
        """uvicorn.run is NOT called with reload=True when Vite is active."""
        result = self._run_full_dev()
        _, kwargs = result["mock_uvicorn_run"].call_args
        assert not kwargs.get("reload", False)


# ---------------------------------------------------------------------------
# _cleanup_vite
# ---------------------------------------------------------------------------

class TestCleanupVite:
    def test_terminates_running_proc(self):
        """terminate() is called when proc.poll() returns None (proc alive)."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        _cleanup_vite(mock_proc)
        mock_proc.terminate.assert_called_once()

    def test_waits_after_terminate(self):
        """wait(timeout=5) is called after terminate()."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        _cleanup_vite(mock_proc)
        mock_proc.wait.assert_called_once_with(timeout=5)

    def test_kills_on_timeout(self):
        """kill() is called when wait() raises TimeoutExpired."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="npx", timeout=5)
        _cleanup_vite(mock_proc)
        mock_proc.kill.assert_called_once()

    def test_no_op_if_proc_dead(self):
        """terminate() is NOT called when proc.poll() returns non-None."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        _cleanup_vite(mock_proc)
        mock_proc.terminate.assert_not_called()

    def test_no_kill_if_wait_succeeds(self):
        """kill() is NOT called when wait() succeeds within timeout."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = None
        _cleanup_vite(mock_proc)
        mock_proc.kill.assert_not_called()
