"""Tests for ``llm_pipeline.codegen.builders``."""
from __future__ import annotations

import libcst as cst

from llm_pipeline.codegen.builders import (
    FieldSpec,
    class_var_dict_assignment,
    import_from,
    pydantic_class,
    pydantic_field_assignment,
)


# ---------------------------------------------------------------------------
# import_from
# ---------------------------------------------------------------------------


class TestImportFrom:
    def test_single_name(self):
        stmt = import_from("typing", ["ClassVar"])
        rendered = cst.Module(body=[stmt]).code
        assert "from typing import ClassVar" in rendered

    def test_multiple_names(self):
        stmt = import_from("pydantic", ["BaseModel", "Field"])
        rendered = cst.Module(body=[stmt]).code
        assert "from pydantic import BaseModel, Field" in rendered

    def test_returns_simple_statement_line(self):
        stmt = import_from("os", ["path"])
        assert isinstance(stmt, cst.SimpleStatementLine)


# ---------------------------------------------------------------------------
# pydantic_field_assignment
# ---------------------------------------------------------------------------


class TestPydanticFieldAssignment:
    def test_simple_str_field(self):
        spec = FieldSpec(name="text", annotation="str", description="Input text")
        stmt = pydantic_field_assignment(spec)
        rendered = cst.Module(body=[stmt]).code
        assert "text: str = Field(description='Input text')" in rendered

    def test_complex_annotation(self):
        spec = FieldSpec(
            name="items", annotation="list[dict[str, int]]", description="A list",
        )
        stmt = pydantic_field_assignment(spec)
        rendered = cst.Module(body=[stmt]).code
        assert "items: list[dict[str, int]]" in rendered

    def test_description_with_quotes_escaped(self):
        spec = FieldSpec(
            name="x", annotation="str",
            description="It's \"important\" stuff",
        )
        stmt = pydantic_field_assignment(spec)
        rendered = cst.Module(body=[stmt]).code
        # The repr-quoted form survives round-trip
        assert cst.parse_module(rendered).code == rendered

    def test_description_with_newlines_escaped(self):
        spec = FieldSpec(
            name="x", annotation="str", description="line1\nline2",
        )
        stmt = pydantic_field_assignment(spec)
        rendered = cst.Module(body=[stmt]).code
        assert cst.parse_module(rendered).code == rendered


# ---------------------------------------------------------------------------
# pydantic_class
# ---------------------------------------------------------------------------


class TestPydanticClass:
    def test_empty_class_emits_pass(self):
        cls = pydantic_class("Empty", fields=[])
        rendered = cst.Module(body=[cls]).code
        assert "class Empty(BaseModel):" in rendered
        assert "pass" in rendered

    def test_class_with_fields(self):
        cls = pydantic_class(
            "Inputs",
            fields=[
                FieldSpec("text", "str", "Input text"),
                FieldSpec("count", "int", "How many"),
            ],
        )
        rendered = cst.Module(body=[cls]).code
        assert "class Inputs(BaseModel):" in rendered
        assert "text: str = Field(description='Input text')" in rendered
        assert "count: int = Field(description='How many')" in rendered

    def test_custom_base(self):
        cls = pydantic_class("Foo", fields=[], base="PromptVariables")
        rendered = cst.Module(body=[cls]).code
        assert "class Foo(PromptVariables):" in rendered

    def test_compiles_as_valid_python(self):
        cls = pydantic_class(
            "Inputs",
            fields=[FieldSpec("text", "str", "Input text")],
        )
        # Wrap in a module with the right imports + run compile() —
        # if any embedded literal is malformed the compile fails.
        module = cst.Module(body=[
            import_from("pydantic", ["BaseModel", "Field"]),
            cls,
        ])
        compile(module.code, "<test>", "exec")


# ---------------------------------------------------------------------------
# class_var_dict_assignment
# ---------------------------------------------------------------------------


class TestClassVarDictAssignment:
    def test_empty_dict(self):
        stmt = class_var_dict_assignment("auto_vars", {})
        rendered = cst.Module(body=[stmt]).code
        assert "auto_vars: ClassVar[dict[str, str]] = {}" in rendered

    def test_with_items(self):
        stmt = class_var_dict_assignment(
            "auto_vars",
            {"sentiment_options": "enum_names(Sentiment)"},
        )
        rendered = cst.Module(body=[stmt]).code
        assert "auto_vars: ClassVar[dict[str, str]]" in rendered
        assert "'sentiment_options'" in rendered
        assert "'enum_names(Sentiment)'" in rendered

    def test_custom_value_type(self):
        stmt = class_var_dict_assignment("counts", {"a": "1"}, value_type="int")
        rendered = cst.Module(body=[stmt]).code
        assert "ClassVar[dict[str, int]]" in rendered

    def test_special_chars_in_keys_and_values_escaped(self):
        stmt = class_var_dict_assignment(
            "weird",
            {"key with 'quotes'": 'value with "quotes"'},
        )
        rendered = cst.Module(body=[stmt]).code
        # Round-trip works = escaping survived
        assert cst.parse_module(rendered).code == rendered

    def test_compiles_as_valid_python(self):
        stmt = class_var_dict_assignment(
            "auto_vars",
            {"sentiment_options": "enum_names(Sentiment)"},
        )
        module = cst.Module(body=[
            import_from("typing", ["ClassVar"]),
            stmt,
        ])
        compile(module.code, "<test>", "exec")
