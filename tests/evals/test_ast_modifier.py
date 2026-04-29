"""Tests for ``apply_instructions_delta_to_file``.

Each test writes a tiny INSTRUCTIONS class file into ``tmp_path``,
applies a delta via the AST helper, and asserts the rewritten source
parses cleanly + carries the expected fields. Re-importing the
rewritten file would require module-loader gymnastics; comparing the
source text + AST is enough to pin behaviour at this layer.
"""
from __future__ import annotations

import ast
import textwrap
from pathlib import Path

import pytest

from llm_pipeline.creator.ast_modifier import (
    ASTModificationError,
    apply_instructions_delta_to_file,
)


def _write_source(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "schema.py"
    path.write_text(textwrap.dedent(source).strip() + "\n", encoding="utf-8")
    return path


def _field_defaults(source: str, class_name: str) -> dict[str, object]:
    """Return ``{field_name: default_value_repr}`` for a class in ``source``."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            out: dict[str, object] = {}
            for child in node.body:
                if (
                    isinstance(child, ast.AnnAssign)
                    and isinstance(child.target, ast.Name)
                    and child.value is not None
                ):
                    out[child.target.id] = ast.unparse(child.value)
            return out
    raise AssertionError(f"class {class_name} not found")


# ---------------------------------------------------------------------------
# add op
# ---------------------------------------------------------------------------


class TestAddField:
    def test_appends_simple_field(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class Sentiment:
                label: str = ""
                score: float = 0.0
        """)
        result = apply_instructions_delta_to_file(
            source_file=path,
            class_name="Sentiment",
            delta=[
                {"op": "add", "field": "intensity", "type_str": "float", "default": 0.5},
            ],
            write_backup=False,
        )
        defaults = _field_defaults(path.read_text(), "Sentiment")
        assert defaults["intensity"] == "0.5"
        assert result["added"] == ["intensity"]

    def test_string_default_quoted(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        apply_instructions_delta_to_file(
            source_file=path, class_name="S",
            delta=[
                {"op": "add", "field": "tag", "type_str": "str", "default": "neutral"},
            ],
            write_backup=False,
        )
        defaults = _field_defaults(path.read_text(), "S")
        assert defaults["tag"] == "'neutral'"

    def test_optional_type_emitted(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        apply_instructions_delta_to_file(
            source_file=path, class_name="S",
            delta=[
                {
                    "op": "add",
                    "field": "ref",
                    "type_str": "Optional[str]",
                    "default": None,
                },
            ],
            write_backup=False,
        )
        text = path.read_text()
        assert "ref: Optional[str] = None" in text

    def test_re_add_existing_field_rejected(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        with pytest.raises(ASTModificationError):
            apply_instructions_delta_to_file(
                source_file=path, class_name="S",
                delta=[
                    {"op": "add", "field": "label", "type_str": "str", "default": ""},
                ],
                write_backup=False,
            )

    def test_writes_backup_by_default(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        apply_instructions_delta_to_file(
            source_file=path, class_name="S",
            delta=[
                {"op": "add", "field": "x", "type_str": "int", "default": 1},
            ],
        )
        bak = path.with_suffix(".py.bak")
        assert bak.exists()
        assert "label" in bak.read_text()
        assert "x: int = 1" not in bak.read_text()  # backup is the original


# ---------------------------------------------------------------------------
# modify op
# ---------------------------------------------------------------------------


class TestModifyField:
    def test_rewrites_default(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        apply_instructions_delta_to_file(
            source_file=path, class_name="S",
            delta=[
                {"op": "modify", "field": "label", "default": "neutral"},
            ],
            write_backup=False,
        )
        defaults = _field_defaults(path.read_text(), "S")
        assert defaults["label"] == "'neutral'"

    def test_modify_missing_field_rejected(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        with pytest.raises(ASTModificationError):
            apply_instructions_delta_to_file(
                source_file=path, class_name="S",
                delta=[
                    {"op": "modify", "field": "ghost", "default": "x"},
                ],
                write_backup=False,
            )

    def test_modify_with_explicit_type_str(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        apply_instructions_delta_to_file(
            source_file=path, class_name="S",
            delta=[
                {"op": "modify", "field": "label", "type_str": "Optional[str]", "default": None},
            ],
            write_backup=False,
        )
        text = path.read_text()
        assert "label: Optional[str] = None" in text


# ---------------------------------------------------------------------------
# Multi-op + edge cases
# ---------------------------------------------------------------------------


class TestComposite:
    def test_add_then_modify_same_field_works(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        apply_instructions_delta_to_file(
            source_file=path, class_name="S",
            delta=[
                {"op": "add", "field": "score", "type_str": "float", "default": 0.0},
                {"op": "modify", "field": "score", "default": 0.5},
            ],
            write_backup=False,
        )
        defaults = _field_defaults(path.read_text(), "S")
        assert defaults["score"] == "0.5"

    def test_class_not_found_raises(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        with pytest.raises(ASTModificationError, match="not found"):
            apply_instructions_delta_to_file(
                source_file=path, class_name="Missing",
                delta=[
                    {"op": "add", "field": "x", "type_str": "int", "default": 1},
                ],
                write_backup=False,
            )

    def test_unsupported_op_rejected(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            class S:
                label: str = ""
        """)
        with pytest.raises(ASTModificationError, match="unsupported op"):
            apply_instructions_delta_to_file(
                source_file=path, class_name="S",
                delta=[{"op": "remove", "field": "label"}],
                write_backup=False,
            )

    def test_resulting_file_is_syntactically_valid(self, tmp_path: Path):
        path = _write_source(tmp_path, """
            from typing import Optional


            class S:
                label: str = ""
                score: float = 0.0
        """)
        apply_instructions_delta_to_file(
            source_file=path, class_name="S",
            delta=[
                {"op": "add", "field": "intensity", "type_str": "float", "default": 0.5},
                {"op": "modify", "field": "label", "default": "neutral"},
            ],
            write_backup=False,
        )
        # ast.parse raises if the splice produced invalid syntax.
        ast.parse(path.read_text())
