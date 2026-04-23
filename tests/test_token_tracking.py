"""Unit tests for token capture, event enrichment, and instrumentation settings threading.

Covers:
1. LLMCallCompleted events have input_tokens, output_tokens, total_tokens
2. StepCompleted event has step-aggregate token values
3. PipelineStepState DB record has token + request fields after _save_step_state()
4. Consensus path sums tokens across all attempts; total_requests = call count
5. When run_result.usage() returns None or zero, fields stored as None/0
6. Pipeline without instrumentation_settings still works
7. build_step_agent() passes instrument= when instrumentation_settings provided
"""
import pytest
from typing import ClassVar, List, Optional
from unittest.mock import MagicMock, patch, call

from sqlmodel import SQLModel, Field, Session, create_engine, select

from llm_pipeline import (
    LLMResultMixin,
    LLMStep,
    MajorityVoteStrategy,
    PipelineConfig,
    PipelineDatabaseRegistry,
    PipelineStepState,
    PipelineStrategies,
    PipelineStrategy,
    step_definition,
)
from llm_pipeline.context import PipelineInputData
from llm_pipeline.db import init_pipeline_db
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.events.handlers import InMemoryEventHandler
from llm_pipeline.inputs import StepInputs
from llm_pipeline.types import StepCallParams
from llm_pipeline.wiring import Bind, FromInput


# ---------------------------------------------------------------------------
# Domain model / instructions / step boilerplate
# ---------------------------------------------------------------------------

class TokenWidget(SQLModel, table=True):
    __tablename__ = "token_widgets"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str


class TokenPipelineInput(PipelineInputData):
    data: str


class TokenInputs(StepInputs):
    data: str


class TokenInstructions(LLMResultMixin):
    count: int
    example: ClassVar[dict] = {"count": 1, "notes": "test"}


@step_definition(
    inputs=TokenInputs,
    instructions=TokenInstructions,
    default_system_key="token.system",
    default_user_key="token.user",
)
class TokenStep(LLMStep):
    def prepare_calls(self) -> List[StepCallParams]:
        return [StepCallParams(variables={"data": self.inputs.data})]


class TokenStrategy(PipelineStrategy):
    def can_handle(self, context):
        return True

    def get_bindings(self) -> List[Bind]:
        return [
            Bind(
                step=TokenStep,
                inputs=TokenInputs.sources(data=FromInput("data")),
            ),
        ]


class TokenRegistry(PipelineDatabaseRegistry, models=[TokenWidget]):
    pass


class TokenStrategies(PipelineStrategies, strategies=[TokenStrategy]):
    pass


class TokenPipeline(
    PipelineConfig,
    registry=TokenRegistry,
    strategies=TokenStrategies,
):
    INPUT_DATA = TokenPipelineInput


def _consensus_token_strategies(threshold, max_calls):
    """Build strategy instances with MajorityVoteStrategy on the token step."""
    mv = MajorityVoteStrategy(threshold=threshold, max_attempts=max_calls)

    class ConsensusTokenTestStrategy(PipelineStrategy):
        def can_handle(self, context):
            return True
        def get_bindings(self) -> List[Bind]:
            return [
                Bind(
                    step=TokenStep,
                    inputs=TokenInputs.sources(data=FromInput("data")),
                    consensus_strategy=mv,
                ),
            ]

    return [ConsensusTokenTestStrategy()]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


from tests.conftest import _mock_usage  # shared helper from root tests/conftest.py


def _make_run_result(count=1, input_tokens=10, output_tokens=5):
    """Build mock AgentRunResult with configurable token usage."""
    instruction = TokenInstructions(count=count, confidence_score=1.0, notes="ok")
    mock_result = MagicMock()
    mock_result.output = instruction
    mock_result.usage.return_value = _mock_usage(input_tokens, output_tokens)
    return mock_result


def _make_run_result_no_usage(count=1):
    """Build mock AgentRunResult where usage() returns None."""
    instruction = TokenInstructions(count=count, confidence_score=1.0, notes="ok")
    mock_result = MagicMock()
    mock_result.output = instruction
    mock_result.usage.return_value = None
    return mock_result


def _make_run_result_zero_usage(count=1):
    """Build mock AgentRunResult where usage() returns zero tokens."""
    instruction = TokenInstructions(count=count, confidence_score=1.0, notes="ok")
    mock_result = MagicMock()
    mock_result.output = instruction
    mock_result.usage.return_value = _mock_usage(input_tokens=0, output_tokens=0)
    return mock_result


def _seed_prompts(session):
    """Add prompts needed by TokenStep."""
    session.add(Prompt(
        prompt_key="token.system",
        prompt_name="Token System",
        prompt_type="system",
        category="test",
        step_name="token",
        content="You are a test assistant.",
        version="1.0",
    ))
    session.add(Prompt(
        prompt_key="token.user",
        prompt_name="Token User",
        prompt_type="user",
        category="test",
        step_name="token",
        content="Process: {data}",
        version="1.0",
    ))
    session.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def token_engine():
    engine = create_engine("sqlite:///:memory:")
    init_pipeline_db(engine)
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def token_session(token_engine):
    with Session(token_engine) as session:
        _seed_prompts(session)
        yield session


@pytest.fixture
def handler():
    return InMemoryEventHandler()


# ---------------------------------------------------------------------------
# 1. LLMCallCompleted events have token fields populated
# ---------------------------------------------------------------------------


class TestLLMCallCompletedTokens:
    """LLMCallCompleted events carry per-call token values."""

    def test_input_tokens_populated(self, token_session, handler):
        pipeline = TokenPipeline(
            session=token_session, model="test-model", event_emitter=handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(input_tokens=20, output_tokens=8)):
            pipeline.execute(input_data={"data": "d"})

        events = handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert len(completed) == 1
        assert completed[0]["input_tokens"] == 20

    def test_output_tokens_populated(self, token_session, handler):
        pipeline = TokenPipeline(
            session=token_session, model="test-model", event_emitter=handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(input_tokens=20, output_tokens=8)):
            pipeline.execute(input_data={"data": "d"})

        events = handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert completed[0]["output_tokens"] == 8

    def test_total_tokens_computed(self, token_session, handler):
        pipeline = TokenPipeline(
            session=token_session, model="test-model", event_emitter=handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(input_tokens=20, output_tokens=8)):
            pipeline.execute(input_data={"data": "d"})

        events = handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert completed[0]["total_tokens"] == 28

    def test_tokens_none_when_no_usage(self, token_session, handler):
        """When usage() returns None, LLMCallCompleted token fields are None."""
        pipeline = TokenPipeline(
            session=token_session, model="test-model", event_emitter=handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result_no_usage()):
            pipeline.execute(input_data={"data": "d"})

        events = handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert completed[0]["input_tokens"] is None
        assert completed[0]["output_tokens"] is None
        assert completed[0]["total_tokens"] is None


# ---------------------------------------------------------------------------
# 2. StepCompleted event has step-aggregate token values
# ---------------------------------------------------------------------------


class TestStepCompletedTokens:
    """StepCompleted events carry step-level aggregated token values."""

    def test_step_completed_has_tokens(self, token_session, handler):
        pipeline = TokenPipeline(
            session=token_session, model="test-model", event_emitter=handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(input_tokens=15, output_tokens=7)):
            pipeline.execute(input_data={"data": "d"})

        events = handler.get_events()
        step_completed = [e for e in events if e["event_type"] == "step_completed"]
        assert len(step_completed) == 1
        assert step_completed[0]["input_tokens"] == 15
        assert step_completed[0]["output_tokens"] == 7
        assert step_completed[0]["total_tokens"] == 22

    def test_step_completed_tokens_zero_when_no_usage(self, token_session, handler):
        """StepCompleted token fields are 0 when usage() returns None.

        _step_total_requests increments even without usage data, so the
        guard (_step_total_requests > 0) passes, yielding accumulator
        values of 0 rather than None.
        """
        pipeline = TokenPipeline(
            session=token_session, model="test-model", event_emitter=handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result_no_usage()):
            pipeline.execute(input_data={"data": "d"})

        events = handler.get_events()
        step_completed = [e for e in events if e["event_type"] == "step_completed"]
        assert step_completed[0]["input_tokens"] == 0
        assert step_completed[0]["output_tokens"] == 0
        assert step_completed[0]["total_tokens"] == 0


# ---------------------------------------------------------------------------
# 3. PipelineStepState DB record has token and request fields
# ---------------------------------------------------------------------------


class TestPipelineStepStateTokens:
    """PipelineStepState DB record persists token fields after _save_step_state()."""

    def test_state_has_input_tokens(self, token_engine, token_session):
        pipeline = TokenPipeline(session=token_session, model="test-model")
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(input_tokens=30, output_tokens=12)):
            pipeline.execute(input_data={"data": "d"})

        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert len(states) == 1
        assert states[0].input_tokens == 30

    def test_state_has_output_tokens(self, token_engine, token_session):
        pipeline = TokenPipeline(session=token_session, model="test-model")
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(input_tokens=30, output_tokens=12)):
            pipeline.execute(input_data={"data": "d"})

        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].output_tokens == 12

    def test_state_has_total_tokens(self, token_engine, token_session):
        pipeline = TokenPipeline(session=token_session, model="test-model")
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result(input_tokens=30, output_tokens=12)):
            pipeline.execute(input_data={"data": "d"})

        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].total_tokens == 42

    def test_state_has_total_requests(self, token_engine, token_session):
        pipeline = TokenPipeline(session=token_session, model="test-model")
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result()):
            pipeline.execute(input_data={"data": "d"})

        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].total_requests == 1

    def test_state_tokens_zero_when_no_usage(self, token_engine, token_session):
        """When usage() returns None, DB fields stored as 0 (not None).

        _step_total_requests increments unconditionally, so the guard
        passes and accumulator values (0) are persisted.
        """
        pipeline = TokenPipeline(session=token_session, model="test-model")
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result_no_usage()):
            pipeline.execute(input_data={"data": "d"})

        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].input_tokens == 0
        assert states[0].output_tokens == 0
        assert states[0].total_tokens == 0
        assert states[0].total_requests == 1


# ---------------------------------------------------------------------------
# 4. Consensus path sums tokens across all attempts
# ---------------------------------------------------------------------------


class TestConsensusTokenAggregation:
    """Consensus path accumulates tokens across attempts."""

    def _run_consensus(self, token_session, handler, counts, input_tokens_list, output_tokens_list,
                       threshold=2, max_calls=5):
        """Run pipeline with consensus and specific per-call token values."""
        responses = []
        for i, count in enumerate(counts):
            it = input_tokens_list[i] if i < len(input_tokens_list) else 10
            ot = output_tokens_list[i] if i < len(output_tokens_list) else 5
            responses.append(_make_run_result(count=count, input_tokens=it, output_tokens=ot))

        call_idx = [0]

        def _side_effect(*args, **kwargs):
            idx = call_idx[0]
            call_idx[0] += 1
            if idx < len(responses):
                return responses[idx]
            return responses[-1]

        pipeline = TokenPipeline(
            session=token_session, model="test-model",
            event_emitter=handler,
            strategies=_consensus_token_strategies(threshold, max_calls),
        )
        with patch("pydantic_ai.Agent.run_sync", side_effect=_side_effect):
            pipeline.execute(input_data={"data": "d"})
        return pipeline

    def test_consensus_sums_input_tokens(self, token_engine, token_session, handler):
        """Consensus with 2 calls: input_tokens summed."""
        # identical counts -> consensus on attempt 2
        self._run_consensus(
            token_session, handler,
            counts=[1, 1],
            input_tokens_list=[20, 30],
            output_tokens_list=[5, 10],
            threshold=2, max_calls=5,
        )
        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert len(states) == 1
        assert states[0].input_tokens == 50  # 20 + 30

    def test_consensus_sums_output_tokens(self, token_engine, token_session, handler):
        self._run_consensus(
            token_session, handler,
            counts=[1, 1],
            input_tokens_list=[20, 30],
            output_tokens_list=[5, 10],
            threshold=2, max_calls=5,
        )
        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].output_tokens == 15  # 5 + 10

    def test_consensus_total_tokens_is_sum(self, token_engine, token_session, handler):
        self._run_consensus(
            token_session, handler,
            counts=[1, 1],
            input_tokens_list=[20, 30],
            output_tokens_list=[5, 10],
            threshold=2, max_calls=5,
        )
        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].total_tokens == 65  # (20+30) + (5+10)

    def test_consensus_total_requests_equals_attempts(self, token_engine, token_session, handler):
        """total_requests = number of consensus calls made."""
        self._run_consensus(
            token_session, handler,
            counts=[1, 1],
            input_tokens_list=[10, 10],
            output_tokens_list=[5, 5],
            threshold=2, max_calls=5,
        )
        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].total_requests == 2

    def test_consensus_per_call_events_have_individual_tokens(self, token_engine, token_session, handler):
        """Each LLMCallCompleted in consensus has per-call (not aggregate) tokens."""
        self._run_consensus(
            token_session, handler,
            counts=[1, 1],
            input_tokens_list=[20, 30],
            output_tokens_list=[5, 10],
            threshold=2, max_calls=5,
        )
        events = handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert len(completed) == 2
        assert completed[0]["input_tokens"] == 20
        assert completed[0]["output_tokens"] == 5
        assert completed[1]["input_tokens"] == 30
        assert completed[1]["output_tokens"] == 10

    def test_consensus_failed_still_accumulates(self, token_engine, token_session, handler):
        """Failed consensus (all different) still accumulates tokens."""
        self._run_consensus(
            token_session, handler,
            counts=[1, 2, 3],
            input_tokens_list=[10, 20, 30],
            output_tokens_list=[2, 4, 6],
            threshold=3, max_calls=3,
        )
        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].input_tokens == 60  # 10+20+30
        assert states[0].output_tokens == 12  # 2+4+6
        assert states[0].total_requests == 3


# ---------------------------------------------------------------------------
# 5. Usage returns None or zero -- no crash
# ---------------------------------------------------------------------------


class TestNullAndZeroUsage:
    """Pipeline handles None/zero usage() gracefully."""

    def test_none_usage_no_crash(self, token_engine, token_session):
        """Pipeline completes when usage() returns None."""
        pipeline = TokenPipeline(session=token_session, model="test-model")
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result_no_usage()):
            result = pipeline.execute(input_data={"data": "d"})
        assert result is pipeline

    def test_zero_usage_stored(self, token_engine, token_session):
        """Zero tokens from usage() stored as 0 in DB."""
        pipeline = TokenPipeline(session=token_session, model="test-model")
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result_zero_usage()):
            pipeline.execute(input_data={"data": "d"})

        with Session(token_engine) as s:
            states = s.exec(select(PipelineStepState)).all()
        assert states[0].input_tokens == 0
        assert states[0].output_tokens == 0
        assert states[0].total_tokens == 0
        assert states[0].total_requests == 1

    def test_zero_usage_events_carry_zero(self, token_engine, token_session, handler):
        """Events carry 0 (not None) when usage has zero tokens."""
        pipeline = TokenPipeline(
            session=token_session, model="test-model", event_emitter=handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result_zero_usage()):
            pipeline.execute(input_data={"data": "d"})

        events = handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert completed[0]["input_tokens"] == 0
        assert completed[0]["output_tokens"] == 0
        assert completed[0]["total_tokens"] == 0

    def test_none_usage_consensus_no_crash(self, token_engine, token_session):
        """Consensus path completes when usage() returns None."""
        result_none = _make_run_result_no_usage(count=1)
        pipeline = TokenPipeline(
            session=token_session, model="test-model",
            strategies=_consensus_token_strategies(threshold=2, max_calls=5),
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=result_none):
            result = pipeline.execute(input_data={"data": "d"})
        assert result is pipeline


# ---------------------------------------------------------------------------
# 6. Pipeline without instrumentation_settings works
# ---------------------------------------------------------------------------


class TestNoInstrumentationSettings:
    """Pipeline with instrumentation_settings=None still works; build_step_agent not passed instrument."""

    def test_pipeline_works_without_instrumentation(self, token_engine, token_session):
        """Pipeline executes successfully without instrumentation_settings."""
        pipeline = TokenPipeline(
            session=token_session, model="test-model",
            instrumentation_settings=None,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result()):
            result = pipeline.execute(input_data={"data": "d"})
        assert result is pipeline

    def test_build_step_agent_called_without_instrument_kwarg(self, token_engine, token_session):
        """build_step_agent() called with instrument=None when no instrumentation_settings."""
        from llm_pipeline.agent_builders import build_step_agent as real_build
        pipeline = TokenPipeline(
            session=token_session, model="test-model",
            instrumentation_settings=None,
        )
        with patch("llm_pipeline.agent_builders.build_step_agent", side_effect=real_build) as mock_build:
            with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result()):
                pipeline.execute(input_data={"data": "d"})

        assert mock_build.called
        _, kwargs = mock_build.call_args
        assert kwargs.get("instrument") is None


# ---------------------------------------------------------------------------
# 7. build_step_agent() passes instrument when instrumentation_settings provided
# ---------------------------------------------------------------------------


class TestInstrumentationSettingsThreading:
    """instrumentation_settings threaded from PipelineConfig to build_step_agent."""

    def test_build_step_agent_receives_instrument(self, token_engine, token_session):
        """build_step_agent() called with instrument= when instrumentation_settings provided."""
        from llm_pipeline.agent_builders import build_step_agent as real_build
        fake_settings = MagicMock(name="FakeInstrumentationSettings")
        pipeline = TokenPipeline(
            session=token_session, model="test-model",
            instrumentation_settings=fake_settings,
        )
        with patch("llm_pipeline.agent_builders.build_step_agent", side_effect=real_build) as mock_build:
            with patch("pydantic_ai.Agent.run_sync", return_value=_make_run_result()):
                pipeline.execute(input_data={"data": "d"})

        assert mock_build.called
        _, kwargs = mock_build.call_args
        assert kwargs["instrument"] is fake_settings

    def test_agent_constructor_receives_instrument(self, token_engine, token_session):
        """Agent() constructor receives instrument= kwarg when settings provided."""
        import pydantic_ai
        fake_settings = MagicMock(name="FakeInstrumentationSettings")

        mock_agent_instance = MagicMock()
        mock_agent_instance.output_validator = MagicMock()
        mock_agent_instance.instructions = MagicMock()

        with patch.object(pydantic_ai, "Agent") as MockAgent:
            MockAgent.return_value = mock_agent_instance
            from llm_pipeline.agent_builders import build_step_agent
            build_step_agent(
                step_name="token",
                output_type=TokenInstructions,
                instrument=fake_settings,
            )

        agent_call_kwargs = MockAgent.call_args[1]
        assert agent_call_kwargs["instrument"] is fake_settings

    def test_agent_constructor_no_instrument_when_none(self, token_engine, token_session):
        """Agent() constructor does NOT receive instrument= when settings is None."""
        import pydantic_ai

        mock_agent_instance = MagicMock()
        mock_agent_instance.output_validator = MagicMock()
        mock_agent_instance.instructions = MagicMock()

        with patch.object(pydantic_ai, "Agent") as MockAgent:
            MockAgent.return_value = mock_agent_instance
            from llm_pipeline.agent_builders import build_step_agent
            build_step_agent(
                step_name="token",
                output_type=TokenInstructions,
                instrument=None,
            )

        agent_call_kwargs = MockAgent.call_args[1]
        assert "instrument" not in agent_call_kwargs

    def test_instrumentation_settings_stored_on_pipeline(self, token_engine, token_session):
        """PipelineConfig stores instrumentation_settings internally."""
        fake_settings = MagicMock()
        pipeline = TokenPipeline(
            session=token_session, model="test-model",
            instrumentation_settings=fake_settings,
        )
        assert pipeline._instrumentation_settings is fake_settings

    def test_no_instrumentation_stores_none(self, token_engine, token_session):
        """PipelineConfig stores None when no instrumentation_settings passed."""
        pipeline = TokenPipeline(
            session=token_session, model="test-model",
        )
        assert pipeline._instrumentation_settings is None
