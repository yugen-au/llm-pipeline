"""Integration tests for pipeline lifecycle event emissions.

Verifies PipelineStarted, PipelineCompleted, and PipelineError events emitted by
Pipeline.execute() via InMemoryEventHandler.
"""
import pytest
from sqlmodel import SQLModel, Session, create_engine
from typing import Any, Dict, List, Optional, Type, ClassVar

from llm_pipeline import (
    PipelineConfig,
    LLMStep,
    LLMResultMixin,
    step_definition,
    PipelineStrategy,
    PipelineStrategies,
    PipelineDatabaseRegistry,
    PipelineContext,
)
from llm_pipeline.llm.provider import LLMProvider
from llm_pipeline.llm.result import LLMCallResult
from llm_pipeline.prompts.service import PromptService
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.types import StepCallParams
from llm_pipeline.events.handlers import InMemoryEventHandler
from llm_pipeline.events.types import PipelineStarted, PipelineCompleted, PipelineError


# -- Mock Provider -------------------------------------------------------------


class MockProvider(LLMProvider):
    """Mock LLM provider that returns predefined responses."""

    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None, should_fail: bool = False):
        self._responses = responses or []
        self._call_count = 0
        self._should_fail = should_fail

    def call_structured(self, prompt, system_instruction, result_class, **kwargs):
        if self._should_fail:
            raise ValueError("Mock provider failure")
        if self._call_count < len(self._responses):
            response = self._responses[self._call_count]
            self._call_count += 1
            return LLMCallResult.success(
                parsed=response,
                raw_response="mock response",
                model_name="mock-model",
                attempt_count=1,
            )
        return LLMCallResult(
            parsed=None,
            raw_response="",
            model_name="mock-model",
            attempt_count=1,
            validation_errors=[],
        )


# -- Test Domain ---------------------------------------------------------------


class SimpleInstructions(LLMResultMixin):
    """Minimal instruction model for test pipeline."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


class SimpleContext(PipelineContext):
    """Minimal context for test pipeline."""
    total: int


# -- Test Steps ----------------------------------------------------------------


@step_definition(
    instructions=SimpleInstructions,
    default_system_key="simple.system",
    default_user_key="simple.user",
    context=SimpleContext,
)
class SimpleStep(LLMStep):
    """Step that succeeds."""
    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={"data": "test"})]

    def process_instructions(self, instructions):
        return SimpleContext(total=instructions[0].count)


class FailingInstructions(LLMResultMixin):
    """Instruction model for failing step."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


@step_definition(
    instructions=FailingInstructions,
    default_system_key="failing.system",
    default_user_key="failing.user",
)
class FailingStep(LLMStep):
    """Step that raises ValueError during execution."""
    def prepare_calls(self) -> List[StepCallParams]:
        raise ValueError("Intentional test failure")


# -- Test Strategies -----------------------------------------------------------


class SuccessStrategy(PipelineStrategy):
    """Strategy with 2 successful steps."""
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [
            SimpleStep.create_definition(),
            SimpleStep.create_definition(),
        ]


class FailureStrategy(PipelineStrategy):
    """Strategy with failing step."""
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [FailingStep.create_definition()]


# -- Test Pipelines ------------------------------------------------------------


class SuccessRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class FailureRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class SuccessStrategies(PipelineStrategies, strategies=[SuccessStrategy]):
    pass


class FailureStrategies(PipelineStrategies, strategies=[FailureStrategy]):
    pass


class SuccessPipeline(PipelineConfig, registry=SuccessRegistry, strategies=SuccessStrategies):
    pass


class FailurePipeline(PipelineConfig, registry=FailureRegistry, strategies=FailureStrategies):
    pass


# -- Fixtures ------------------------------------------------------------------


@pytest.fixture
def engine():
    """In-memory SQLite engine with tables."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    SQLModel.metadata.create_all(eng)
    return eng


@pytest.fixture
def seeded_session(engine):
    """Session with prompts for test steps."""
    with Session(engine) as session:
        session.add(Prompt(
            prompt_key="simple.system",
            prompt_name="Simple System",
            prompt_type="system",
            category="test",
            step_name="simple",
            content="You are a test assistant.",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="simple.user",
            prompt_name="Simple User",
            prompt_type="user",
            category="test",
            step_name="simple",
            content="Process: {data}",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="failing.system",
            prompt_name="Failing System",
            prompt_type="system",
            category="test",
            step_name="failing",
            content="You are a test assistant.",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="failing.user",
            prompt_name="Failing User",
            prompt_type="user",
            category="test",
            step_name="failing",
            content="Process: {data}",
            version="1.0",
        ))
        session.commit()

    # Return a new session for test use
    return Session(engine)


@pytest.fixture
def in_memory_handler():
    """Fresh InMemoryEventHandler for each test."""
    return InMemoryEventHandler()


# -- Tests ---------------------------------------------------------------------


class TestPipelineLifecycleSuccess:
    """Verify PipelineStarted and PipelineCompleted emitted on successful execution."""

    def test_pipeline_lifecycle_success(self, seeded_session, in_memory_handler):
        """Execute successful pipeline, verify PipelineStarted + PipelineCompleted emitted."""
        mock_provider = MockProvider(responses=[
            {"count": 1, "notes": "first"},
            {"count": 2, "notes": "second"},
        ])

        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=mock_provider,
            event_emitter=in_memory_handler,
        )
        pipeline.execute(data="test data", initial_context={})

        # Verify event sequence
        events = in_memory_handler.get_events()
        assert len(events) >= 2, "Expected at least PipelineStarted + PipelineCompleted"

        # First event: PipelineStarted
        started_events = [e for e in events if e["event_type"] == "pipeline_started"]
        assert len(started_events) == 1, "Expected exactly 1 PipelineStarted event"
        started = started_events[0]
        assert started["pipeline_name"] == "success"  # snake_case derived from class name
        assert "run_id" in started
        assert "timestamp" in started

        # Last event: PipelineCompleted
        completed_events = [e for e in events if e["event_type"] == "pipeline_completed"]
        assert len(completed_events) == 1, "Expected exactly 1 PipelineCompleted event"
        completed = completed_events[0]
        assert completed["pipeline_name"] == "success"
        assert completed["run_id"] == started["run_id"]
        assert "execution_time_ms" in completed
        assert isinstance(completed["execution_time_ms"], (int, float))
        assert completed["execution_time_ms"] > 0
        assert "steps_executed" in completed
        # _executed_steps is a set of step CLASSES, not instances - 2 SimpleStep instances = 1 unique class
        assert completed["steps_executed"] == 1, "Expected 1 unique step class executed"

        # No PipelineError emitted
        error_events = [e for e in events if e["event_type"] == "pipeline_error"]
        assert len(error_events) == 0, "No PipelineError should be emitted on success"


class TestPipelineLifecycleError:
    """Verify PipelineStarted and PipelineError emitted on pipeline failure."""

    def test_pipeline_lifecycle_error(self, seeded_session, in_memory_handler):
        """Execute failing pipeline, verify PipelineStarted + PipelineError emitted."""
        mock_provider = MockProvider()

        pipeline = FailurePipeline(
            session=seeded_session,
            provider=mock_provider,
            event_emitter=in_memory_handler,
        )

        with pytest.raises(ValueError, match="Intentional test failure"):
            pipeline.execute(data="test data", initial_context={})

        # Verify event sequence
        events = in_memory_handler.get_events()
        assert len(events) >= 2, "Expected at least PipelineStarted + PipelineError"

        # First event: PipelineStarted
        started_events = [e for e in events if e["event_type"] == "pipeline_started"]
        assert len(started_events) == 1, "Expected exactly 1 PipelineStarted event"
        started = started_events[0]
        assert started["pipeline_name"] == "failure"  # snake_case derived from class name
        assert "run_id" in started

        # PipelineError emitted
        error_events = [e for e in events if e["event_type"] == "pipeline_error"]
        assert len(error_events) == 1, "Expected exactly 1 PipelineError event"
        error = error_events[0]
        assert error["pipeline_name"] == "failure"
        assert error["run_id"] == started["run_id"]
        assert error["error_type"] == "ValueError"
        assert "Intentional test failure" in error["error_message"]
        assert error["traceback"] is not None
        assert isinstance(error["traceback"], str)
        assert len(error["traceback"]) > 0
        assert "step_name" in error
        assert error["step_name"] == "failing", "step_name should be 'failing' for FailingStep"

        # PipelineCompleted NOT emitted
        completed_events = [e for e in events if e["event_type"] == "pipeline_completed"]
        assert len(completed_events) == 0, "PipelineCompleted should NOT be emitted on error"


class TestPipelineLifecycleNoEmitter:
    """Verify pipeline executes successfully without event_emitter (zero overhead)."""

    def test_pipeline_lifecycle_no_emitter(self, seeded_session):
        """Execute pipeline without event_emitter, verify no events and successful run."""
        mock_provider = MockProvider(responses=[
            {"count": 1, "notes": "first"},
            {"count": 2, "notes": "second"},
        ])

        # Create pipeline WITHOUT event_emitter
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=mock_provider,
            event_emitter=None,
        )
        result = pipeline.execute(data="test data", initial_context={})

        # Verify execution succeeded
        assert result is not None
        assert result.context["total"] == 2  # from second step
        # _executed_steps is a set of step CLASSES - 2 SimpleStep instances = 1 unique class
        assert len(result._executed_steps) == 1

        # No way to verify zero events without handler, but execution proves zero-overhead path works
