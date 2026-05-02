"""Tests for ``codegen.api.generate_prompt_variables``.

Validates the YAML→step-file upsert path:

- Existing step file's ``XPrompt`` class gets its body rewritten in
  place; surrounding code (Inputs / Instructions / Step class /
  comments / hand-written imports) survives unchanged.
- Step file with no ``XPrompt`` class yet gets one appended.
- Required imports (``Field`` / ``ClassVar`` / ``PromptVariables``)
  are added if missing, left alone if present.
- ``auto_generate`` keys go into ``auto_vars`` ClassVar; others
  become Pydantic fields.
- Empty / ``None`` ``variable_definitions`` -> ``pass`` body.
- Idempotency: a second call with identical inputs is a no-op.
- Path-guard: writes outside the configured root throw.
- Missing ``step_file`` raises (generate doesn't scaffold new steps).
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


def _import_step_file(path: Path, mod_name: str):
    """Import a step file under a synthetic module name.

    Each test gets a unique ``mod_name`` so the
    ``PromptVariables`` registry doesn't see duplicate registrations
    across tests.
    """
    spec = importlib.util.spec_from_file_location(mod_name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _step_stub(name: str = "x") -> str:
    """Minimal step file content — no XPrompt class yet."""
    return f"# stub step file for '{name}'\n"


def _make_step_file(tmp_path: Path, name: str = "x") -> Path:
    """Create ``tmp_path/steps/<name>.py`` with stub content; return path."""
    steps = tmp_path / "steps"
    steps.mkdir(exist_ok=True)
    sf = steps / f"{name}.py"
    sf.write_text(_step_stub(name), encoding="utf-8")
    return sf


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


class TestHappyPaths:
    def test_fields_only_generates_pydantic_fields(self, tmp_path):
        sf = _make_step_file(tmp_path, "summary")
        written = generate_prompt_variables(
            prompt_name="summary",
            variable_definitions={
                "text": {"type": "str", "description": "Input text"},
                "primary_topic": {
                    "type": "str", "description": "Primary topic",
                },
            },
            step_file=sf,
            root=tmp_path,
        )
        assert written is True

        source = sf.read_text()
        compile(source, str(sf), "exec")

        mod = _import_step_file(sf, "_test_gen_summary_fields")
        cls = mod.SummaryPrompt
        assert "text" in cls.model_fields
        assert "primary_topic" in cls.model_fields
        assert cls.model_fields["text"].description == "Input text"
        assert cls.model_fields["primary_topic"].description == "Primary topic"
        assert cls.auto_vars == {}

    def test_auto_generate_goes_into_auto_vars(self, tmp_path):
        sf = _make_step_file(tmp_path, "topic_extraction")
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
            step_file=sf,
            root=tmp_path,
        )

        mod = _import_step_file(sf, "_test_gen_topic_autovars")
        cls = mod.TopicExtractionPrompt
        assert "text" in cls.model_fields
        assert "sentiment_options" not in cls.model_fields
        assert cls.auto_vars == {
            "sentiment_options": "enum_names(Sentiment)",
        }

    def test_only_auto_vars_no_fields(self, tmp_path):
        sf = _make_step_file(tmp_path, "only_auto")
        generate_prompt_variables(
            prompt_name="only_auto",
            variable_definitions={
                "options": {
                    "type": "str",
                    "description": "All options",
                    "auto_generate": "enum_values(MyEnum)",
                },
            },
            step_file=sf,
            root=tmp_path,
        )

        mod = _import_step_file(sf, "_test_gen_only_auto")
        cls = mod.OnlyAutoPrompt
        assert cls.model_fields == {}
        assert cls.auto_vars == {"options": "enum_values(MyEnum)"}

    def test_no_variable_definitions_emits_pass_body(self, tmp_path):
        sf = _make_step_file(tmp_path, "bare")
        generate_prompt_variables(
            prompt_name="bare",
            variable_definitions=None,
            step_file=sf,
            root=tmp_path,
        )

        source = sf.read_text()
        assert "class BarePrompt(PromptVariables):" in source
        assert "pass" in source
        # No fields → no Field import added.
        assert "from pydantic import Field" not in source
        # No auto_vars → no ClassVar import added.
        assert "from typing import ClassVar" not in source

        mod = _import_step_file(sf, "_test_gen_bare")
        cls = mod.BarePrompt
        assert cls.model_fields == {}
        assert cls.auto_vars == {}

    def test_empty_dict_variable_definitions_emits_pass(self, tmp_path):
        sf = _make_step_file(tmp_path, "empty_dict")
        generate_prompt_variables(
            prompt_name="empty_dict",
            variable_definitions={},
            step_file=sf,
            root=tmp_path,
        )
        mod = _import_step_file(sf, "_test_gen_empty_dict")
        assert mod.EmptyDictPrompt.model_fields == {}
        assert mod.EmptyDictPrompt.auto_vars == {}

    def test_class_name_is_pascal_case_with_prompt_suffix(self, tmp_path):
        sf = _make_step_file(tmp_path, "multi_word_thing")
        generate_prompt_variables(
            prompt_name="multi_word_thing",
            variable_definitions={
                "x": {"type": "str", "description": "x"},
            },
            step_file=sf,
            root=tmp_path,
        )
        source = sf.read_text()
        assert "class MultiWordThingPrompt(PromptVariables):" in source

    def test_description_with_special_characters_round_trips(self, tmp_path):
        # Single quotes, double quotes, backslashes, unicode — every
        # special char must survive the repr-quoting round trip.
        gnarly = (
            "Has 'single' and \"double\" quotes, a \\ backslash, "
            "and unicode — emdash."
        )
        sf = _make_step_file(tmp_path, "gnarly")
        generate_prompt_variables(
            prompt_name="gnarly",
            variable_definitions={
                "text": {"type": "str", "description": gnarly},
            },
            step_file=sf,
            root=tmp_path,
        )
        mod = _import_step_file(sf, "_test_gen_gnarly")
        assert mod.GnarlyPrompt.model_fields["text"].description == gnarly


# ---------------------------------------------------------------------------
# Upsert behavior — surrounding content is preserved
# ---------------------------------------------------------------------------


class TestUpsertPreservesSurroundingContent:
    def test_existing_xprompt_class_replaced_in_place(self, tmp_path):
        sf = _make_step_file(tmp_path, "x")
        sf.write_text(
            "# leading comment\n"
            "from pydantic import Field\n"
            "from llm_pipeline.prompts import PromptVariables\n"
            "\n"
            "\n"
            "class XPrompt(PromptVariables):\n"
            "    \"\"\"stale\"\"\"\n"
            "    old_field: str = Field(description='gone')\n"
            "\n"
            "\n"
            "# trailing user content\n",
            encoding="utf-8",
        )

        generate_prompt_variables(
            prompt_name="x",
            variable_definitions={
                "text": {"type": "str", "description": "Input text"},
            },
            step_file=sf,
            root=tmp_path,
        )

        body = sf.read_text()
        assert "old_field" not in body
        assert "text: str = Field(description='Input text')" in body
        # Bracketing content survives.
        assert "# leading comment" in body
        assert "# trailing user content" in body

    def test_appends_class_when_missing_from_step_file(self, tmp_path):
        sf = _make_step_file(tmp_path, "fresh")
        sf.write_text(
            "from llm_pipeline.graph import LLMStepNode\n"
            "\n"
            "\n"
            "class FreshStep(LLMStepNode):\n"
            "    pass\n",
            encoding="utf-8",
        )

        generate_prompt_variables(
            prompt_name="fresh",
            variable_definitions={
                "text": {"type": "str", "description": "Input"},
            },
            step_file=sf,
            root=tmp_path,
        )

        body = sf.read_text()
        # Original step class preserved.
        assert "class FreshStep(LLMStepNode):" in body
        # FreshPrompt appended.
        assert "class FreshPrompt(PromptVariables):" in body
        # Required imports added.
        assert "from pydantic import Field" in body
        assert "from llm_pipeline.prompts import PromptVariables" in body

    def test_imports_not_duplicated_when_already_present(self, tmp_path):
        sf = _make_step_file(tmp_path, "imp")
        sf.write_text(
            "from pydantic import Field\n"
            "from llm_pipeline.prompts import PromptVariables\n"
            "\n"
            "# nothing else yet\n",
            encoding="utf-8",
        )

        generate_prompt_variables(
            prompt_name="imp",
            variable_definitions={
                "text": {"type": "str", "description": "Input"},
            },
            step_file=sf,
            root=tmp_path,
        )

        body = sf.read_text()
        # Each import appears exactly once.
        assert body.count("from pydantic import Field") == 1
        assert body.count("from llm_pipeline.prompts import PromptVariables") == 1


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_second_call_with_identical_inputs_returns_false(self, tmp_path):
        sf = _make_step_file(tmp_path, "idemp")
        defs = {"text": {"type": "str", "description": "Input"}}

        first = generate_prompt_variables(
            prompt_name="idemp",
            variable_definitions=defs,
            step_file=sf,
            root=tmp_path,
        )
        second = generate_prompt_variables(
            prompt_name="idemp",
            variable_definitions=defs,
            step_file=sf,
            root=tmp_path,
        )
        assert first is True
        assert second is False

    def test_changed_inputs_returns_true_and_rewrites(self, tmp_path):
        sf = _make_step_file(tmp_path, "change")
        generate_prompt_variables(
            prompt_name="change",
            variable_definitions={
                "text": {"type": "str", "description": "v1"},
            },
            step_file=sf,
            root=tmp_path,
        )
        rewritten = generate_prompt_variables(
            prompt_name="change",
            variable_definitions={
                "text": {"type": "str", "description": "v2"},
            },
            step_file=sf,
            root=tmp_path,
        )
        assert rewritten is True
        body = sf.read_text()
        assert "v2" in body
        assert "v1" not in body


# ---------------------------------------------------------------------------
# Path-guard / missing step file
# ---------------------------------------------------------------------------


class TestPathGuard:
    def test_write_outside_root_raises_codegen_error(self, tmp_path):
        root = tmp_path / "inside"
        root.mkdir()
        outside = tmp_path / "outside" / "x.py"
        outside.parent.mkdir()
        outside.write_text(_step_stub(), encoding="utf-8")

        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "text": {"type": "str", "description": "t"},
                },
                step_file=outside,
                root=root,
            )

    def test_write_under_root_is_allowed(self, tmp_path):
        sf = _make_step_file(tmp_path, "x")
        generate_prompt_variables(
            prompt_name="x",
            variable_definitions={
                "text": {"type": "str", "description": "t"},
            },
            step_file=sf,
            root=tmp_path,
        )
        assert "XPrompt(PromptVariables):" in sf.read_text()

    def test_missing_step_file_raises_codegen_error(self, tmp_path):
        # No step file created — generate doesn't scaffold new ones.
        steps = tmp_path / "steps"
        steps.mkdir()
        with pytest.raises(CodegenError, match="does not exist"):
            generate_prompt_variables(
                prompt_name="ghost",
                variable_definitions={
                    "text": {"type": "str", "description": "t"},
                },
                step_file=steps / "ghost.py",
                root=tmp_path,
            )


# ---------------------------------------------------------------------------
# Malformed inputs
# ---------------------------------------------------------------------------


class TestMalformedInputs:
    def test_empty_prompt_name_raises(self, tmp_path):
        sf = _make_step_file(tmp_path, "x")
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="",
                variable_definitions=None,
                step_file=sf,
                root=tmp_path,
            )

    def test_var_definition_missing_description_raises(self, tmp_path):
        sf = _make_step_file(tmp_path, "x")
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "text": {"type": "str"},  # no description
                },
                step_file=sf,
                root=tmp_path,
            )

    def test_var_definition_empty_description_raises(self, tmp_path):
        sf = _make_step_file(tmp_path, "x")
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "text": {"type": "str", "description": ""},
                },
                step_file=sf,
                root=tmp_path,
            )

    def test_var_definition_non_dict_raises(self, tmp_path):
        sf = _make_step_file(tmp_path, "x")
        with pytest.raises(CodegenError):
            generate_prompt_variables(
                prompt_name="x",
                variable_definitions={
                    "text": "just a string",  # malformed
                },
                step_file=sf,
                root=tmp_path,
            )

    def test_auto_generate_empty_string_raises(self, tmp_path):
        sf = _make_step_file(tmp_path, "x")
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
                step_file=sf,
                root=tmp_path,
            )


# ---------------------------------------------------------------------------
# Integration: generated class enforces PromptVariables contract
# ---------------------------------------------------------------------------


class TestPromptVariablesContractIntegration:
    """End-to-end: generated class flows through ``PromptVariables`` rules."""

    def test_generated_class_is_promptvariables_subclass(self, tmp_path):
        sf = _make_step_file(tmp_path, "contract")
        generate_prompt_variables(
            prompt_name="contract",
            variable_definitions={
                "text": {"type": "str", "description": "Input"},
            },
            step_file=sf,
            root=tmp_path,
        )
        mod = _import_step_file(sf, "_test_gen_contract")
        from llm_pipeline.prompts import PromptVariables

        assert issubclass(mod.ContractPrompt, PromptVariables)

    def test_generated_class_can_be_instantiated_with_field_values(
        self, tmp_path,
    ):
        sf = _make_step_file(tmp_path, "inst")
        generate_prompt_variables(
            prompt_name="inst",
            variable_definitions={
                "text": {"type": "str", "description": "Input"},
                "sentiment": {"type": "str", "description": "Sentiment"},
            },
            step_file=sf,
            root=tmp_path,
        )
        mod = _import_step_file(sf, "_test_gen_inst")
        instance = mod.InstPrompt(text="hello", sentiment="positive")
        assert instance.text == "hello"
        assert instance.sentiment == "positive"

    def test_auto_vars_keys_cannot_be_passed_as_constructor_args(
        self, tmp_path,
    ):
        sf = _make_step_file(tmp_path, "autovar_excl")
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
            step_file=sf,
            root=tmp_path,
        )
        mod = _import_step_file(sf, "_test_gen_autovar_excl")
        # 'options' should be a class-level attribute, not a model field.
        assert "options" not in mod.AutovarExclPrompt.model_fields
        # Can still construct with just the field.
        instance = mod.AutovarExclPrompt(text="hi")
        assert instance.text == "hi"
