"""Tests for ``llm_pipeline.codegen.transformers``."""
from __future__ import annotations

import libcst as cst

from llm_pipeline.codegen.transformers import (
    AddFieldToClass,
    ModifyFieldOnClass,
    collect_class_field_names,
    find_class,
)


# ---------------------------------------------------------------------------
# AddFieldToClass
# ---------------------------------------------------------------------------


class TestAddFieldToClass:
    def test_appends_to_class_body(self):
        source = (
            "class Inputs:\n"
            "    text: str = ''\n"
        )
        new_stmt = cst.parse_statement("sentiment: str = ''")
        transformer = AddFieldToClass("Inputs", new_stmt)
        modified = cst.parse_module(source).visit(transformer)
        assert "sentiment: str = ''" in modified.code
        assert "text: str = ''" in modified.code
        assert transformer.visited_target

    def test_preserves_comments(self):
        source = (
            "class Inputs:\n"
            "    # important field\n"
            "    text: str = ''\n"
        )
        new_stmt = cst.parse_statement("sentiment: str = ''")
        transformer = AddFieldToClass("Inputs", new_stmt)
        modified = cst.parse_module(source).visit(transformer)
        assert "# important field" in modified.code
        assert "sentiment: str = ''" in modified.code

    def test_target_class_missing_visited_target_false(self):
        source = "class OtherClass:\n    x: int = 0\n"
        new_stmt = cst.parse_statement("y: int = 0")
        transformer = AddFieldToClass("Inputs", new_stmt)
        modified = cst.parse_module(source).visit(transformer)
        assert not transformer.visited_target
        # Source unchanged
        assert "Inputs" not in modified.code

    def test_only_modifies_named_class_not_others(self):
        source = (
            "class A:\n    x: int = 0\n\n"
            "class B:\n    y: int = 0\n"
        )
        new_stmt = cst.parse_statement("z: int = 99")
        transformer = AddFieldToClass("A", new_stmt)
        modified = cst.parse_module(source).visit(transformer)
        # A got the new field
        assert "z: int = 99" in modified.code
        # B is untouched
        rendered = modified.code
        b_section = rendered[rendered.index("class B:"):]
        assert "z: int = 99" not in b_section


# ---------------------------------------------------------------------------
# ModifyFieldOnClass
# ---------------------------------------------------------------------------


class TestModifyFieldOnClass:
    def test_replaces_field(self):
        source = (
            "class Inputs:\n"
            "    text: str = 'old'\n"
            "    count: int = 0\n"
        )
        new_stmt = cst.parse_statement("text: str = 'new'")
        transformer = ModifyFieldOnClass("Inputs", "text", new_stmt)
        modified = cst.parse_module(source).visit(transformer)
        assert "text: str = 'new'" in modified.code
        assert "text: str = 'old'" not in modified.code
        # Other field untouched
        assert "count: int = 0" in modified.code
        assert transformer.visited_target
        assert transformer.visited_field

    def test_preserves_field_position(self):
        source = (
            "class Inputs:\n"
            "    a: int = 1\n"
            "    b: str = 'old'\n"
            "    c: int = 3\n"
        )
        new_stmt = cst.parse_statement("b: str = 'new'")
        transformer = ModifyFieldOnClass("Inputs", "b", new_stmt)
        modified = cst.parse_module(source).visit(transformer)
        rendered = modified.code
        # b stays in the middle, not appended at the end
        a_idx = rendered.index("a: int = 1")
        b_idx = rendered.index("b: str = 'new'")
        c_idx = rendered.index("c: int = 3")
        assert a_idx < b_idx < c_idx

    def test_field_missing_visited_field_false(self):
        source = "class Inputs:\n    text: str = ''\n"
        new_stmt = cst.parse_statement("nonexistent: int = 0")
        transformer = ModifyFieldOnClass("Inputs", "nonexistent", new_stmt)
        modified = cst.parse_module(source).visit(transformer)
        assert transformer.visited_target
        assert not transformer.visited_field
        # Source unchanged
        assert "nonexistent" not in modified.code

    def test_target_class_missing_visited_target_false(self):
        source = "class Other:\n    text: str = ''\n"
        new_stmt = cst.parse_statement("text: str = 'new'")
        transformer = ModifyFieldOnClass("Inputs", "text", new_stmt)
        modified = cst.parse_module(source).visit(transformer)
        assert not transformer.visited_target
        assert not transformer.visited_field


# ---------------------------------------------------------------------------
# collect_class_field_names
# ---------------------------------------------------------------------------


class TestCollectClassFieldNames:
    def test_returns_ann_assign_names(self):
        source = (
            "class Inputs:\n"
            "    text: str = ''\n"
            "    count: int = 0\n"
            "    items: list[str] = []\n"
        )
        module = cst.parse_module(source)
        names = collect_class_field_names(module, "Inputs")
        assert names == {"text", "count", "items"}

    def test_skips_non_annotated_assignments(self):
        source = (
            "class Inputs:\n"
            "    text: str = ''\n"
            "    plain_assign = 42\n"  # not an AnnAssign
        )
        module = cst.parse_module(source)
        names = collect_class_field_names(module, "Inputs")
        assert names == {"text"}
        assert "plain_assign" not in names

    def test_class_missing_returns_empty(self):
        source = "class Other:\n    x: int = 0\n"
        module = cst.parse_module(source)
        names = collect_class_field_names(module, "Inputs")
        assert names == set()

    def test_empty_class_returns_empty(self):
        source = "class Inputs:\n    pass\n"
        module = cst.parse_module(source)
        names = collect_class_field_names(module, "Inputs")
        assert names == set()


# ---------------------------------------------------------------------------
# find_class
# ---------------------------------------------------------------------------


class TestFindClass:
    def test_finds_top_level_class(self):
        source = (
            "x = 1\n"
            "class Foo:\n"
            "    pass\n"
        )
        module = cst.parse_module(source)
        cls = find_class(module, "Foo")
        assert cls is not None
        assert cls.name.value == "Foo"

    def test_returns_none_when_missing(self):
        source = "class Foo:\n    pass\n"
        module = cst.parse_module(source)
        assert find_class(module, "Bar") is None

    def test_returns_first_when_multiple_top_level(self):
        # Edge case — duplicate class names. Returns the first.
        source = (
            "class Foo:\n    x: int = 1\n\n"
            "class Foo:\n    y: int = 2\n"
        )
        module = cst.parse_module(source)
        cls = find_class(module, "Foo")
        assert cls is not None
        # body has the first definition's field
        body = cls.body
        assert isinstance(body, cst.IndentedBlock)
