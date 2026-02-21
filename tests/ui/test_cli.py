"""Tests for llm_pipeline.ui.cli - all code paths covered.

Patch targets for deferred imports:
  create_app       -> "llm_pipeline.ui.app.create_app"
  uvicorn.run      -> "uvicorn.run"
  StaticFiles      -> "starlette.staticfiles.StaticFiles"
  subprocess.run   -> "llm_pipeline.ui.cli.subprocess.run"
  subprocess.Popen -> "llm_pipeline.ui.cli.subprocess.Popen"
  atexit.register  -> "llm_pipeline.ui.cli.atexit.register"
  Path.exists      -> targeted side_effect keyed on path suffix, NOT global True/False
"""
import os
import signal
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from llm_pipeline.ui.cli import _cleanup_vite, _create_dev_app


# ---------------------------------------------------------------------------
# Path.exists helpers - targeted, not global
# ---------------------------------------------------------------------------

def _path_exists_side_effect(frontend_exists: bool, dist_exists: bool):
    """Return a side_effect for Path.exists that answers only the two paths
    cli.py checks (frontend/, frontend/dist/); all other paths use real
    filesystem behaviour."""
    real_exists = Path.exists

    def _side_effect(self: Path) -> bool:
        p = str(self)
        if p.endswith("frontend") and not p.endswith("frontend/dist") \
                and not p.endswith(r"frontend\dist"):
            # strip trailing sep variants
            stripped = p.rstrip("/\\")
            if stripped.endswith("frontend"):
                return frontend_exists
        if p.endswith("dist") or p.endswith("dist/") or p.endswith("dist\\"):
            return dist_exists
        return real_exists(self)

    return _side_effect


def _only_frontend_missing():
    """frontend/ absent -> dist/ irrelevant. Used by prod-no-dist and headless-dev."""
    return _path_exists_side_effect(frontend_exists=False, dist_exists=False)


def _only_dist_missing():
    """frontend/ present, dist/ absent."""
    return _path_exists_side_effect(frontend_exists=True, dist_exists=False)


def _both_present():
    """frontend/ and dist/ both present."""
    return _path_exists_side_effect(frontend_exists=True, dist_exists=True)


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
        from llm_pipeline.ui.cli import main
        if mock_app is None:
            mock_app = MagicMock()
        argv = ["llm-pipeline", "ui"] + (extra_argv or [])
        with patch.object(sys, "argv", argv), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app) as mock_ca, \
             patch.object(Path, "exists", _only_frontend_missing()), \
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
        mock_app = MagicMock()
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
            mock_app = MagicMock()
        with patch.object(sys, "argv", ["llm-pipeline", "ui"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch.object(Path, "exists", _both_present()), \
             patch("starlette.staticfiles.StaticFiles") as mock_sf_cls, \
             patch("uvicorn.run") as mock_run:
            main()
        return mock_app, mock_sf_cls, mock_run

    def test_static_files_mounted_on_root(self):
        """app.mount is called with '/' when dist/ exists."""
        mock_app = MagicMock()
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
        mock_app = MagicMock()
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
        mock_app = MagicMock()
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--port", "9000"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch.object(Path, "exists", _only_frontend_missing()), \
             patch("uvicorn.run") as mock_run:
            main()
        _, kwargs = mock_run.call_args
        assert kwargs.get("port") == 9000


# ---------------------------------------------------------------------------
# --db flag
# ---------------------------------------------------------------------------

class TestDbFlag:
    def test_db_path_passed_to_create_app(self):
        """--db /tmp/test.db causes create_app(db_path='/tmp/test.db')."""
        from llm_pipeline.ui.cli import main
        mock_app = MagicMock()
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--db", "/tmp/test.db"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app) as mock_ca, \
             patch.object(Path, "exists", _only_frontend_missing()), \
             patch("uvicorn.run"):
            main()
        mock_ca.assert_called_once_with(db_path="/tmp/test.db")

    def test_db_none_by_default(self):
        """create_app is called with db_path=None when --db not supplied."""
        from llm_pipeline.ui.cli import main
        mock_app = MagicMock()
        with patch.object(sys, "argv", ["llm-pipeline", "ui"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app) as mock_ca, \
             patch.object(Path, "exists", _only_frontend_missing()), \
             patch("uvicorn.run"):
            main()
        mock_ca.assert_called_once_with(db_path=None)


# ---------------------------------------------------------------------------
# Dev mode - no frontend/ directory (headless reload mode)
# ---------------------------------------------------------------------------

class TestDevModeNoFrontend:
    """--dev without frontend/ -> uvicorn factory mode with reload."""

    def _run_headless_dev(self, extra_argv=None):
        from llm_pipeline.ui.cli import main
        argv = ["llm-pipeline", "ui", "--dev"] + (extra_argv or [])
        with patch.object(sys, "argv", argv), \
             patch.object(Path, "exists", _only_frontend_missing()), \
             patch("uvicorn.run") as mock_run, \
             patch("llm_pipeline.ui.cli.subprocess") as mock_sub:
            main()
        return mock_run, mock_sub

    def test_uvicorn_called_with_reload(self):
        """uvicorn.run is called with reload=True when frontend/ is absent."""
        mock_run, _ = self._run_headless_dev()
        _, kwargs = mock_run.call_args
        assert kwargs.get("reload") is True

    def test_uvicorn_called_with_factory_true(self):
        """uvicorn.run is called with factory=True in headless dev mode."""
        mock_run, _ = self._run_headless_dev()
        _, kwargs = mock_run.call_args
        assert kwargs.get("factory") is True

    def test_uvicorn_first_arg_is_factory_import_string(self):
        """uvicorn.run first positional arg is the factory import string."""
        mock_run, _ = self._run_headless_dev()
        args, _ = mock_run.call_args
        assert args[0] == "llm_pipeline.ui.cli:_create_dev_app"

    def test_host_is_loopback(self):
        """Dev mode without frontend/ uses host 127.0.0.1."""
        mock_run, _ = self._run_headless_dev()
        _, kwargs = mock_run.call_args
        assert kwargs.get("host") == "127.0.0.1"

    def test_no_subprocess_popen_called(self):
        """No subprocess.Popen called in headless dev mode (no Vite)."""
        _, mock_sub = self._run_headless_dev()
        mock_sub.Popen.assert_not_called()

    def test_info_message_printed_to_stderr(self, capsys):
        """INFO message printed when no frontend/ found in dev mode."""
        self._run_headless_dev()
        captured = capsys.readouterr()
        assert "INFO" in captured.err

    def test_db_flag_sets_env_var(self):
        """--db /tmp/x.db sets LLM_PIPELINE_DB env var for factory reload."""
        from llm_pipeline.ui.cli import main
        captured_env: dict = {}
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--dev", "--db", "/tmp/x.db"]), \
             patch.object(Path, "exists", _only_frontend_missing()), \
             patch("uvicorn.run"), \
             patch.dict(os.environ, {}, clear=False):
            main()
            captured_env["val"] = os.environ.get("LLM_PIPELINE_DB")
        assert captured_env["val"] == "/tmp/x.db"


# ---------------------------------------------------------------------------
# _create_dev_app factory
# ---------------------------------------------------------------------------

class TestCreateDevApp:
    """_create_dev_app reads LLM_PIPELINE_DB env var and calls create_app."""

    def test_reads_env_var_and_passes_to_create_app(self):
        """_create_dev_app passes LLM_PIPELINE_DB value as db_path."""
        mock_app = MagicMock()
        with patch.dict(os.environ, {"LLM_PIPELINE_DB": "/tmp/env.db"}), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app) as mock_ca:
            result = _create_dev_app()
        mock_ca.assert_called_once_with(db_path="/tmp/env.db")

    def test_passes_none_when_env_var_absent(self):
        """_create_dev_app passes db_path=None when LLM_PIPELINE_DB not set."""
        mock_app = MagicMock()
        env = {k: v for k, v in os.environ.items() if k != "LLM_PIPELINE_DB"}
        with patch.dict(os.environ, env, clear=True), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app) as mock_ca:
            result = _create_dev_app()
        mock_ca.assert_called_once_with(db_path=None)

    def test_returns_create_app_result(self):
        """_create_dev_app returns the value returned by create_app."""
        sentinel = object()
        with patch.dict(os.environ, {}, clear=False), \
             patch("llm_pipeline.ui.app.create_app", return_value=sentinel):
            result = _create_dev_app()
        assert result is sentinel


# ---------------------------------------------------------------------------
# Dev mode - frontend/ exists, npx missing
# ---------------------------------------------------------------------------

class TestDevModeNpxMissing:
    """--dev with frontend/ but npx not found -> SystemExit(1)."""

    def test_exits_1_when_npx_missing(self):
        """SystemExit(1) raised when npx is not available."""
        from llm_pipeline.ui.cli import main
        mock_app = MagicMock()
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--dev"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch.object(Path, "exists", _only_dist_missing()), \
             patch("llm_pipeline.ui.cli.subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(SystemExit) as exc_info:
                main()
        assert exc_info.value.code == 1

    def test_error_message_printed_to_stderr(self, capsys):
        """ERROR message printed when npx is not found."""
        from llm_pipeline.ui.cli import main
        mock_app = MagicMock()
        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--dev"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch.object(Path, "exists", _only_dist_missing()), \
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
        from llm_pipeline.ui.cli import main, _cleanup_vite as cleanup_fn
        argv = ["llm-pipeline", "ui", "--dev"] + (extra_argv or [])
        mock_app = MagicMock()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        # Mock the cli module's signal reference; give it SIGTERM so the guard fires.
        mock_signal_mod = MagicMock()
        mock_signal_mod.SIGTERM = signal.SIGTERM

        with patch.object(sys, "argv", argv), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch.object(Path, "exists", _only_dist_missing()), \
             patch("llm_pipeline.ui.cli.subprocess.run") as mock_sub_run, \
             patch("llm_pipeline.ui.cli.subprocess.Popen", return_value=mock_proc) as mock_popen, \
             patch("uvicorn.run") as mock_uvicorn_run, \
             patch("llm_pipeline.ui.cli.atexit.register") as mock_atexit_reg, \
             patch("llm_pipeline.ui.cli._cleanup_vite") as mock_cleanup, \
             patch("llm_pipeline.ui.cli.signal", mock_signal_mod):
            main()

        return {
            "mock_app": mock_app,
            "mock_proc": mock_proc,
            "mock_popen": mock_popen,
            "mock_uvicorn_run": mock_uvicorn_run,
            "mock_atexit_reg": mock_atexit_reg,
            "mock_cleanup": mock_cleanup,
            "mock_signal_signal": mock_signal_mod.signal,
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
        """atexit.register is called with a callable and the vite proc."""
        result = self._run_full_dev()
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

    def test_sigterm_handler_registered_on_unix(self):
        """signal.signal(SIGTERM, ...) is called when SIGTERM is available."""
        result = self._run_full_dev()
        mock_sig = result["mock_signal_signal"]
        mock_sig.assert_called_once()
        call_args = mock_sig.call_args[0]
        assert call_args[0] == signal.SIGTERM
        assert callable(call_args[1])

    def test_sigterm_handler_skipped_when_no_sigterm(self):
        """signal.signal is NOT called when signal.SIGTERM is absent (Windows guard).

        Replace cli's signal module reference with a MagicMock whose spec excludes
        SIGTERM, so hasattr(signal, 'SIGTERM') returns False inside _start_vite_mode.
        """
        from llm_pipeline.ui.cli import main
        mock_app = MagicMock()
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        # MagicMock with spec=['signal'] has no SIGTERM -> hasattr returns False
        mock_signal_mod = MagicMock(spec=["signal"])
        mock_signal_mod.signal = MagicMock()

        with patch.object(sys, "argv", ["llm-pipeline", "ui", "--dev"]), \
             patch("llm_pipeline.ui.app.create_app", return_value=mock_app), \
             patch.object(Path, "exists", _only_dist_missing()), \
             patch("llm_pipeline.ui.cli.subprocess.run"), \
             patch("llm_pipeline.ui.cli.subprocess.Popen", return_value=mock_proc), \
             patch("uvicorn.run"), \
             patch("llm_pipeline.ui.cli.atexit.register"), \
             patch("llm_pipeline.ui.cli._cleanup_vite"), \
             patch("llm_pipeline.ui.cli.signal", mock_signal_mod):
            main()

        mock_signal_mod.signal.assert_not_called()


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


# ---------------------------------------------------------------------------
# Import guard - _run_ui catches ImportError for missing [ui] deps
# ---------------------------------------------------------------------------

class TestImportGuardCli:
    """_run_ui() catches ImportError for known UI deps and exits with message."""

    def test_missing_fastapi_exits_1(self):
        """ImportError for 'fastapi' triggers sys.exit(1)."""
        from llm_pipeline.ui.cli import _run_ui
        args = MagicMock()
        args.dev = False
        with patch("llm_pipeline.ui.app.create_app", side_effect=ImportError("fastapi", name="fastapi")):
            with pytest.raises(SystemExit) as exc_info:
                _run_ui(args)
        assert exc_info.value.code == 1

    def test_missing_fastapi_prints_install_hint(self, capsys):
        """ImportError for 'fastapi' prints install instruction to stderr."""
        from llm_pipeline.ui.cli import _run_ui
        args = MagicMock()
        args.dev = False
        with patch("llm_pipeline.ui.app.create_app", side_effect=ImportError("fastapi", name="fastapi")):
            with pytest.raises(SystemExit):
                _run_ui(args)
        captured = capsys.readouterr()
        assert "pip install llm-pipeline[ui]" in captured.err

    def test_missing_uvicorn_exits_1(self):
        """ImportError for 'uvicorn' triggers sys.exit(1)."""
        from llm_pipeline.ui.cli import _run_ui
        args = MagicMock()
        args.dev = True
        args.db = None
        with patch.object(Path, "exists", _only_frontend_missing()), \
             patch("uvicorn.run", side_effect=ImportError("uvicorn", name="uvicorn")):
            with pytest.raises(SystemExit) as exc_info:
                _run_ui(args)
        assert exc_info.value.code == 1

    def test_unknown_import_error_reraised(self):
        """ImportError for unknown module (not a UI dep) is re-raised."""
        from llm_pipeline.ui.cli import _run_ui
        args = MagicMock()
        args.dev = False
        with patch("llm_pipeline.ui.app.create_app", side_effect=ImportError("bogus", name="bogus")):
            with pytest.raises(ImportError, match="bogus"):
                _run_ui(args)
