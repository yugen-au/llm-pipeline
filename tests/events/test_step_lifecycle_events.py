"""Integration tests for step lifecycle event emissions.

Verifies StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
events emitted by Pipeline.execute() via InMemoryEventHandler.
"""
import pytest
from unittest.mock import patch

from llm_pipeline.events.types import (
    StepSelecting,
    StepSelected,
    StepSkipped,
    StepStarted,
    StepCompleted,
)
from conftest import (
    SuccessPipeline,
    SkipPipeline,
    make_simple_run_result,
)


# -- Tests ---------------------------------------------------------------------


class TestStepSelecting:
    """Verify StepSelecting event emitted before step selection."""

    def test_step_selecting_emitted(self, seeded_session, in_memory_handler):
        """Execute pipeline, verify StepSelecting emitted for each step index."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=1)):
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
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=1)):
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
        pipeline = SkipPipeline(
            session=seeded_session,
            model="test-model",
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
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=1)):
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
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=2)):
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
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=None,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=2)):
            result = pipeline.execute(data="test data", initial_context={})

        # Verify execution succeeded
        assert result is not None
        assert result.context["total"] == 2  # from mocked count=2
        # _executed_steps is a set of step CLASSES - 2 SimpleStep instances = 1 unique class
        assert len(result._executed_steps) == 1


class TestStepLifecycleOrdering:
    """Verify correct event ordering for step lifecycle events."""

    def test_non_skipped_step_ordering(self, seeded_session, in_memory_handler):
        """Verify event order: StepSelecting -> StepSelected -> StepStarted -> StepCompleted."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=1)):
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
        pipeline = SkipPipeline(
            session=seeded_session,
            model="test-model",
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
