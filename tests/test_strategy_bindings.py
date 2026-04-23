"""Tests for Phase 4 strategy + pipeline contract changes.

Covers the unit-level pieces of the Bind-based execution contract:
- StepDefinition carries ``inputs_spec`` and ``extraction_binds``.
- ``create_step`` attaches them to the step instance.
- ``PipelineStrategy.get_bindings()`` is the abstract method (get_steps removed).
- ``LLMStep.inputs`` starts as None, typed as Optional[StepInputs].
- ``_compile_bind_to_step_def`` converts a Bind into a usable StepDefinition.

End-to-end pipeline runs require pipeline migration (Phase 5) before they
can execute.
"""
from __future__ import annotations

from typing import List, Optional
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.inputs import StepInputs
from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition
from llm_pipeline.strategy import PipelineStrategy, StepDefinition
from llm_pipeline.types import StepCallParams
from llm_pipeline.wiring import Bind, FromInput, FromOutput


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _Input(BaseModel):
    name: str
    count: int


class PingInstructions(LLMResultMixin):
    echo: str


class PingInputs(StepInputs):
    name: str


@step_definition(
    instructions=PingInstructions,
    inputs=PingInputs,
    default_system_key="ping.system",
    default_user_key="ping.user",
)
class PingStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [StepCallParams(variables={"name": self.inputs.name})]


class PongRecord(SQLModel):
    id: Optional[int] = Field(default=None, primary_key=True)
    echo: str


class PongExtraction(PipelineExtraction, model=PongRecord):
    class FromPingInputs(StepInputs):
        echo_value: str

    def from_ping(self, inputs: FromPingInputs) -> list[PongRecord]:
        return [PongRecord(echo=inputs.echo_value)]


# ---------------------------------------------------------------------------
# StepDefinition shape
# ---------------------------------------------------------------------------


class TestStepDefinitionShape:
    def test_inputs_spec_field_defaults_to_none(self):
        spec = PingInputs.sources(name=FromInput("name"))
        sd = StepDefinition(
            step_class=PingStep,
            system_instruction_key="k.system",
            user_prompt_key="k.user",
            instructions=PingInstructions,
        )
        assert sd.inputs_spec is None
        assert sd.extraction_binds == []

        sd_with = StepDefinition(
            step_class=PingStep,
            system_instruction_key="k.system",
            user_prompt_key="k.user",
            instructions=PingInstructions,
            inputs_spec=spec,
        )
        assert sd_with.inputs_spec is spec

    def test_extraction_binds_list_of_bind(self):
        ext_bind = Bind(
            extraction=PongExtraction,
            inputs=PongExtraction.FromPingInputs.sources(
                echo_value=FromInput("name"),
            ),
        )
        sd = StepDefinition(
            step_class=PingStep,
            system_instruction_key="k.system",
            user_prompt_key="k.user",
            instructions=PingInstructions,
            extraction_binds=[ext_bind],
        )
        assert sd.extraction_binds == [ext_bind]


# ---------------------------------------------------------------------------
# create_step attaches bindings to step instance
# ---------------------------------------------------------------------------


class TestCreateStepAttaches:
    def test_inputs_spec_attached_to_step(self, monkeypatch):
        # Stub prompt resolver so create_step doesn't need a real DB.
        from llm_pipeline.prompts import resolver as _resolver
        monkeypatch.setattr(
            _resolver,
            "resolve_with_auto_discovery",
            lambda *_a, **_k: ("sys.key", "user.key"),
        )

        spec = PingInputs.sources(name=FromInput("name"))
        ext_bind = Bind(
            extraction=PongExtraction,
            inputs=PongExtraction.FromPingInputs.sources(
                echo_value=FromInput("name"),
            ),
        )
        sd = StepDefinition(
            step_class=PingStep,
            system_instruction_key="sys.key",
            user_prompt_key="user.key",
            instructions=PingInstructions,
            inputs_spec=spec,
            extraction_binds=[ext_bind],
        )

        fake_pipeline = MagicMock()
        fake_pipeline.session = MagicMock()

        step = sd.create_step(pipeline=fake_pipeline)
        assert step._inputs_spec is spec
        assert step._extraction_binds == [ext_bind]

    def test_step_inputs_attribute_starts_none(self, monkeypatch):
        from llm_pipeline.prompts import resolver as _resolver
        monkeypatch.setattr(
            _resolver,
            "resolve_with_auto_discovery",
            lambda *_a, **_k: ("sys.key", "user.key"),
        )

        sd = StepDefinition(
            step_class=PingStep,
            system_instruction_key="sys.key",
            user_prompt_key="user.key",
            instructions=PingInstructions,
        )
        fake_pipeline = MagicMock()
        step = sd.create_step(pipeline=fake_pipeline)
        # Pipeline populates this before prepare_calls; starts None.
        assert step.inputs is None


# ---------------------------------------------------------------------------
# PipelineStrategy abstract contract
# ---------------------------------------------------------------------------


class TestStrategyAbstractContract:
    def test_strategy_must_implement_get_bindings(self):
        class IncompleteStrategy(PipelineStrategy):
            def can_handle(self, context):
                return True
            # get_bindings not implemented

        with pytest.raises(TypeError, match="abstract"):
            IncompleteStrategy()

    def test_strategy_with_get_bindings_instantiates(self):
        class ValidStrategy(PipelineStrategy):
            def can_handle(self, context):
                return True

            def get_bindings(self) -> List[Bind]:
                return [
                    Bind(
                        step=PingStep,
                        inputs=PingInputs.sources(name=FromInput("name")),
                    ),
                ]

        # Should not raise.
        strat = ValidStrategy()
        bindings = strat.get_bindings()
        assert len(bindings) == 1
        assert bindings[0].step is PingStep


# ---------------------------------------------------------------------------
# LLMStep.inputs attribute
# ---------------------------------------------------------------------------


class TestLLMStepInputsAttribute:
    def test_inputs_attribute_exists_and_is_none_after_init(self):
        fake_pipeline = MagicMock()
        step = PingStep(
            system_instruction_key="sys.key",
            user_prompt_key="user.key",
            instructions=PingInstructions,
            pipeline=fake_pipeline,
        )
        assert step.inputs is None

    def test_inputs_can_be_set_to_stepinputs_instance(self):
        fake_pipeline = MagicMock()
        step = PingStep(
            system_instruction_key="sys.key",
            user_prompt_key="user.key",
            instructions=PingInstructions,
            pipeline=fake_pipeline,
        )
        step.inputs = PingInputs(name="hello")
        assert step.inputs.name == "hello"


# ---------------------------------------------------------------------------
# _compile_bind_to_step_def via PipelineConfig
# ---------------------------------------------------------------------------


class TestCompileBindToStepDef:
    """Test the pipeline helper that converts a Bind into a StepDefinition.

    Uses the real helper by spinning up a minimal PipelineConfig subclass
    only enough to call the method directly.
    """

    def test_compile_carries_inputs_spec_and_extraction_binds(self):
        from llm_pipeline.pipeline import PipelineConfig

        spec = PingInputs.sources(name=FromInput("name"))
        ext_bind = Bind(
            extraction=PongExtraction,
            inputs=PongExtraction.FromPingInputs.sources(
                echo_value=FromOutput(PingStep, field="echo"),
            ),
        )
        bind = Bind(
            step=PingStep,
            inputs=spec,
            extractions=[ext_bind],
        )

        # Call the unbound method directly with a throwaway self; no
        # pipeline state needed.
        compiled = PipelineConfig._compile_bind_to_step_def(
            MagicMock(), bind
        )
        assert compiled.step_class is PingStep
        assert compiled.instructions is PingInstructions
        assert compiled.inputs_spec is spec
        assert compiled.extraction_binds == [ext_bind]


# ---------------------------------------------------------------------------
# process_instructions removed
# ---------------------------------------------------------------------------


class TestProcessInstructionsRemoved:
    def test_llmstep_has_no_process_instructions(self):
        # Base class method is gone; subclasses can still define if they want
        # but nothing in the framework calls it.
        assert not hasattr(LLMStep, "process_instructions")
