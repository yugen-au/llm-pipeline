"""Integration tests for step lifecycle event emissions.

Verifies StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
events emitted by Pipeline.execute() via InMemoryEventHandler.
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
from llm_pipeline.events.types import (
    StepSelecting,
    StepSelected,
    StepSkipped,
    StepStarted,
    StepCompleted,
)


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


class SkippableInstructions(LLMResultMixin):
    """Instruction model for skippable step."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


class SkippableContext(PipelineContext):
    """Minimal context for skippable step."""
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


@step_definition(
    instructions=SkippableInstructions,
    default_system_key="skippable.system",
    default_user_key="skippable.user",
    context=SkippableContext,
)
class SkippableStep(LLMStep):
    """Step that is skipped (should_skip returns True)."""
    def should_skip(self) -> bool:
        return True

    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={"data": "test"})]

    def process_instructions(self, instructions):
        return SkippableContext(total=instructions[0].count)


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


class SkipStrategy(PipelineStrategy):
    """Strategy with skippable step."""
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [SkippableStep.create_definition()]


# -- Test Pipelines ------------------------------------------------------------


class SuccessRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class SkipRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class SuccessStrategies(PipelineStrategies, strategies=[SuccessStrategy]):
    pass


class SkipStrategies(PipelineStrategies, strategies=[SkipStrategy]):
    pass


class SuccessPipeline(PipelineConfig, registry=SuccessRegistry, strategies=SuccessStrategies):
    pass


class SkipPipeline(PipelineConfig, registry=SkipRegistry, strategies=SkipStrategies):
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
            prompt_key="skippable.system",
            prompt_name="Skippable System",
            prompt_type="system",
            category="test",
            step_name="skippable",
            content="You are a test assistant.",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key="skippable.user",
            prompt_name="Skippable User",
            prompt_type="user",
            category="test",
            step_name="skippable",
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


class TestStepSelecting:
    """Verify StepSelecting event emitted before step selection."""

    def test_step_selecting_emitted(self, seeded_session, in_memory_handler):
        """Execute pipeline, verify StepSelecting emitted for each step index."""
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

        events = in_memory_handler.get_events()
        selecting_events = [e for e in events if e["event_type"] == "step_selecting"]

        # 2 SimpleStep instances in SuccessStrategy
        assert len(selecting_events) == 2, "Expected 2 StepSelecting events"

        # First StepSelecting
        first_selecting = selecting_events[0]
        assert first_selecting["step_index"] == 0
        assert first_selecting["strategy_count"] == 1  # 1 strategy in SuccessStrategies
        assert first_selecting["step_name"] is None  # step_name not yet known
        assert "run_id" in first_selecting
        assert "timestamp" in first_selecting

        # Second StepSelecting
        second_selecting = selecting_events[1]
        assert second_selecting["step_index"] == 1
        assert second_selecting["strategy_count"] == 1


class TestStepSelected:
    """Verify StepSelected event emitted after step selection."""

    def test_step_selected_emitted(self, seeded_session, in_memory_handler):
        """Execute pipeline, verify StepSelected emitted with correct fields."""
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

        events = in_memory_handler.get_events()
        selected_events = [e for e in events if e["event_type"] == "step_selected"]

        assert len(selected_events) == 2, "Expected 2 StepSelected events"

        # First StepSelected
        first_selected = selected_events[0]
        assert first_selected["step_name"] == "simple"
        assert first_selected["step_number"] == 1
        assert first_selected["strategy_name"] == "success"  # snake_case from SuccessStrategy
        assert "run_id" in first_selected

        # Second StepSelected
        second_selected = selected_events[1]
        assert second_selected["step_name"] == "simple"
        assert second_selected["step_number"] == 2
        assert second_selected["strategy_name"] == "success"


class TestStepSkipped:
    """Verify StepSkipped event emitted when should_skip returns True."""

    def test_step_skipped_emitted(self, seeded_session, in_memory_handler):
        """Execute pipeline with skippable step, verify StepSkipped emitted."""
        mock_provider = MockProvider(responses=[])

        pipeline = SkipPipeline(
            session=seeded_session,
            provider=mock_provider,
            event_emitter=in_memory_handler,
        )
        pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        skipped_events = [e for e in events if e["event_type"] == "step_skipped"]

        assert len(skipped_events) == 1, "Expected 1 StepSkipped event"

        skipped = skipped_events[0]
        assert skipped["step_name"] == "skippable"
        assert skipped["step_number"] == 1
        assert skipped["reason"] == "should_skip returned True"
        assert "run_id" in skipped

        # StepStarted and StepCompleted should NOT be emitted for skipped steps
        started_events = [e for e in events if e["event_type"] == "step_started"]
        completed_events = [e for e in events if e["event_type"] == "step_completed"]
        assert len(started_events) == 0, "StepStarted should not be emitted for skipped step"
        assert len(completed_events) == 0, "StepCompleted should not be emitted for skipped step"


class TestStepStarted:
    """Verify StepStarted event emitted before step execution."""

    def test_step_started_emitted(self, seeded_session, in_memory_handler):
        """Execute pipeline, verify StepStarted emitted with system_key and user_key."""
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

        events = in_memory_handler.get_events()
        started_events = [e for e in events if e["event_type"] == "step_started"]

        assert len(started_events) == 2, "Expected 2 StepStarted events"

        # First StepStarted
        first_started = started_events[0]
        assert first_started["step_name"] == "simple"
        assert first_started["step_number"] == 1
        assert first_started["system_key"] == "simple.system"
        assert first_started["user_key"] == "simple.user"
        assert "run_id" in first_started

        # Second StepStarted
        second_started = started_events[1]
        assert second_started["step_name"] == "simple"
        assert second_started["step_number"] == 2
        assert second_started["system_key"] == "simple.system"
        assert second_started["user_key"] == "simple.user"


class TestStepCompleted:
    """Verify StepCompleted event emitted after step execution."""

    def test_step_completed_emitted(self, seeded_session, in_memory_handler):
        """Execute pipeline, verify StepCompleted emitted with execution_time_ms."""
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

        events = in_memory_handler.get_events()
        completed_events = [e for e in events if e["event_type"] == "step_completed"]

        assert len(completed_events) == 2, "Expected 2 StepCompleted events"

        # First StepCompleted
        first_completed = completed_events[0]
        assert first_completed["step_name"] == "simple"
        assert first_completed["step_number"] == 1
        assert "execution_time_ms" in first_completed
        assert isinstance(first_completed["execution_time_ms"], (int, float))
        assert first_completed["execution_time_ms"] >= 0
        assert "run_id" in first_completed

        # Second StepCompleted
        second_completed = completed_events[1]
        assert second_completed["step_name"] == "simple"
        assert second_completed["step_number"] == 2
        assert isinstance(second_completed["execution_time_ms"], (int, float))
        assert second_completed["execution_time_ms"] >= 0


class TestStepLifecycleNoEmitter:
    """Verify pipeline executes successfully without event_emitter (zero overhead)."""

    def test_step_lifecycle_no_emitter(self, seeded_session):
        """Execute pipeline without event_emitter, verify successful run."""
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


class TestStepLifecycleOrdering:
    """Verify correct event ordering for step lifecycle events."""

    def test_non_skipped_step_ordering(self, seeded_session, in_memory_handler):
        """Verify event order: StepSelecting -> StepSelected -> StepStarted -> StepCompleted."""
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

        events = in_memory_handler.get_events()

        # Extract step lifecycle events for first step
        step_events = [
            e for e in events
            if e["event_type"] in ["step_selecting", "step_selected", "step_started", "step_completed"]
            and (e.get("step_number") == 1 or e.get("step_index") == 0)
        ]

        # Verify order
        assert len(step_events) >= 4, "Expected at least 4 step lifecycle events"
        assert step_events[0]["event_type"] == "step_selecting"
        assert step_events[1]["event_type"] == "step_selected"
        assert step_events[2]["event_type"] == "step_started"
        assert step_events[3]["event_type"] == "step_completed"

    def test_skipped_step_ordering(self, seeded_session, in_memory_handler):
        """Verify event order for skipped step: StepSelecting -> StepSelected -> StepSkipped."""
        mock_provider = MockProvider(responses=[])

        pipeline = SkipPipeline(
            session=seeded_session,
            provider=mock_provider,
            event_emitter=in_memory_handler,
        )
        pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()

        # Extract step lifecycle events
        step_events = [
            e for e in events
            if e["event_type"] in ["step_selecting", "step_selected", "step_skipped", "step_started", "step_completed"]
        ]

        # Verify order
        assert len(step_events) >= 3, "Expected at least 3 step lifecycle events"
        assert step_events[0]["event_type"] == "step_selecting"
        assert step_events[1]["event_type"] == "step_selected"
        assert step_events[2]["event_type"] == "step_skipped"

        # Verify StepStarted and StepCompleted are NOT emitted
        started_count = sum(1 for e in step_events if e["event_type"] == "step_started")
        completed_count = sum(1 for e in step_events if e["event_type"] == "step_completed")
        assert started_count == 0, "StepStarted should not be emitted for skipped step"
        assert completed_count == 0, "StepCompleted should not be emitted for skipped step"
