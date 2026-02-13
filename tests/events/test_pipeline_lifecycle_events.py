"""Integration tests for pipeline lifecycle event emissions.

Verifies PipelineStarted, PipelineCompleted, and PipelineError events emitted by
Pipeline.execute() via InMemoryEventHandler.
"""
import pytest

from llm_pipeline.events.types import PipelineStarted, PipelineCompleted, PipelineError
from conftest import (
    MockProvider,
    SuccessPipeline,
    FailurePipeline,
)


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
