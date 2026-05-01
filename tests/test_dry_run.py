"""Tests for ``llm_pipeline._dry_run``.

The shared dry-run context is the single mechanism every CLI
subcommand uses to enter "compute the diff but don't mutate" mode.
These tests pin its behaviour:

- Default state is "not dry-run" (production-safe default).
- ``dry_run_mode(enabled=True)`` flips the flag inside its block;
  ``is_dry_run()`` returns True there.
- The flag is restored on exit, even if the block raises.
- Nested scopes don't leak the inner value to the outer scope.
- ``enabled=False`` is a deliberate no-op so callers can write
  ``with dry_run_mode(enabled=config.dry_run):`` unconditionally.
"""
from __future__ import annotations

import pytest

from llm_pipeline._dry_run import dry_run_mode, is_dry_run


class TestIsDryRunDefault:
    def test_default_is_false(self):
        assert is_dry_run() is False


class TestDryRunMode:
    def test_enabled_true_flips_the_flag_inside_block(self):
        assert is_dry_run() is False
        with dry_run_mode(enabled=True):
            assert is_dry_run() is True
        assert is_dry_run() is False

    def test_enabled_false_keeps_flag_off(self):
        with dry_run_mode(enabled=False):
            assert is_dry_run() is False

    def test_default_enabled_is_true(self):
        # ``dry_run_mode()`` with no args is the "yes, dry-run" form.
        with dry_run_mode():
            assert is_dry_run() is True

    def test_flag_restored_on_exception(self):
        with pytest.raises(RuntimeError):
            with dry_run_mode(enabled=True):
                assert is_dry_run() is True
                raise RuntimeError("boom")
        assert is_dry_run() is False

    def test_nested_scopes_restore_outer_value(self):
        with dry_run_mode(enabled=True):
            assert is_dry_run() is True
            with dry_run_mode(enabled=False):
                assert is_dry_run() is False
            # Outer scope's True is restored after inner exits.
            assert is_dry_run() is True
        assert is_dry_run() is False

    def test_outer_disabled_inner_enabled(self):
        with dry_run_mode(enabled=False):
            assert is_dry_run() is False
            with dry_run_mode(enabled=True):
                assert is_dry_run() is True
            assert is_dry_run() is False
