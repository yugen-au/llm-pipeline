"""Integration tests for extraction event emissions.

Verifies ExtractionStarting, ExtractionCompleted, and ExtractionError events
emitted by LLMStep.extract_data() via InMemoryEventHandler. Tests use
ExtractionPipeline with ItemDetectionStep + ItemExtraction from conftest.
"""
import pytest
from unittest.mock import patch, MagicMock
from pydantic import ValidationError

from llm_pipeline.events.types import (
    ExtractionStarting,
    ExtractionCompleted,
    ExtractionError,
)
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.step import step_definition, LLMStep, LLMResultMixin
from llm_pipeline import PipelineConfig, PipelineStrategy, PipelineStrategies, PipelineDatabaseRegistry
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.types import StepCallParams
from conftest import (
    ExtractionPipeline,
    Item,
    ItemDetectionInstructions,
    ItemDetectionContext,
    make_item_detection_run_result,
)
from typing import List, ClassVar


# -- Helpers -------------------------------------------------------------------


def _run_extraction_pipeline(seeded_session, handler):
    """Execute ExtractionPipeline with ItemDetectionStep."""
    pipeline = ExtractionPipeline(
        session=seeded_session,
        model="test-model",
        event_emitter=handler,
    )
    with patch("pydantic_ai.Agent.run_sync", return_value=make_item_detection_run_result(item_count=2, category="test")):
        pipeline.execute(data="test data", initial_context={})
    return pipeline, handler.get_events()


def _extraction_events(events):
    """Filter only extraction-related events from full event stream."""
    extraction_types = {
        "extraction_starting",
        "extraction_completed",
        "extraction_error",
    }
    return [e for e in events if e["event_type"] in extraction_types]


# -- Tests: ExtractionStarting -------------------------------------------------


class TestExtractionStarting:
    """Verify ExtractionStarting emitted when extraction begins."""

    def test_extraction_starting_fires(self, seeded_session, in_memory_handler):
        """ExtractionStarting emitted before extraction.extract()."""
        _, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "extraction_starting"]
        assert len(starting) == 1, "Expected 1 ExtractionStarting"

    def test_extraction_starting_fields(self, seeded_session, in_memory_handler):
        """ExtractionStarting has extraction_class, model_class, step_name, timestamp."""
        pipeline, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "extraction_starting"][0]

        assert starting["extraction_class"] == "ItemExtraction"
        assert starting["model_class"] == "Item"
        assert starting["step_name"] == "item_detection"
        assert "timestamp" in starting
        assert isinstance(starting["timestamp"], str)
        assert starting["run_id"] == pipeline.run_id
        assert starting["pipeline_name"] == pipeline.pipeline_name


# -- Tests: ExtractionCompleted ------------------------------------------------


class TestExtractionCompleted:
    """Verify ExtractionCompleted emitted when extraction succeeds."""

    def test_extraction_completed_fires(self, seeded_session, in_memory_handler):
        """ExtractionCompleted emitted after extraction.extract() + flush."""
        _, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "extraction_completed"]
        assert len(completed) == 1, "Expected 1 ExtractionCompleted"

    def test_extraction_completed_fields(self, seeded_session, in_memory_handler):
        """ExtractionCompleted has extraction_class, model_class, instance_count, execution_time_ms."""
        pipeline, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "extraction_completed"][0]

        assert completed["extraction_class"] == "ItemExtraction"
        assert completed["model_class"] == "Item"
        assert completed["instance_count"] == 2, "ItemExtraction creates 2 items"
        assert completed["execution_time_ms"] > 0, "Execution time should be positive"
        assert isinstance(completed["execution_time_ms"], (int, float))
        assert completed["step_name"] == "item_detection"
        assert "timestamp" in completed
        assert completed["run_id"] == pipeline.run_id
        assert completed["pipeline_name"] == pipeline.pipeline_name

    def test_extraction_completed_after_starting(self, seeded_session, in_memory_handler):
        """ExtractionCompleted fires after ExtractionStarting."""
        _, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        ee = _extraction_events(events)
        types = [e["event_type"] for e in ee]

        starting_idx = types.index("extraction_starting")
        completed_idx = types.index("extraction_completed")
        assert starting_idx < completed_idx, "ExtractionStarting must precede ExtractionCompleted"


# -- Tests: ExtractionError ----------------------------------------------------


class FailingItemDetectionInstructions(LLMResultMixin):
    """Instruction model for failing extraction step."""
    item_count: int
    category: str

    example: ClassVar[dict] = {"item_count": 2, "category": "test", "notes": "ok"}


class FailingItemDetectionContext(ItemDetectionContext):
    """Context for failing extraction step (inherits from ItemDetectionContext)."""
    pass


class FailingItemExtraction(PipelineExtraction, model=Item):
    """Extraction that raises ValidationError during extract()."""
    def extract(self, results: List[FailingItemDetectionInstructions]) -> List[Item]:
        """Raise ValidationError to trigger ExtractionError event."""
        from pydantic import BaseModel, Field

        class StrictItem(BaseModel):
            name: str = Field(min_length=5)  # Enforce minimum length
            value: int = Field(gt=0)  # Must be positive

        # This will raise ValidationError: name too short
        StrictItem(name="x", value=-1)
        return []  # Never reached


@step_definition(
    instructions=FailingItemDetectionInstructions,
    default_system_key="item_detection.system",
    default_user_key="item_detection.user",
    default_extractions=[FailingItemExtraction],
    context=FailingItemDetectionContext,
)
class FailingItemDetectionStep(LLMStep):
    """Step with failing extraction for error event tests."""
    def prepare_calls(self) -> List[StepCallParams]:
        return [{"variables": {"data": "test"}}]

    def process_instructions(self, instructions):
        return FailingItemDetectionContext(category=instructions[0].category)


class FailingExtractionStrategy(PipelineStrategy):
    """Strategy with failing extraction step."""
    def can_handle(self, context):
        return True

    def get_steps(self):
        return [FailingItemDetectionStep.create_definition()]


class FailingExtractionRegistry(PipelineDatabaseRegistry, models=[Item]):
    pass


class FailingExtractionAgentRegistry(AgentRegistry, agents={
    "failing_item_detection": FailingItemDetectionInstructions,
}):
    pass


class FailingExtractionStrategies(PipelineStrategies, strategies=[FailingExtractionStrategy]):
    pass


class FailingExtractionPipeline(
    PipelineConfig,
    registry=FailingExtractionRegistry,
    strategies=FailingExtractionStrategies,
    agent_registry=FailingExtractionAgentRegistry,
):
    pass


def _make_failing_run_result(item_count=2, category="test"):
    """Build MagicMock for FailingItemDetectionInstructions."""
    instruction = FailingItemDetectionInstructions(
        item_count=item_count, category=category, confidence_score=1.0, notes="ok"
    )
    mock_result = MagicMock()
    mock_result.output = instruction
    return mock_result


class TestExtractionError:
    """Verify ExtractionError emitted when extraction fails."""

    def test_extraction_error_fires(self, seeded_session, in_memory_handler):
        """ExtractionError emitted when extraction raises exception."""
        pipeline = FailingExtractionPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )

        with pytest.raises(ValidationError):
            with patch("pydantic_ai.Agent.run_sync", return_value=_make_failing_run_result()):
                pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        errors = [e for e in events if e["event_type"] == "extraction_error"]
        assert len(errors) == 1, "Expected 1 ExtractionError"

    def test_extraction_error_fields(self, seeded_session, in_memory_handler):
        """ExtractionError has extraction_class, error_type, error_message, validation_errors."""
        pipeline = FailingExtractionPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )

        with pytest.raises(ValidationError):
            with patch("pydantic_ai.Agent.run_sync", return_value=_make_failing_run_result()):
                pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        error = [e for e in events if e["event_type"] == "extraction_error"][0]

        assert error["extraction_class"] == "FailingItemExtraction"
        assert error["error_type"] == "ValidationError"
        assert error["error_message"] != "", "Error message should be populated"
        assert isinstance(error["validation_errors"], list)
        assert len(error["validation_errors"]) > 0, "validation_errors should be populated for ValidationError"
        assert all(isinstance(e, str) for e in error["validation_errors"]), "validation_errors elements must be strings"
        assert "timestamp" in error
        assert error["step_name"] == "failing_item_detection"
        assert error["run_id"] == pipeline.run_id
        assert error["pipeline_name"] == pipeline.pipeline_name

    def test_extraction_error_after_starting(self, seeded_session, in_memory_handler):
        """ExtractionError fires after ExtractionStarting, no ExtractionCompleted."""
        pipeline = FailingExtractionPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )

        with pytest.raises(ValidationError):
            with patch("pydantic_ai.Agent.run_sync", return_value=_make_failing_run_result()):
                pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        ee = _extraction_events(events)
        types = [e["event_type"] for e in ee]

        assert "extraction_starting" in types
        assert "extraction_error" in types
        assert "extraction_completed" not in types, "ExtractionCompleted should not fire on error"

        starting_idx = types.index("extraction_starting")
        error_idx = types.index("extraction_error")
        assert starting_idx < error_idx, "ExtractionStarting must precede ExtractionError"


# -- Tests: Event Ordering -----------------------------------------------------


class TestExtractionEventOrdering:
    """Verify ExtractionStarting -> ExtractionCompleted ordering."""

    def test_full_sequence_success(self, seeded_session, in_memory_handler):
        """Full success sequence: ExtractionStarting -> ExtractionCompleted."""
        _, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        ee = _extraction_events(events)
        types = [e["event_type"] for e in ee]

        assert types == [
            "extraction_starting",
            "extraction_completed",
        ]


# -- Tests: Zero Overhead (No Emitter) -----------------------------------------


class TestExtractionZeroOverhead:
    """Verify no crash when event_emitter=None."""

    def test_no_events_without_emitter(self, seeded_session):
        """Pipeline with extractions but no event_emitter runs without error."""
        pipeline = ExtractionPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=None,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_item_detection_run_result(item_count=2, category="test")):
            result = pipeline.execute(data="test data", initial_context={})
        assert result is not None
        assert "category" in result.context


# -- Tests: Event Fields -------------------------------------------------------


class TestExtractionEventFields:
    """Verify run_id, pipeline_name, step_name, timestamp populated correctly."""

    def test_run_id_consistent_across_extraction_events(self, seeded_session, in_memory_handler):
        """All extraction events share the same run_id."""
        pipeline, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        ee = _extraction_events(events)
        for e in ee:
            assert e["run_id"] == pipeline.run_id

    def test_pipeline_name_consistent(self, seeded_session, in_memory_handler):
        """All extraction events have the same pipeline_name."""
        pipeline, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        ee = _extraction_events(events)
        for e in ee:
            assert e["pipeline_name"] == pipeline.pipeline_name

    def test_step_name_consistent(self, seeded_session, in_memory_handler):
        """All extraction events have step_name='item_detection'."""
        _, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        ee = _extraction_events(events)
        for e in ee:
            assert e["step_name"] == "item_detection"
