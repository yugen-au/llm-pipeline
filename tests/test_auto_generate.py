"""Tests for auto_generate expression parsing, resolution, and factory building."""
import enum
import pytest

from llm_pipeline.prompts.variables import (
    _parse_auto_generate,
    _resolve_object,
    build_auto_generate_factory as _build_auto_generate_factory,
    register_auto_generate,
    set_auto_generate_base_path,
    clear_auto_generate_registry,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@pytest.fixture(autouse=True)
def _clean_registries():
    yield
    clear_auto_generate_registry()


# ---------------------------------------------------------------------------
# Expression parsing
# ---------------------------------------------------------------------------


class TestParseAutoGenerate:
    def test_enum_values(self):
        func, args = _parse_auto_generate("enum_values(Color)")
        assert func == "enum_values"
        assert args == ["Color"]

    def test_enum_names(self):
        func, args = _parse_auto_generate("enum_names(Color)")
        assert func == "enum_names"
        assert args == ["Color"]

    def test_enum_value(self):
        func, args = _parse_auto_generate("enum_value(Color, RED)")
        assert func == "enum_value"
        assert args == ["Color", "RED"]

    def test_constant(self):
        func, args = _parse_auto_generate("constant(hello world)")
        assert func == "constant"
        assert args == ["hello world"]

    def test_whitespace_stripped(self):
        func, args = _parse_auto_generate("  enum_values( Color )  ")
        assert func == "enum_values"
        assert args == ["Color"]

    def test_invalid_expression(self):
        with pytest.raises(ValueError, match="Unrecognized"):
            _parse_auto_generate("unknown_func(X)")

    def test_empty_expression(self):
        with pytest.raises(ValueError, match="Unrecognized"):
            _parse_auto_generate("")

    def test_no_parens(self):
        with pytest.raises(ValueError, match="Unrecognized"):
            _parse_auto_generate("enum_values")


# ---------------------------------------------------------------------------
# Object resolution
# ---------------------------------------------------------------------------


class TestResolveObject:
    def test_registry_lookup(self):
        register_auto_generate("Color", Color)
        obj = _resolve_object("Color", None, "enum_values")
        assert obj is Color

    def test_import_path(self):
        obj = _resolve_object(
            "Color",
            "tests.test_auto_generate.Color",
            "enum_values",
        )
        assert obj is Color

    def test_convention_resolution(self):
        # Use this test module as a fake "enums" submodule
        set_auto_generate_base_path("tests.test_auto_generate_enums")
        # This will fail because that module doesn't exist, testing fallthrough
        with pytest.raises(ValueError, match="Cannot resolve"):
            _resolve_object("Color", None, "enum_values")

    def test_not_found_raises(self):
        with pytest.raises(ValueError, match="Cannot resolve 'Nonexistent'"):
            _resolve_object("Nonexistent", None, "enum_values")

    def test_registry_takes_precedence(self):
        """Registry wins even when import_path is provided."""
        sentinel = object()
        register_auto_generate("Color", sentinel)
        obj = _resolve_object(
            "Color",
            "tests.test_auto_generate.Color",
            "enum_values",
        )
        assert obj is sentinel


# ---------------------------------------------------------------------------
# Factory building + execution
# ---------------------------------------------------------------------------


class TestBuildAutoGenerateFactory:
    def setup_method(self):
        register_auto_generate("Color", Color)

    def test_enum_values(self):
        factory = _build_auto_generate_factory("enum_values(Color)")
        assert factory() == "red, green, blue"

    def test_enum_names(self):
        factory = _build_auto_generate_factory("enum_names(Color)")
        assert factory() == "RED, GREEN, BLUE"

    def test_enum_value(self):
        factory = _build_auto_generate_factory("enum_value(Color, RED)")
        assert factory() == "red"

    def test_enum_value_wrong_arg_count(self):
        with pytest.raises(ValueError, match="enum_value requires 2 args"):
            _build_auto_generate_factory("enum_value(Color)")

    def test_constant(self):
        factory = _build_auto_generate_factory("constant(hello)")
        assert factory() == "hello"

    def test_lazy_resolution(self):
        """Factory resolves at call time, not at build time."""
        factory = _build_auto_generate_factory("enum_values(LateEnum)")
        # Not registered yet -- building succeeds
        # But calling fails
        with pytest.raises(ValueError, match="Cannot resolve"):
            factory()
        # Now register
        register_auto_generate("LateEnum", Color)
        assert factory() == "red, green, blue"

    def test_import_path_override(self):
        clear_auto_generate_registry()
        factory = _build_auto_generate_factory(
            "enum_values(Color)",
            import_path="tests.test_auto_generate.Color",
        )
        assert factory() == "red, green, blue"


# Phase E: ``rebuild_from_db`` was the bridge between DB-stored
# variable_definitions and runtime PromptVariables classes; both went
# away with the local Prompt table. The auto_generate factory builder
# is exercised directly by ``TestBuildAutoGenerateFactory`` above.
