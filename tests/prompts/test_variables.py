"""Tests for PromptVariables base class + registry + auto-discovery."""
from __future__ import annotations

import sys
from types import ModuleType

import pytest
from pydantic import BaseModel, Field

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
    def test_valid_subclass_with_both_nested_classes(self):
        class WidgetDetectionPrompt(PromptVariables):
            class system(BaseModel):
                tone: str = Field(description="Voice tone")

            class user(BaseModel):
                text: str = Field(description="Text to inspect")

        assert issubclass(WidgetDetectionPrompt.system, BaseModel)
        assert issubclass(WidgetDetectionPrompt.user, BaseModel)
        assert "tone" in WidgetDetectionPrompt.system.model_fields
        assert "text" in WidgetDetectionPrompt.user.model_fields

    def test_empty_nested_classes_allowed(self):
        class NoVarsPrompt(PromptVariables):
            class system(BaseModel):
                pass

            class user(BaseModel):
                pass

        assert NoVarsPrompt.system.model_fields == {}
        assert NoVarsPrompt.user.model_fields == {}

    def test_missing_system_raises(self):
        with pytest.raises(TypeError, match="must be a Pydantic BaseModel subclass"):

            class MissingSystemPrompt(PromptVariables):
                class user(BaseModel):
                    text: str = Field(description="Text")

    def test_missing_user_raises(self):
        with pytest.raises(TypeError, match="must be a Pydantic BaseModel subclass"):

            class MissingUserPrompt(PromptVariables):
                class system(BaseModel):
                    pass

    def test_system_not_a_basemodel_raises(self):
        with pytest.raises(TypeError, match="must be a Pydantic BaseModel subclass"):

            class BadSystemPrompt(PromptVariables):
                class system:  # bare class — not a BaseModel
                    pass

                class user(BaseModel):
                    pass

    def test_field_without_description_raises(self):
        with pytest.raises(ValueError, match="must use Field"):

            class NoDescPrompt(PromptVariables):
                class system(BaseModel):
                    pass

                class user(BaseModel):
                    text: str = Field()  # no description

    def test_plain_default_without_field_raises(self):
        # text: str = "hi" — no Field() at all, no description
        with pytest.raises(ValueError, match="must use Field"):

            class PlainDefaultPrompt(PromptVariables):
                class system(BaseModel):
                    pass

                class user(BaseModel):
                    text: str = "default"  # type: ignore[assignment]

    def test_instance_validates_like_normal_pydantic(self):
        class ValidPrompt(PromptVariables):
            class system(BaseModel):
                pass

            class user(BaseModel):
                text: str = Field(description="Text")

        instance = ValidPrompt(
            system=ValidPrompt.system(),
            user=ValidPrompt.user(text="hi"),
        )
        assert instance.user.text == "hi"


class TestRegistry:
    def test_register_and_lookup(self):
        class FooPrompt(PromptVariables):
            class system(BaseModel):
                pass

            class user(BaseModel):
                pass

        register_prompt_variables("foo", FooPrompt)
        assert get_prompt_variables("foo") is FooPrompt

    def test_lookup_missing_returns_none(self):
        assert get_prompt_variables("nope") is None

    def test_register_duplicate_same_class_is_noop(self):
        class FooPrompt(PromptVariables):
            class system(BaseModel):
                pass

            class user(BaseModel):
                pass

        register_prompt_variables("foo", FooPrompt)
        register_prompt_variables("foo", FooPrompt)  # second call should not raise
        assert get_prompt_variables("foo") is FooPrompt

    def test_register_duplicate_different_class_raises(self):
        class FooPrompt(PromptVariables):
            class system(BaseModel):
                pass

            class user(BaseModel):
                pass

        class BarPrompt(PromptVariables):
            class system(BaseModel):
                pass

            class user(BaseModel):
                pass

        register_prompt_variables("foo", FooPrompt)
        with pytest.raises(ValueError, match="Duplicate PromptVariables"):
            register_prompt_variables("foo", BarPrompt)

    def test_get_all_returns_copy(self):
        class FooPrompt(PromptVariables):
            class system(BaseModel):
                pass

            class user(BaseModel):
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
            "from pydantic import BaseModel, Field\n"
            "from llm_pipeline.prompts.variables import PromptVariables\n"
            "class SentimentAnalysisPrompt(PromptVariables):\n"
            "    class system(BaseModel):\n"
            "        pass\n"
            "    class user(BaseModel):\n"
            "        text: str = Field(description='Text')\n",
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
            "from pydantic import BaseModel, Field\n"
            "from llm_pipeline.prompts.variables import PromptVariables\n"
            "class FooPrompt(PromptVariables):\n"
            "    class system(BaseModel):\n"
            "        pass\n"
            "    class user(BaseModel):\n"
            "        pass\n",
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
            "from pydantic import BaseModel, Field\n"
            "from llm_pipeline.prompts.variables import PromptVariables\n"
            "class WidgetPrompt(PromptVariables):\n"
            "    class system(BaseModel):\n"
            "        pass\n"
            "    class user(BaseModel):\n"
            "        pass\n",
            mod.__dict__,
        )

        discover_prompt_variables([mod])
        discover_prompt_variables([mod])  # second pass should not raise
        assert get_prompt_variables("widget") is mod.__dict__["WidgetPrompt"]
