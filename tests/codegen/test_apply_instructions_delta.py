"""Tests for ``llm_pipeline.codegen.api.apply_instructions_delta``.

End-to-end coverage of the libcst-based replacement for
``creator/ast_modifier.apply_instructions_delta_to_file``. Each test
writes a real source file under a tmp ``llm_pipelines/`` root, runs
the delta, and asserts the file's new state.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from llm_pipeline.codegen.api import CodegenError, apply_instructions_delta


def _write_source(root: Path, name: str, content: str) -> Path:
    """Helper: write a Python file under ``root`` and return its path."""
    path = root / f"{name}.py"
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Add op
# ---------------------------------------------------------------------------


class TestAddOp:
    def test_appends_field(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = ''\n",
        )
        report = apply_instructions_delta(
            source_file=src,
            class_name="Result",
            delta=[{
                "op": "add",
                "field": "confidence",
                "type_str": "float",
                "default": 0.5,
            }],
            root=tmp_path,
            write_backup=False,
        )
        assert report["added"] == ["confidence"]
        assert report["modified"] == []
        new_src = src.read_text(encoding="utf-8")
        assert "sentiment: str = ''" in new_src
        assert "confidence: float = 0.5" in new_src

    def test_existing_field_raises(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = ''\n",
        )
        with pytest.raises(CodegenError) as exc_info:
            apply_instructions_delta(
                source_file=src,
                class_name="Result",
                delta=[{
                    "op": "add",
                    "field": "sentiment",
                    "type_str": "str",
                    "default": "",
                }],
                root=tmp_path,
                write_backup=False,
            )
        assert "already present" in str(exc_info.value)

    def test_missing_type_str_raises(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = ''\n",
        )
        with pytest.raises(CodegenError) as exc_info:
            apply_instructions_delta(
                source_file=src,
                class_name="Result",
                delta=[{
                    "op": "add",
                    "field": "confidence",
                    # type_str missing
                    "default": 0.5,
                }],
                root=tmp_path,
                write_backup=False,
            )
        assert "type_str" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Modify op
# ---------------------------------------------------------------------------


class TestModifyOp:
    def test_rewrites_existing_field(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = 'old'\n",
        )
        report = apply_instructions_delta(
            source_file=src,
            class_name="Result",
            delta=[{
                "op": "modify",
                "field": "sentiment",
                "type_str": "str",
                "default": "new",
            }],
            root=tmp_path,
            write_backup=False,
        )
        assert report["added"] == []
        assert report["modified"] == ["sentiment"]
        new_src = src.read_text(encoding="utf-8")
        assert "sentiment: str = 'new'" in new_src
        assert "sentiment: str = 'old'" not in new_src

    def test_omitted_type_str_preserves_annotation(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = 'old'\n",
        )
        apply_instructions_delta(
            source_file=src,
            class_name="Result",
            delta=[{
                "op": "modify",
                "field": "sentiment",
                # type_str omitted — annotation should stay 'str'
                "default": "new",
            }],
            root=tmp_path,
            write_backup=False,
        )
        new_src = src.read_text(encoding="utf-8")
        assert "sentiment: str = 'new'" in new_src
        # The annotation isn't replaced with 'Any' or anything else
        assert "Any" not in new_src

    def test_missing_field_raises(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = ''\n",
        )
        with pytest.raises(CodegenError) as exc_info:
            apply_instructions_delta(
                source_file=src,
                class_name="Result",
                delta=[{
                    "op": "modify",
                    "field": "nonexistent",
                    "default": "x",
                }],
                root=tmp_path,
                write_backup=False,
            )
        assert "not present" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Compound deltas
# ---------------------------------------------------------------------------


class TestCompoundDeltas:
    def test_add_and_modify_same_call(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = 'old'\n",
        )
        report = apply_instructions_delta(
            source_file=src,
            class_name="Result",
            delta=[
                {"op": "modify", "field": "sentiment", "default": "new"},
                {
                    "op": "add", "field": "confidence",
                    "type_str": "float", "default": 0.5,
                },
            ],
            root=tmp_path,
            write_backup=False,
        )
        assert report["added"] == ["confidence"]
        assert report["modified"] == ["sentiment"]
        new_src = src.read_text(encoding="utf-8")
        assert "sentiment: str = 'new'" in new_src
        assert "confidence: float = 0.5" in new_src

    def test_preserves_comments_around_changes(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n"
            "    # important field\n"
            "    sentiment: str = 'old'\n",
        )
        apply_instructions_delta(
            source_file=src,
            class_name="Result",
            delta=[{"op": "modify", "field": "sentiment", "default": "new"}],
            root=tmp_path,
            write_backup=False,
        )
        new_src = src.read_text(encoding="utf-8")
        assert "# important field" in new_src
        assert "sentiment: str = 'new'" in new_src


# ---------------------------------------------------------------------------
# Path guard + missing file
# ---------------------------------------------------------------------------


class TestPathGuard:
    def test_path_outside_root_raises(self, tmp_path: Path):
        # Create an "outside" file the guard should block writes to
        outside_dir = tmp_path.parent / "outside_codegen"
        outside_dir.mkdir(parents=True, exist_ok=True)
        outside = outside_dir / "framework_code.py"
        outside.write_text("class Result:\n    x: int = 0\n", encoding="utf-8")
        try:
            with pytest.raises(CodegenError) as exc_info:
                apply_instructions_delta(
                    source_file=outside,
                    class_name="Result",
                    delta=[{
                        "op": "modify", "field": "x", "default": 99,
                    }],
                    root=tmp_path,
                    write_backup=False,
                )
            assert "not under" in str(exc_info.value)
            # File unchanged
            assert outside.read_text(encoding="utf-8") == (
                "class Result:\n    x: int = 0\n"
            )
        finally:
            outside.unlink(missing_ok=True)
            outside_dir.rmdir()

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(CodegenError) as exc_info:
            apply_instructions_delta(
                source_file=tmp_path / "does_not_exist.py",
                class_name="X",
                delta=[],
                root=tmp_path,
                write_backup=False,
            )
        assert "does not exist" in str(exc_info.value)

    def test_class_not_found_raises(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Other:\n    x: int = 0\n",
        )
        with pytest.raises(CodegenError) as exc_info:
            apply_instructions_delta(
                source_file=src,
                class_name="Result",  # not present
                delta=[],
                root=tmp_path,
                write_backup=False,
            )
        assert "not found" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------


class TestBackups:
    def test_writes_bak_when_requested(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = 'old'\n",
        )
        original_content = src.read_text(encoding="utf-8")
        apply_instructions_delta(
            source_file=src,
            class_name="Result",
            delta=[{"op": "modify", "field": "sentiment", "default": "new"}],
            root=tmp_path,
            write_backup=True,
        )
        bak = src.with_suffix(src.suffix + ".bak")
        assert bak.exists()
        assert bak.read_text(encoding="utf-8") == original_content

    def test_no_bak_when_disabled(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = 'old'\n",
        )
        apply_instructions_delta(
            source_file=src,
            class_name="Result",
            delta=[{"op": "modify", "field": "sentiment", "default": "new"}],
            root=tmp_path,
            write_backup=False,
        )
        bak = src.with_suffix(src.suffix + ".bak")
        assert not bak.exists()


# ---------------------------------------------------------------------------
# Output validity
# ---------------------------------------------------------------------------


class TestOutputValidity:
    def test_modified_source_re_parses_cleanly(self, tmp_path: Path):
        src = _write_source(
            tmp_path, "instructions",
            "class Result:\n    sentiment: str = ''\n",
        )
        apply_instructions_delta(
            source_file=src,
            class_name="Result",
            delta=[
                {
                    "op": "add", "field": "confidence",
                    "type_str": "float", "default": 0.5,
                },
            ],
            root=tmp_path,
            write_backup=False,
        )
        # Compile the result — fails on any syntax issue
        new_src = src.read_text(encoding="utf-8")
        compile(new_src, str(src), "exec")
