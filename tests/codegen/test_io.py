"""Tests for ``llm_pipeline.codegen.io`` — path guard + atomic write."""
from __future__ import annotations

from pathlib import Path

import libcst as cst
import pytest

from llm_pipeline.codegen.io import (
    CodegenPathError,
    LLM_PIPELINES_ROOT_ENV,
    assert_under_root,
    read_module,
    resolve_root,
    write_module,
    write_module_if_changed,
)


# ---------------------------------------------------------------------------
# resolve_root
# ---------------------------------------------------------------------------


class TestResolveRoot:
    def test_explicit_root_wins(self, tmp_path: Path):
        result = resolve_root(tmp_path)
        assert result == tmp_path.resolve()

    def test_env_var_overrides_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setenv(LLM_PIPELINES_ROOT_ENV, str(tmp_path))
        result = resolve_root()
        assert result == tmp_path.resolve()

    def test_default_is_cwd_relative(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.delenv(LLM_PIPELINES_ROOT_ENV, raising=False)
        monkeypatch.chdir(tmp_path)
        result = resolve_root()
        assert result == (tmp_path / "llm_pipelines").resolve()


# ---------------------------------------------------------------------------
# assert_under_root
# ---------------------------------------------------------------------------


class TestAssertUnderRoot:
    def test_path_under_root_passes(self, tmp_path: Path):
        target = tmp_path / "variables" / "foo.py"
        # Doesn't have to exist; the guard works on resolved paths
        result = assert_under_root(target, root=tmp_path)
        assert result == target.resolve()

    def test_path_outside_root_raises(self, tmp_path: Path):
        outside = tmp_path.parent / "framework_code.py"
        with pytest.raises(CodegenPathError) as exc_info:
            assert_under_root(outside, root=tmp_path)
        assert "not under" in str(exc_info.value)

    def test_path_traversal_blocked(self, tmp_path: Path):
        # ../ escape attempt — path resolution catches it
        sneaky = tmp_path / "subdir" / ".." / ".." / "outside.py"
        with pytest.raises(CodegenPathError):
            assert_under_root(sneaky, root=tmp_path)

    def test_root_itself_passes(self, tmp_path: Path):
        # Writing AT the root (e.g. an __init__.py) is fine
        result = assert_under_root(tmp_path, root=tmp_path)
        assert result == tmp_path.resolve()


# ---------------------------------------------------------------------------
# read_module
# ---------------------------------------------------------------------------


class TestReadModule:
    def test_reads_and_parses(self, tmp_path: Path):
        path = tmp_path / "mod.py"
        path.write_text("x = 1\n", encoding="utf-8")
        module = read_module(path)
        assert isinstance(module, cst.Module)
        assert module.code == "x = 1\n"

    def test_read_is_not_path_guarded(self, tmp_path: Path):
        # Reading is unguarded — you can inspect framework code
        outside = tmp_path / "outside.py"
        outside.write_text("x = 2\n", encoding="utf-8")
        # No CodegenPathError raised because we're reading, not writing
        module = read_module(outside)
        assert module.code == "x = 2\n"


# ---------------------------------------------------------------------------
# write_module
# ---------------------------------------------------------------------------


class TestWriteModule:
    def test_writes_under_root(self, tmp_path: Path):
        target = tmp_path / "out.py"
        module = cst.parse_module("x = 1\n")
        write_module(target, module, root=tmp_path)
        assert target.read_text(encoding="utf-8") == "x = 1\n"

    def test_creates_parent_dirs(self, tmp_path: Path):
        target = tmp_path / "deep" / "nested" / "file.py"
        module = cst.parse_module("x = 1\n")
        write_module(target, module, root=tmp_path)
        assert target.exists()

    def test_path_outside_root_blocked(self, tmp_path: Path):
        outside = tmp_path.parent / "outside.py"
        module = cst.parse_module("x = 1\n")
        with pytest.raises(CodegenPathError):
            write_module(outside, module, root=tmp_path)
        assert not outside.exists()

    def test_overwrites_existing(self, tmp_path: Path):
        target = tmp_path / "out.py"
        target.write_text("old = 1\n", encoding="utf-8")
        module = cst.parse_module("new = 2\n")
        write_module(target, module, root=tmp_path)
        assert target.read_text(encoding="utf-8") == "new = 2\n"


# ---------------------------------------------------------------------------
# write_module_if_changed
# ---------------------------------------------------------------------------


class TestWriteModuleIfChanged:
    def test_writes_when_file_missing(self, tmp_path: Path):
        target = tmp_path / "out.py"
        module = cst.parse_module("x = 1\n")
        wrote = write_module_if_changed(target, module, root=tmp_path)
        assert wrote is True
        assert target.read_text(encoding="utf-8") == "x = 1\n"

    def test_writes_when_content_differs(self, tmp_path: Path):
        target = tmp_path / "out.py"
        target.write_text("old = 1\n", encoding="utf-8")
        module = cst.parse_module("new = 2\n")
        wrote = write_module_if_changed(target, module, root=tmp_path)
        assert wrote is True
        assert target.read_text(encoding="utf-8") == "new = 2\n"

    def test_skips_when_content_matches(self, tmp_path: Path):
        target = tmp_path / "out.py"
        target.write_text("x = 1\n", encoding="utf-8")
        original_mtime = target.stat().st_mtime_ns
        module = cst.parse_module("x = 1\n")
        wrote = write_module_if_changed(target, module, root=tmp_path)
        assert wrote is False
        # mtime unchanged — we didn't touch the file
        assert target.stat().st_mtime_ns == original_mtime

    def test_path_guard_still_applies(self, tmp_path: Path):
        outside = tmp_path.parent / "outside.py"
        module = cst.parse_module("x = 1\n")
        with pytest.raises(CodegenPathError):
            write_module_if_changed(outside, module, root=tmp_path)
