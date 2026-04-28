"""Tests for the ``inputs=`` kwarg on @step_definition.

Phase 2: breaking change.

- ``inputs=`` is a new optional kwarg declaring a ``StepInputs`` subclass
  as the step's typed input contract. Naming (``{StepName}Inputs``) and
  type (StepInputs subclass) validated at decoration time; stored on
  ``step_class.INPUTS``.
- ``context=`` kwarg is removed. @step_definition no longer accepts it
  and raises ``TypeError`` if passed.
"""
from typing import List

import pytest
from pydantic import BaseModel

from llm_pipeline.inputs import StepInputs
from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition
from llm_pipeline.types import StepCallParams


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


class FooInstructions(LLMResultMixin):
    label: str


class FooInputs(StepInputs):
    x: str


class BarInstructions(LLMResultMixin):
    val: int


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestInputsKwargAccepted:
    def test_inputs_stored_on_class(self):
        @step_definition(instructions=FooInstructions, inputs=FooInputs)
        class FooStep(LLMStep):
            def prepare_calls(self) -> List[StepCallParams]:
                return []

        assert FooStep.INPUTS is FooInputs

    def test_inputs_not_provided_is_none(self):
        @step_definition(instructions=FooInstructions)
        class FooStep(LLMStep):
            def prepare_calls(self) -> List[StepCallParams]:
                return []

        assert FooStep.INPUTS is None


# ---------------------------------------------------------------------------
# Validation failures
# ---------------------------------------------------------------------------


class TestInputsValidation:
    def test_misnamed_inputs_class_rejected(self):
        class FooInputsWrongName(StepInputs):
            x: str

        with pytest.raises(ValueError, match="FooInputs"):
            @step_definition(
                instructions=FooInstructions, inputs=FooInputsWrongName
            )
            class FooStep(LLMStep):
                def prepare_calls(self) -> List[StepCallParams]:
                    return []

    def test_non_stepinputs_subclass_rejected(self):
        class FooInputs_NotStepInputs(BaseModel):  # BaseModel, not StepInputs
            x: str

        # Rename to match expected naming so only the type check fails.
        FooInputs_NotStepInputs.__name__ = "FooInputs"

        with pytest.raises(TypeError, match="StepInputs"):
            @step_definition(
                instructions=FooInstructions, inputs=FooInputs_NotStepInputs
            )
            class FooStep(LLMStep):
                def prepare_calls(self) -> List[StepCallParams]:
                    return []

    def test_non_class_rejected(self):
        not_a_class = object()  # not a type at all

        with pytest.raises(TypeError, match="StepInputs"):
            @step_definition(instructions=FooInstructions, inputs=not_a_class)  # type: ignore[arg-type]
            class FooStep(LLMStep):
                def prepare_calls(self) -> List[StepCallParams]:
                    return []


# ---------------------------------------------------------------------------
# Breaking: context= kwarg removed
# ---------------------------------------------------------------------------


class TestContextKwargRemoved:
    """Phase 2: ``context=`` is no longer accepted by @step_definition."""

    def test_context_kwarg_rejected_as_unknown(self):
        from pydantic import BaseModel

        class BarContext(BaseModel):
            pass

        with pytest.raises(TypeError, match="context"):
            step_definition(
                instructions=BarInstructions, context=BarContext,  # type: ignore[call-arg]
            )

    def test_no_context_attribute_on_step_class(self):
        @step_definition(instructions=BarInstructions)
        class BarStep(LLMStep):
            def prepare_calls(self) -> List[StepCallParams]:
                return []

        # CONTEXT attribute no longer set by the decorator.
        assert not hasattr(BarStep, "CONTEXT")
