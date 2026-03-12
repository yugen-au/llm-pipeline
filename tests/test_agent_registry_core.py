"""
Tests for naming.py, agent_registry.py, agent_builders.py, step.py, strategy.py,
and pipeline.py changes introduced in pydantic-ai-1-agent-registry-core.
"""
from dataclasses import fields as dc_fields
from typing import Any

import pytest
from pydantic import BaseModel

from llm_pipeline.naming import to_snake_case
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.agent_builders import StepDeps, build_step_agent


# ============================================================
# naming.py
# ============================================================

class TestToSnakeCase:
    def test_simple_camel(self):
        assert to_snake_case("ConstraintExtraction") == "constraint_extraction"

    def test_consecutive_capitals_html_parser(self):
        # double-regex required: single regex would produce "htmlparser"
        assert to_snake_case("HTMLParser") == "html_parser"

    def test_consecutive_capitals_io_error(self):
        assert to_snake_case("IOError") == "io_error"

    def test_consecutive_caps_url_resolver(self):
        assert to_snake_case("URLResolver") == "url_resolver"

    def test_strip_suffix_step(self):
        assert to_snake_case("ConstraintExtractionStep", strip_suffix="Step") == "constraint_extraction"

    def test_strip_suffix_strategy(self):
        assert to_snake_case("LaneBasedStrategy", strip_suffix="Strategy") == "lane_based"

    def test_strip_suffix_absent(self):
        # suffix not present -> convert normally, no error
        assert to_snake_case("ConstraintExtraction", strip_suffix="Step") == "constraint_extraction"

    def test_strip_suffix_html_parser_step(self):
        assert to_snake_case("HTMLParserStep", strip_suffix="Step") == "html_parser"

    def test_already_lower(self):
        assert to_snake_case("alreadylower") == "alreadylower"

    def test_single_word(self):
        assert to_snake_case("Parser") == "parser"

    def test_empty_string(self):
        assert to_snake_case("") == ""

    def test_strip_suffix_none_explicit(self):
        # strip_suffix=None should behave same as omitted
        assert to_snake_case("HTMLParser", strip_suffix=None) == "html_parser"


# ============================================================
# agent_registry.py
# ============================================================

class ExtractionOutput(BaseModel):
    value: str


class ValidationOutput(BaseModel):
    valid: bool


class TestAgentRegistryInitSubclass:
    def test_concrete_with_agents_ok(self):
        class MyPipelineAgentRegistry(AgentRegistry, agents={
            "extract_data": ExtractionOutput,
        }):
            pass

        assert MyPipelineAgentRegistry.AGENTS == {"extract_data": ExtractionOutput}

    def test_concrete_without_agents_raises(self):
        with pytest.raises(ValueError, match="agents"):
            class BadRegistry(AgentRegistry):
                pass

    def test_underscore_prefix_skip(self):
        # classes starting with _ are skipped even without agents=
        class _PrivateRegistry(AgentRegistry):
            pass
        # should not raise

    def test_multiple_steps_registered(self):
        class MultistepRegistry(AgentRegistry, agents={
            "step_one": ExtractionOutput,
            "step_two": ValidationOutput,
        }):
            pass

        assert len(MultistepRegistry.AGENTS) == 2
        assert MultistepRegistry.AGENTS["step_one"] is ExtractionOutput
        assert MultistepRegistry.AGENTS["step_two"] is ValidationOutput

    def test_agents_does_not_bleed_to_sibling(self):
        class RegistryA(AgentRegistry, agents={"step_a": ExtractionOutput}):
            pass

        class RegistryB(AgentRegistry, agents={"step_b": ValidationOutput}):
            pass

        assert "step_a" not in RegistryB.AGENTS
        assert "step_b" not in RegistryA.AGENTS


class TestAgentRegistryGetOutputType:
    def setup_method(self):
        class LookupRegistry(AgentRegistry, agents={
            "extract_rates": ExtractionOutput,
            "validate_lanes": ValidationOutput,
        }):
            pass
        self.registry = LookupRegistry

    def test_returns_correct_type(self):
        assert self.registry.get_output_type("extract_rates") is ExtractionOutput

    def test_returns_correct_type_second(self):
        assert self.registry.get_output_type("validate_lanes") is ValidationOutput

    def test_missing_key_raises_key_error(self):
        with pytest.raises(KeyError, match="no_such_step"):
            self.registry.get_output_type("no_such_step")

    def test_key_error_message_includes_available_steps(self):
        with pytest.raises(KeyError) as exc_info:
            self.registry.get_output_type("missing")
        assert "extract_rates" in str(exc_info.value) or "validate_lanes" in str(exc_info.value)


# ============================================================
# agent_builders.py - StepDeps
# ============================================================

class TestStepDepsFields:
    def test_field_count(self):
        f = dc_fields(StepDeps)
        assert len(f) == 10

    def test_required_field_names(self):
        names = [f.name for f in dc_fields(StepDeps)]
        for required in ("session", "pipeline_context", "prompt_service",
                         "run_id", "pipeline_name", "step_name"):
            assert required in names

    def test_optional_field_names(self):
        names = [f.name for f in dc_fields(StepDeps)]
        assert "event_emitter" in names
        assert "variable_resolver" in names
        assert "array_validation" in names
        assert "validation_context" in names

    def test_optional_defaults_none(self):
        import dataclasses
        defaults = {
            f.name: f.default
            for f in dc_fields(StepDeps)
            if f.default is not dataclasses.MISSING
        }
        assert defaults.get("event_emitter") is None
        assert defaults.get("variable_resolver") is None
        assert defaults.get("array_validation") is None
        assert defaults.get("validation_context") is None

    def test_instantiation_with_required_only(self):
        deps = StepDeps(
            session=object(),
            pipeline_context={},
            prompt_service=object(),
            run_id="run-1",
            pipeline_name="test_pipeline",
            step_name="extract_data",
        )
        assert deps.event_emitter is None
        assert deps.variable_resolver is None
        assert deps.run_id == "run-1"

    def test_instantiation_with_all_fields(self):
        mock_emitter = object()
        mock_resolver = object()
        deps = StepDeps(
            session=object(),
            pipeline_context={"key": "val"},
            prompt_service=object(),
            run_id="run-2",
            pipeline_name="my_pipeline",
            step_name="validate",
            event_emitter=mock_emitter,
            variable_resolver=mock_resolver,
        )
        assert deps.event_emitter is mock_emitter
        assert deps.variable_resolver is mock_resolver


# ============================================================
# agent_builders.py - build_step_agent
# ============================================================

class SimpleOutput(BaseModel):
    result: str


class TestBuildStepAgent:
    def test_returns_agent_instance(self):
        from pydantic_ai import Agent
        agent = build_step_agent("test_step", SimpleOutput)
        assert isinstance(agent, Agent)

    def test_defer_model_check_true(self):
        # Agent should construct without a model (defer_model_check=True)
        agent = build_step_agent("test_step", SimpleOutput, model=None)
        assert agent is not None

    def test_agent_name_set(self):
        agent = build_step_agent("my_step_name", SimpleOutput)
        assert agent.name == "my_step_name"

    def test_retries_custom(self):
        agent = build_step_agent("step", SimpleOutput, retries=5)
        assert agent._max_result_retries == 5

    def test_retries_default(self):
        agent = build_step_agent("step", SimpleOutput)
        assert agent._max_result_retries == 3

    def test_with_explicit_model_string(self):
        from pydantic_ai import Agent
        # model string provided; defer_model_check still True
        agent = build_step_agent("step", SimpleOutput, model="test:dummy")
        assert isinstance(agent, Agent)

    def test_instructions_registered(self):
        # @agent.instructions decorator registers a function;
        # check internal _instructions_functions list is non-empty
        agent = build_step_agent("step", SimpleOutput)
        # pydantic-ai stores registered instruction fns on the agent
        assert hasattr(agent, '_instructions_functions') or hasattr(agent, '_system_prompts')


# ============================================================
# step.py - LLMStep.get_agent(), build_user_prompt() deprecation
# ============================================================

class TestLLMStepMethods:
    """Test LLMStep new methods using a minimal concrete subclass."""

    def _make_step(self, agent_name_override=None):
        from llm_pipeline.step import LLMStep
        from pydantic import BaseModel as PB

        class FakeInstructions(PB):
            data: str

        class MockPipeline:
            pipeline_name = "test"
            run_id = "r1"
            _variable_resolver = None

        class ExtractDataStep(LLMStep):
            def prepare_calls(self):
                return []

        step = ExtractDataStep(
            system_instruction_key="sys_key",
            user_prompt_key="user_key",
            instructions=FakeInstructions,
            pipeline=MockPipeline(),
        )
        if agent_name_override is not None:
            step._agent_name = agent_name_override
        return step

    def test_step_name_snake_case(self):
        step = self._make_step()
        assert step.step_name == "extract_data"

    def test_get_agent_uses_step_name(self):
        class GetAgentRegistry(AgentRegistry, agents={
            "extract_data": ExtractionOutput,
        }):
            pass
        step = self._make_step()
        output_type = step.get_agent(GetAgentRegistry)
        assert output_type is ExtractionOutput

    def test_get_agent_uses_override(self):
        class OverrideRegistry(AgentRegistry, agents={
            "custom_name": ValidationOutput,
        }):
            pass
        step = self._make_step(agent_name_override="custom_name")
        output_type = step.get_agent(OverrideRegistry)
        assert output_type is ValidationOutput

    def test_build_user_prompt_calls_service(self):
        step = self._make_step()

        class MockPromptService:
            def get_user_prompt(self, key, variables, variable_instance, context):
                return f"prompt:{key}:{variables.get('x')}"

        result = step.build_user_prompt({"x": "hello"}, MockPromptService())
        assert result == "prompt:user_key:hello"

    def test_build_user_prompt_model_dump(self):
        from pydantic import BaseModel as PB
        step = self._make_step()

        class VarModel(PB):
            x: str = "world"

        class MockPromptService:
            def get_user_prompt(self, key, variables, variable_instance, context):
                return f"prompt:{variables.get('x')}"

        result = step.build_user_prompt(VarModel(), MockPromptService())
        assert result == "prompt:world"

# ============================================================
# strategy.py - StepDefinition.agent_name, step_name property
# ============================================================

class TestStepDefinitionNewFields:
    def _make_step_def(self, step_class, agent_name=None):
        from llm_pipeline.strategy import StepDefinition
        from pydantic import BaseModel as PB

        class DummyInstructions(PB):
            pass

        return StepDefinition(
            step_class=step_class,
            system_instruction_key="sys",
            user_prompt_key="user",
            instructions=DummyInstructions,
            agent_name=agent_name,
        )

    def test_step_name_property_simple(self):
        from llm_pipeline.step import LLMStep

        class ExtractRatesStep(LLMStep):
            def prepare_calls(self): return []

        sd = self._make_step_def(ExtractRatesStep)
        assert sd.step_name == "extract_rates"

    def test_step_name_property_consecutive_caps(self):
        from llm_pipeline.step import LLMStep

        class HTMLParserStep(LLMStep):
            def prepare_calls(self): return []

        sd = self._make_step_def(HTMLParserStep)
        assert sd.step_name == "html_parser"

    def test_agent_name_default_none(self):
        from llm_pipeline.step import LLMStep

        class SomeStep(LLMStep):
            def prepare_calls(self): return []

        sd = self._make_step_def(SomeStep)
        assert sd.agent_name is None

    def test_agent_name_can_be_set(self):
        from llm_pipeline.step import LLMStep

        class AnotherStep(LLMStep):
            def prepare_calls(self): return []

        sd = self._make_step_def(AnotherStep, agent_name="custom_agent")
        assert sd.agent_name == "custom_agent"

    def test_create_step_sets_agent_name_on_instance(self):
        """create_step() should copy agent_name onto step._agent_name."""
        from llm_pipeline.step import LLMStep
        from llm_pipeline.strategy import StepDefinition
        from pydantic import BaseModel as PB
        from unittest.mock import MagicMock, patch
        from sqlmodel import create_engine, Session
        import llm_pipeline.db.prompt  # ensure model is registered

        class AgentNameInstructions(PB):
            pass

        class AgentNameStep(LLMStep):
            def prepare_calls(self): return []

        sd = StepDefinition(
            step_class=AgentNameStep,
            system_instruction_key="sys",
            user_prompt_key="user",
            instructions=AgentNameInstructions,
            agent_name="override_name",
        )

        # build an in-memory session with prompt tables for create_step
        from llm_pipeline.db import init_pipeline_db
        engine = create_engine("sqlite:///:memory:")
        init_pipeline_db(engine)
        session = Session(engine)

        # add prompts so create_step doesn't raise
        from llm_pipeline.db.prompt import Prompt
        session.add(Prompt(prompt_key="sys", prompt_name="sys", prompt_type="system", content="x", is_active=True))
        session.add(Prompt(prompt_key="user", prompt_name="user", prompt_type="user", content="y", is_active=True))
        session.commit()

        class FakePipeline:
            pass
        fake_pipeline = FakePipeline()
        fake_pipeline.session = session
        fake_pipeline._current_strategy = None

        step = sd.create_step(fake_pipeline)
        assert step._agent_name == "override_name"

        session.close()
        engine.dispose()


# ============================================================
# pipeline.py - PipelineConfig agent_registry= param
# Module-level SQLModel tables and registry classes to avoid SQLModel
# table-redefinition errors when test methods run in the same process.
# ============================================================

from typing import Optional as _Opt
from sqlmodel import SQLModel as _SQLModel, Field as _Field
from llm_pipeline.registry import PipelineDatabaseRegistry as _PDR
from llm_pipeline.pipeline import PipelineConfig as _PC

class _NoARModel(_SQLModel, table=True):
    __tablename__ = "test_no_ar_model"
    id: _Opt[int] = _Field(default=None, primary_key=True)

class _NoARRegistry(_PDR, models=[_NoARModel]):
    pass

class _NoARPipeline(_PC, registry=_NoARRegistry):
    pass

class _ARModel(_SQLModel, table=True):
    __tablename__ = "test_ar_model"
    id: _Opt[int] = _Field(default=None, primary_key=True)

class _ARRegistry(_PDR, models=[_ARModel]):
    pass

class _ARAgentRegistry(AgentRegistry, agents={"step_one": ExtractionOutput}):
    pass

class _ARPipeline(_PC, registry=_ARRegistry, agent_registry=_ARAgentRegistry):
    pass

class _WrongModel(_SQLModel, table=True):
    __tablename__ = "test_wrong_model"
    id: _Opt[int] = _Field(default=None, primary_key=True)

# Registry named to match "WrongARPipeline" -> "WrongARRegistry"
class WrongARRegistry(_PDR, models=[_WrongModel]):
    pass

# Agent registry intentionally misnamed (should be "WrongARAgentRegistry")
class _WrongNamedAgentReg(AgentRegistry, agents={"s": ExtractionOutput}):
    pass


class TestPipelineConfigAgentRegistry:
    def test_agent_registry_none_is_ok(self):
        """Existing pipelines with no agent_registry= must still work."""
        assert _NoARPipeline.AGENT_REGISTRY is None

    def test_agent_registry_accepted_and_stored(self):
        assert _ARPipeline.AGENT_REGISTRY is _ARAgentRegistry

    def test_wrong_agent_registry_name_raises(self):
        with pytest.raises(ValueError, match="AgentRegistry"):
            class WrongARPipeline(
                _PC,
                registry=WrongARRegistry,
                agent_registry=_WrongNamedAgentReg,
            ):
                pass

    def test_class_var_agent_registry_on_base_is_none(self):
        from llm_pipeline.pipeline import PipelineConfig
        assert PipelineConfig.AGENT_REGISTRY is None
