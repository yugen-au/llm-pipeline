"""Tests for ``codegen.api.generate_prompt_variables``.

Validates the YAML→Python generation path:

- Output is valid Python (compiles).
- Output is importable + the generated class registers via
  ``PromptVariables.__pydantic_init_subclass__`` (full integration).
- ``auto_generate`` keys go into ``auto_vars`` ClassVar; others
  become Pydantic fields.
- Empty / ``None`` ``variable_definitions`` -> ``pass`` body.
- Idempotency: a second call with identical inputs is a no-op.
- Path-guard: writes outside the configured root throw.
- Malformed inputs raise :class:`CodegenError`.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from llm_pipeline.codegen import (
    CodegenError,
    generate_prompt_variables,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _import_generated(path: Path, mod_name: str):
    """Import the generated file under a synthetic module name.

    Each test gets a unique ``mod_name`` so the
    ``PromptVariables`` registry doesn't see duplicate registrations
    across tests. We don't go through ``register_prompt_variables``
    here — we just want the class object to verify shape.
    """
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestHappyPaths:
    def test_fields_only_generates_pydantic_fields(self, tmp_path):
        out = tmp_path / "_summary.py"
        written = generate_prompt_variables(
            prompt_name="summary",
            variable_definitions={
                "text": {"type": "str", "description": "Input text"},
                "primary_topic": {
                    "type": "str", "description": "Primary topic",
                },
            },
            output_path=out,
            root=tmp_path,
        )
        assert written is True
        assert out.exists()

        source = out.read_text()
        compile(source, str(out), "exec")

        mod = _import_generated(out, "_test_gen_summary_fields")
        cls = mod.SummaryPrompt
        assert "text" in cls.model_fields
        assert "primary_topic" in cls.model_fields
        assert cls.model_fields["text"].description == "Input text"
        assert cls.model_fields["primary_topic"].description == "Primary topic"
        assert cls.auto_vars == {}

    def test_auto_generate_goes_into_auto_vars(self, tmp_path):
        out = tmp_path / "_topic_extraction.py"
        generate_prompt_variables(
            prompt_name="topic_extraction",
            variable_definitions={
                "text": {"type": "str", "description": "Input text"},
                "sentiment_options": {
                    "type": "str",
                    "description": "Allowed sentiments",
                    "auto_generate": "enum_names(Sentiment)",
                },
            },
            output_path=out,
            root=tmp_path,
        )

        mod = _import_generated(out, "_test_gen_topic_autovars")
        cls = mod.TopicExtractionPrompt
        # Field side
        assert "text" in cls.model_fields
        # auto_vars side — sentiment_options must NOT be a field
        assert "sentiment_options" not in cls.model_fields
        assert cls.auto_vars == {
            "sentiment_options": "enum_names(Sentiment)",
        }

    def test_only_auto_vars_no_fields(self, tmp_path):
        out = tmp_path / "_only_auto.py"
        generate_prompt_variables(
            prompt_name="only_auto",
            variable_definitions={
                "options": {
                    "type": "str",
                    "description": "All options",
                    "auto_generate": "enum_values(MyEnum)",
                },
            },
            output_path=out,
            root=tmp_path,
        )

        mod = _import_generated(out, "_test_gen_only_auto")
        cls = mod.OnlyAutoPrompt
        assert cls.model_fields == {}
        assert cls.auto_vars == {"options": "enum_values(MyEnum)"}

    def test_no_variable_definitions_emits_pass_body(self, tmp_path):
        out = tmp_path / "_bare.py"
        generate_prompt_variables(
            prompt_name="bare",
            variable_definitions=None,
            output_path=out,
            root=tmp_path,
        )

        source = out.read_text()
        # Sanity: contains class + pass body, no Field/ClassVar imports.
        assert "class BarePrompt(PromptVariables):" in source
        assert "pass" in source
        assert "from pydantic import Field" not in source
        assert "from typing import ClassVar" not in source

        mod = _import_generated(out, "_test_gen_bare")
        cls = mod.BarePrompt
        assert cls.model_fields == {}
        assert cls.auto_vars == {}

    def test_empty_dict_variable_definitions_emits_pass(self, tmp_path):
        out = tmp_path / "_empty_dict.py"
        generate_prompt_variables(
            prompt_name="empty_dict",
            variable_definitions={},
            output_path=out,
            root=tmp_path,
        )
        mod = _import_generated(out, "_test_gen_empty_dict")
        assert mod.EmptyDictPrompt.model_fields == {}
        assert mod.EmptyDictPrompt.auto_vars == {}

    def test_class_name_is_pascal_case_with_prompt_suffix(self, tmp_path):
        out = tmp_path / "_x.py"
        generate_prompt_variables(
            prompt_name="multi_word_thing",
            variable_definitions={
                "x": {"type": "str", "description": "x"},
            },
            output_path=out,
            root=tmp_path,
        )
        source = out.read_text()
        assert "class MultiWordThingPrompt(PromptVariables):" in source

    def test_description_with_special_characters_round_trips(self, tmp_path):
        # Single quotes, double quotes, backslashes, unicode — every
        # special char must survive the repr-quoting round trip.
        gnarly = (
            "Has 'single' and \"double\" quotes, a \\ backslash, "
            "and unicode — emdash."
        )
        out = tmp_path / "_gnarly.py"
        generate_prompt_variables(
            prompt_name="gnarly",
            variable_definitions={
                "text": {"type": "str", "description": gnarly},
            },
            output_path=out,
            root=tmp_path,
        )
        mod = _import_generated(out, "_test_gen_gnarly")
        assert mod.GnarlyPrompt.model_fields["text"].description == gnarly


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_call_with_identical_inputs_returns_false(self, tmp_path):
        out = tmp_path / "_idemp.py"
        defs = {"text": {"type": "str", "description": "Input"}}

        first = generate_prompt_variables(
            prompt_name="idemp",
            variable_definitions=defs,
            output_path=out,
            root=tmp_path,
        )
        second = generate_prompt_variables(
            prompt_name="idemp",
            variable_definitions=defs,
            output_path=out,
            root=tmp_path,
        )
        assert first is True
        assert second is False

    def test_changed_inputs_returns_true_and_rewrites(self, tmp_path):
        out = tmp_path / "_change.py"
        generate_prompt_variables(
            prompt_name="change",
            variable_definitions={
                "text": {"type": "str", "description": "v1"},
            },
            output_path=out,
            root=tmp_path,
        )
        rewritten = generate_prompt_variables(
            prompt_name="change",
            variable_definitions={
                "text": {"type": "str", "description": "v2"},
            },
            output_path=out,
            root=tmp_path,
        )
        assert rewritten is True
        assert "v2" in out.read_text()
        assert "v1" not in out.read_text()


# ---------------------------------------------------------------------------
# Path-guard
# ---------------------------------------------------------------------------


class TestPathGuard:
    def test_write_outside_root_raises_codegen_error(self, tmp_path):
        root = tmp_path / "inside"
        root.mkdir()
        outside = tmp_path / "outside" / "_x.py"
        outside.parent.mkdir()

        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "text": {"type": "str", "description": "t"},
                },
                output_path=outside,
                root=root,
            )

    def test_write_under_root_is_allowed(self, tmp_path):
        out = tmp_path / "subdir" / "_x.py"
        # Note: path doesn't exist yet — function creates parents.
        generate_prompt_variables(
            prompt_name="x",
            variable_definitions={
                "text": {"type": "str", "description": "t"},
            },
            output_path=out,
            root=tmp_path,
        )
        assert out.exists()


# ---------------------------------------------------------------------------
# Malformed inputs
# ---------------------------------------------------------------------------


class TestMalformedInputs:
    def test_empty_prompt_name_raises(self, tmp_path):
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="",
                variable_definitions=None,
                output_path=tmp_path / "_x.py",
                root=tmp_path,
            )

    def test_var_definition_missing_description_raises(self, tmp_path):
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "text": {"type": "str"},  # no description
                },
                output_path=tmp_path / "_x.py",
                root=tmp_path,
            )

    def test_var_definition_empty_description_raises(self, tmp_path):
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "text": {"type": "str", "description": ""},
                },
                output_path=tmp_path / "_x.py",
                root=tmp_path,
            )

    def test_var_definition_non_dict_raises(self, tmp_path):
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "text": "just a string",  # malformed
                },
                output_path=tmp_path / "_x.py",
                root=tmp_path,
            )

    def test_auto_generate_empty_string_raises(self, tmp_path):
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "opts": {
                        "type": "str",
                        "description": "Options",
                        "auto_generate": "",
                    },
                },
                output_path=tmp_path / "_x.py",
                root=tmp_path,
            )


# ---------------------------------------------------------------------------
# Integration: generated class enforces PromptVariables contract
# ---------------------------------------------------------------------------


class TestPromptVariablesContractIntegration:
    """End-to-end: generated class flows through ``PromptVariables`` rules."""

    def test_generated_class_is_promptvariables_subclass(self, tmp_path):
        out = tmp_path / "_contract.py"
        generate_prompt_variables(
            prompt_name="contract",
            variable_definitions={
                "text": {"type": "str", "description": "Input"},
            },
            output_path=out,
            root=tmp_path,
        )
        mod = _import_generated(out, "_test_gen_contract")
        from llm_pipeline.prompts import PromptVariables

        assert issubclass(mod.ContractPrompt, PromptVariables)

    def test_generated_class_can_be_instantiated_with_field_values(
        self, tmp_path,
    ):
        out = tmp_path / "_inst.py"
        generate_prompt_variables(
            prompt_name="inst",
            variable_definitions={
                "text": {"type": "str", "description": "Input"},
                "sentiment": {"type": "str", "description": "Sentiment"},
            },
            output_path=out,
            root=tmp_path,
        )
        mod = _import_generated(out, "_test_gen_inst")
        instance = mod.InstPrompt(text="hello", sentiment="positive")
        assert instance.text == "hello"
        assert instance.sentiment == "positive"

    def test_auto_vars_keys_cannot_be_passed_as_constructor_args(
        self, tmp_path,
    ):
        out = tmp_path / "_autovar_excl.py"
        generate_prompt_variables(
            prompt_name="autovar_excl",
            variable_definitions={
                "text": {"type": "str", "description": "Input"},
                "options": {
                    "type": "str",
                    "description": "Options",
                    "auto_generate": "enum_values(X)",
                },
            },
            output_path=out,
            root=tmp_path,
        )
        mod = _import_generated(out, "_test_gen_autovar_excl")
        # 'options' should be a class-level attribute, not a model field.
        assert "options" not in mod.AutovarExclPrompt.model_fields
        # Can still construct with just the field.
        instance = mod.AutovarExclPrompt(text="hi")
        assert instance.text == "hi"
