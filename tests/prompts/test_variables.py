"""Tests for PromptVariables base class + registry + auto-discovery."""
from __future__ import annotations

import sys
from types import ModuleType
from typing import ClassVar

import pytest
from pydantic import Field

from llm_pipeline.prompts.discovery import discover_prompt_variables
from llm_pipeline.prompts.variables import (
    PromptVariables,
    clear_prompt_variables_registry,
    get_all_prompt_variables,
    get_prompt_variables,
    register_prompt_variables,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_prompt_variables_registry()
    yield
    clear_prompt_variables_registry()


class TestPromptVariablesBase:
    def test_valid_subclass_with_fields(self):
        class WidgetDetectionPrompt(PromptVariables):
            tone: str = Field(description="Voice tone")
            text: str = Field(description="Text to inspect")

        assert "tone" in WidgetDetectionPrompt.model_fields
        assert "text" in WidgetDetectionPrompt.model_fields

    def test_empty_class_allowed(self):
        class NoVarsPrompt(PromptVariables):
            pass

        assert NoVarsPrompt.model_fields == {}
        # Empty subclass instantiates with no args
        NoVarsPrompt()

    def test_field_without_description_raises(self):
        with pytest.raises(ValueError, match="must use Field"):

            class NoDescPrompt(PromptVariables):
                text: str = Field()  # no description

    def test_plain_default_without_field_raises(self):
        # text: str = "hi" — no Field(), no description
        with pytest.raises(ValueError, match="must use Field"):

            class PlainDefaultPrompt(PromptVariables):
                text: str = "default"  # type: ignore[assignment]

    def test_instance_validates_like_normal_pydantic(self):
        class ValidPrompt(PromptVariables):
            text: str = Field(description="Text")

        instance = ValidPrompt(text="hi")
        assert instance.text == "hi"

    def test_model_dump_yields_flat_dict(self):
        class FlatPrompt(PromptVariables):
            text: str = Field(description="Text")
            count: int = Field(description="Count", default=0)

        instance = FlatPrompt(text="hi", count=3)
        assert instance.model_dump() == {"text": "hi", "count": 3}


class TestAutoVars:
    def test_default_is_empty_dict(self):
        class NoAutoPrompt(PromptVariables):
            text: str = Field(description="Text")

        # Inherits the empty default from the base class
        assert NoAutoPrompt.auto_vars == {}

    def test_auto_vars_classvar(self):
        class AutoPrompt(PromptVariables):
            text: str = Field(description="Text")
            auto_vars: ClassVar[dict[str, str]] = {
                "labels": "enum_names(Label)",
            }

        assert AutoPrompt.auto_vars == {"labels": "enum_names(Label)"}
        # auto_vars is NOT a Pydantic field — model_fields excludes it
        assert "auto_vars" not in AutoPrompt.model_fields

    def test_auto_vars_not_a_constructor_arg(self):
        # Structural override-prevention: passing auto_vars at
        # construction time is rejected by Pydantic (extra='forbid' by
        # default, but ClassVar isn't a field anyway).
        class AutoPrompt(PromptVariables):
            text: str = Field(description="Text")
            auto_vars: ClassVar[dict[str, str]] = {"x": "constant(y)"}

        # Pydantic ignores ClassVar in __init__
        instance = AutoPrompt(text="hi")
        # The class-level dict is still intact; the LLM-author can't
        # have changed it via construction.
        assert AutoPrompt.auto_vars == {"x": "constant(y)"}
        assert instance.text == "hi"

    def test_auto_vars_overlap_with_field_raises(self):
        with pytest.raises(ValueError, match="appear in BOTH"):

            class OverlapPrompt(PromptVariables):
                sentiment: str = Field(description="The sentiment")
                auto_vars: ClassVar[dict[str, str]] = {
                    "sentiment": "enum_names(Sentiment)",  # collides with field
                }

    def test_auto_vars_non_dict_raises(self):
        with pytest.raises(TypeError, match="must be a dict"):

            class BadAutoPrompt(PromptVariables):
                text: str = Field(description="Text")
                auto_vars: ClassVar = ["enum_names(Sentiment)"]  # type: ignore[assignment]

    def test_auto_vars_empty_value_raises(self):
        with pytest.raises(TypeError, match="non-empty auto_generate"):

            class EmptyValuePrompt(PromptVariables):
                text: str = Field(description="Text")
                auto_vars: ClassVar[dict[str, str]] = {"labels": ""}

    def test_auto_vars_empty_key_raises(self):
        with pytest.raises(TypeError, match="non-empty strings"):

            class EmptyKeyPrompt(PromptVariables):
                text: str = Field(description="Text")
                auto_vars: ClassVar[dict[str, str]] = {"": "constant(x)"}


class TestRegistry:
    def test_register_and_lookup(self):
        class FooPrompt(PromptVariables):
            pass

        register_prompt_variables("foo", FooPrompt)
        assert get_prompt_variables("foo") is FooPrompt

    def test_lookup_missing_returns_none(self):
        assert get_prompt_variables("nope") is None

    def test_register_duplicate_same_class_is_noop(self):
        class FooPrompt(PromptVariables):
            pass

        register_prompt_variables("foo", FooPrompt)
        register_prompt_variables("foo", FooPrompt)  # second call should not raise
        assert get_prompt_variables("foo") is FooPrompt

    def test_register_duplicate_different_class_raises(self):
        class FooPrompt(PromptVariables):
            pass

        class BarPrompt(PromptVariables):
            pass

        register_prompt_variables("foo", FooPrompt)
        with pytest.raises(ValueError, match="Duplicate PromptVariables"):
            register_prompt_variables("foo", BarPrompt)

    def test_get_all_returns_copy(self):
        class FooPrompt(PromptVariables):
            pass

        register_prompt_variables("foo", FooPrompt)
        snapshot = get_all_prompt_variables()
        snapshot["other"] = FooPrompt  # mutate the copy
        assert "other" not in get_all_prompt_variables()


class TestDiscovery:
    def _make_module(self, name: str) -> ModuleType:
        mod = ModuleType(name)
        sys.modules[name] = mod
        return mod

    def test_discovers_subclass_in_module(self):
        mod = self._make_module("test_pv_discovery_a")
        # Define inside the module so cls.__module__ matches
        exec(
            "from pydantic import Field\n"
            "from llm_pipeline.prompts.variables import PromptVariables\n"
            "class SentimentAnalysisPrompt(PromptVariables):\n"
            "    text: str = Field(description='Text')\n",
            mod.__dict__,
        )

        discover_prompt_variables([mod])
        assert get_prompt_variables("sentiment_analysis") is mod.__dict__[
            "SentimentAnalysisPrompt"
        ]

    def test_skips_classes_imported_from_other_modules(self):
        # Define class in module A
        mod_a = self._make_module("test_pv_discovery_b_origin")
        exec(
            "from llm_pipeline.prompts.variables import PromptVariables\n"
            "class FooPrompt(PromptVariables):\n"
            "    pass\n",
            mod_a.__dict__,
        )
        # Module B re-exports it but didn't define it
        mod_b = self._make_module("test_pv_discovery_b_consumer")
        mod_b.__dict__["FooPrompt"] = mod_a.__dict__["FooPrompt"]

        # Discovery walks B; should NOT register because cls.__module__ != mod_b.__name__
        discover_prompt_variables([mod_b])
        assert get_prompt_variables("foo") is None

    def test_idempotent_double_discovery(self):
        mod = self._make_module("test_pv_discovery_c")
        exec(
            "from llm_pipeline.prompts.variables import PromptVariables\n"
            "class WidgetPrompt(PromptVariables):\n"
            "    pass\n",
            mod.__dict__,
        )

        discover_prompt_variables([mod])
        discover_prompt_variables([mod])  # second pass should not raise
        assert get_prompt_variables("widget") is mod.__dict__["WidgetPrompt"]
