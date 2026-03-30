"""
Tests for naming.py, agent_registry.py, agent_builders.py, step.py, strategy.py,
and pipeline.py -- updated for global agent registry API.
"""
from dataclasses import fields as dc_fields
from typing import Any

import pytest
from pydantic import BaseModel

from llm_pipeline.naming import to_snake_case
from llm_pipeline.agent_registry import (
    AgentSpec,
    register_agent,
    get_agent_tools,
    get_registered_agents,
    clear_agent_registry,
)
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
# agent_registry.py - global registry functions
# ============================================================

class TestAgentSpec:
    def test_default_tools_empty(self):
        spec = AgentSpec()
        assert spec.tools == []

    def test_tools_stored(self):
        def my_tool(): pass
        spec = AgentSpec(tools=[my_tool])
        assert spec.tools == [my_tool]

    def test_is_dataclass(self):
        fields = dc_fields(AgentSpec)
        names = [f.name for f in fields]
        assert names == ["tools"]


class TestRegisterAgent:
    def setup_method(self):
        clear_agent_registry()

    def teardown_method(self):
        clear_agent_registry()

    def test_register_and_retrieve(self):
        def tool_a(): pass
        register_agent("my_agent", tools=[tool_a])
        assert get_agent_tools("my_agent") == [tool_a]

    def test_register_multiple_agents(self):
        def t1(): pass
        def t2(): pass
        register_agent("agent_a", tools=[t1])
        register_agent("agent_b", tools=[t2])
        assert get_agent_tools("agent_a") == [t1]
        assert get_agent_tools("agent_b") == [t2]

    def test_register_overwrites_existing(self):
        def old_tool(): pass
        def new_tool(): pass
        register_agent("overwrite_me", tools=[old_tool])
        register_agent("overwrite_me", tools=[new_tool])
        assert get_agent_tools("overwrite_me") == [new_tool]

    def test_register_empty_tools(self):
        register_agent("no_tools", tools=[])
        assert get_agent_tools("no_tools") == []

    def test_tools_list_is_copied(self):
        """Mutating original list should not affect registry."""
        tools = [lambda: None]
        register_agent("copy_test", tools=tools)
        tools.append(lambda: None)
        assert len(get_agent_tools("copy_test")) == 1


class TestGetAgentTools:
    def setup_method(self):
        clear_agent_registry()

    def teardown_method(self):
        clear_agent_registry()

    def test_unknown_agent_returns_empty_list(self):
        assert get_agent_tools("nonexistent") == []

    def test_returns_correct_tools(self):
        def my_tool(): pass
        register_agent("lookup_test", tools=[my_tool])
        assert get_agent_tools("lookup_test") == [my_tool]


class TestGetRegisteredAgents:
    def setup_method(self):
        clear_agent_registry()

    def teardown_method(self):
        clear_agent_registry()

    def test_empty_registry(self):
        assert get_registered_agents() == {}

    def test_returns_all_registered(self):
        register_agent("a", tools=[])
        register_agent("b", tools=[])
        result = get_registered_agents()
        assert set(result.keys()) == {"a", "b"}
        assert all(isinstance(v, AgentSpec) for v in result.values())

    def test_returns_copy(self):
        """Mutating returned dict should not affect registry."""
        register_agent("orig", tools=[])
        copy = get_registered_agents()
        copy["injected"] = AgentSpec(tools=[])
        assert "injected" not in get_registered_agents()


class TestClearAgentRegistry:
    def teardown_method(self):
        clear_agent_registry()

    def test_clears_all(self):
        register_agent("temp", tools=[])
        clear_agent_registry()
        assert get_registered_agents() == {}
        assert get_agent_tools("temp") == []


# ============================================================
# agent_builders.py - StepDeps
# ============================================================

class TestStepDepsFields:
    def test_field_count(self):
        f = dc_fields(StepDeps)
        assert len(f) == 11

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
# step.py - LLMStep.step_name, build_user_prompt()
# ============================================================

class TestLLMStepMethods:
    """Test LLMStep methods using a minimal concrete subclass."""

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
# agent_builders.py - build_step_agent validators param
# ============================================================

class TestBuildStepAgentValidators:
    def test_validators_param_accepted(self):
        # empty list must not raise
        agent = build_step_agent("step", SimpleOutput, validators=[])
        assert agent is not None

    def test_validators_none_accepted(self):
        # None (default) must not raise
        agent = build_step_agent("step", SimpleOutput, validators=None)
        assert agent is not None

    def test_validators_registered(self):
        from pydantic_ai import RunContext

        async def dummy_validator(ctx: RunContext, output: Any) -> Any:
            return output

        agent = build_step_agent("step", SimpleOutput, validators=[dummy_validator])
        # pydantic-ai stores output validators on _output_validators
        assert hasattr(agent, "_output_validators")
        validator_fns = [v.function for v in agent._output_validators]
        assert dummy_validator in validator_fns

    def test_multiple_validators_registered_in_order(self):
        from pydantic_ai import RunContext

        async def first_validator(ctx: RunContext, output: Any) -> Any:
            return output

        async def second_validator(ctx: RunContext, output: Any) -> Any:
            return output

        agent = build_step_agent(
            "step", SimpleOutput, validators=[first_validator, second_validator]
        )
        validator_fns = [v.function for v in agent._output_validators]
        assert first_validator in validator_fns
        assert second_validator in validator_fns
        assert validator_fns.index(first_validator) < validator_fns.index(second_validator)

    def test_validation_context_wired(self):
        agent = build_step_agent("step", SimpleOutput)
        # Agent constructor accepts validation_context kwarg; verify it is set
        # pydantic-ai stores it as _validation_context on the agent
        assert hasattr(agent, "_validation_context")
        assert agent._validation_context is not None
        assert callable(agent._validation_context)


# ============================================================
# agent_builders.py - build_step_agent tools param
# ============================================================

class TestBuildStepAgentTools:
    """Tests for the tools parameter of build_step_agent.

    Verifies that tool callables are wrapped in FunctionToolset ->
    EventEmittingToolset and attached to the Agent via toolsets=.
    """

    @staticmethod
    def _dummy_tool(query: str) -> str:
        """A minimal tool callable for testing."""
        return f"result:{query}"

    @staticmethod
    def _another_tool(x: int) -> int:
        """Second tool callable for multi-tool tests."""
        return x * 2

    def test_tools_none_no_toolset(self):
        """tools=None (default) should not attach any user toolsets."""
        agent = build_step_agent("step", SimpleOutput, tools=None)
        assert agent._user_toolsets == []

    def test_tools_empty_list_no_toolset(self):
        """tools=[] (falsy) should not attach any user toolsets."""
        agent = build_step_agent("step", SimpleOutput, tools=[])
        assert agent._user_toolsets == []

    def test_tools_provided_attaches_toolset(self):
        """Non-empty tools list should produce exactly one user toolset."""
        agent = build_step_agent("step", SimpleOutput, tools=[self._dummy_tool])
        assert len(agent._user_toolsets) == 1

    def test_tools_wrapped_in_event_emitting_toolset(self):
        """The attached toolset should be an EventEmittingToolset."""
        from llm_pipeline.toolsets import EventEmittingToolset

        agent = build_step_agent("step", SimpleOutput, tools=[self._dummy_tool])
        toolset = agent._user_toolsets[0]
        assert isinstance(toolset, EventEmittingToolset)

    def test_inner_toolset_is_function_toolset(self):
        """EventEmittingToolset.wrapped should be a FunctionToolset."""
        from pydantic_ai.toolsets import FunctionToolset

        agent = build_step_agent("step", SimpleOutput, tools=[self._dummy_tool])
        toolset = agent._user_toolsets[0]
        assert isinstance(toolset.wrapped, FunctionToolset)

    def test_multiple_tools_registered(self):
        """Multiple tool callables should all be registered in the inner toolset."""
        agent = build_step_agent(
            "step", SimpleOutput, tools=[self._dummy_tool, self._another_tool]
        )
        assert len(agent._user_toolsets) == 1
        # inner FunctionToolset.tools is a dict keyed by tool name
        inner = agent._user_toolsets[0].wrapped
        tool_names = list(inner.tools.keys())
        assert "_dummy_tool" in tool_names
        assert "_another_tool" in tool_names

    def test_tools_with_other_params_coexist(self):
        """tools param should work alongside validators and instrument."""
        from pydantic_ai import RunContext

        async def dummy_validator(ctx: RunContext, output: Any) -> Any:
            return output

        agent = build_step_agent(
            "step",
            SimpleOutput,
            validators=[dummy_validator],
            tools=[self._dummy_tool],
        )
        # toolset attached
        assert len(agent._user_toolsets) == 1
        # validator also registered
        validator_fns = [v.function for v in agent._output_validators]
        assert dummy_validator in validator_fns

    def test_agent_still_valid_with_tools(self):
        """Agent with tools should still have correct name and retries."""
        from pydantic_ai import Agent

        agent = build_step_agent(
            "my_tool_step", SimpleOutput, retries=7, tools=[self._dummy_tool]
        )
        assert isinstance(agent, Agent)
        assert agent.name == "my_tool_step"
        assert agent._max_result_retries == 7
