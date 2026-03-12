"""Integration tests for transformation event emissions.

Verifies TransformationStarting and TransformationCompleted events emitted
by Pipeline.execute() via InMemoryEventHandler, covering both fresh (cache miss)
and cached (cache hit) code paths.
"""
import pytest
from unittest.mock import patch

from llm_pipeline.events.types import TransformationStarting, TransformationCompleted
from conftest import TransformationPipeline, make_transformation_run_result


# -- Helpers -------------------------------------------------------------------


def _run_transformation_fresh(seeded_session, handler):
    """Execute TransformationPipeline on fresh DB (cache miss path).

    Returns (pipeline, events).
    """
    pipeline = TransformationPipeline(
        session=seeded_session,
        model="test-model",
        event_emitter=handler,
    )
    with patch("pydantic_ai.Agent.run_sync", return_value=make_transformation_run_result(count=5, operation="transform")):
        pipeline.execute(data={"input_key": "input_value"}, initial_context={}, use_cache=False)
    return pipeline, handler.get_events()


def _run_transformation_cached(seeded_session, handler):
    """Execute TransformationPipeline twice: run 1 populates cache, run 2 hits cache.

    Returns (pipeline2, events2) from the second run only.
    """
    # Run 1: cache miss, saves state
    pipeline1 = TransformationPipeline(
        session=seeded_session,
        model="test-model",
        event_emitter=handler,
    )
    with patch("pydantic_ai.Agent.run_sync", return_value=make_transformation_run_result(count=5, operation="transform")):
        pipeline1.execute(data={"input_key": "input_value"}, initial_context={}, use_cache=True)

    # Clear events from first run
    handler.clear()

    # Run 2: cache hit path
    pipeline2 = TransformationPipeline(
        session=seeded_session,
        model="test-model",
        event_emitter=handler,
    )
    with patch("pydantic_ai.Agent.run_sync", return_value=make_transformation_run_result(count=5, operation="transform")):
        pipeline2.execute(data={"input_key": "input_value"}, initial_context={}, use_cache=True)
    return pipeline2, handler.get_events()


def _transformation_events(events):
    """Filter only transformation-related events from full event stream."""
    transformation_types = {
        "transformation_starting",
        "transformation_completed",
    }
    return [e for e in events if e["event_type"] in transformation_types]


# -- Tests: TransformationStarting (Fresh Path) --------------------------------


class TestTransformationStartingFreshPath:
    """Verify TransformationStarting emitted on fresh (cache miss) path."""

    def test_starting_emitted_fresh(self, seeded_session, in_memory_handler):
        """TransformationStarting emitted on fresh run (cached=False)."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"]
        assert len(starting) == 1, "Expected 1 TransformationStarting on fresh run"

    def test_starting_transformation_class(self, seeded_session, in_memory_handler):
        """transformation_class is 'TransformationTransformation'."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["transformation_class"] == "TransformationTransformation", (
            f"Expected 'TransformationTransformation', got '{starting['transformation_class']}'"
        )

    def test_starting_cached_false(self, seeded_session, in_memory_handler):
        """cached=False on fresh path."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["cached"] is False, "Expected cached=False on fresh path"

    def test_starting_step_name(self, seeded_session, in_memory_handler):
        """step_name is 'transformation' for TransformationStep."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["step_name"] == "transformation"

    def test_starting_has_run_id(self, seeded_session, in_memory_handler):
        """TransformationStarting carries run_id from pipeline."""
        pipeline, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["run_id"] == pipeline.run_id

    def test_starting_has_pipeline_name(self, seeded_session, in_memory_handler):
        """TransformationStarting carries pipeline_name."""
        pipeline, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["pipeline_name"] == pipeline.pipeline_name

    def test_starting_has_timestamp(self, seeded_session, in_memory_handler):
        """timestamp is present and valid ISO string."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert "timestamp" in starting
        assert isinstance(starting["timestamp"], str)
        from datetime import datetime
        parsed = datetime.fromisoformat(starting["timestamp"])
        assert parsed is not None


# -- Tests: TransformationCompleted (Fresh Path) -------------------------------


class TestTransformationCompletedFreshPath:
    """Verify TransformationCompleted emitted on fresh (cache miss) path."""

    def test_completed_emitted_fresh(self, seeded_session, in_memory_handler):
        """TransformationCompleted emitted on fresh run (cached=False)."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"]
        assert len(completed) == 1, "Expected 1 TransformationCompleted on fresh run"

    def test_completed_data_key_equals_step_name(self, seeded_session, in_memory_handler):
        """data_key equals step_name ('transformation')."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["data_key"] == "transformation"
        assert completed["step_name"] == "transformation"
        assert completed["data_key"] == completed["step_name"]

    def test_completed_execution_time_positive(self, seeded_session, in_memory_handler):
        """execution_time_ms > 0 on fresh path."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["execution_time_ms"] > 0, (
            f"Expected execution_time_ms > 0, got {completed['execution_time_ms']}"
        )

    def test_completed_cached_false(self, seeded_session, in_memory_handler):
        """cached=False on fresh path."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["cached"] is False, "Expected cached=False on fresh path"

    def test_completed_has_run_id(self, seeded_session, in_memory_handler):
        """TransformationCompleted carries run_id from pipeline."""
        pipeline, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["run_id"] == pipeline.run_id

    def test_completed_has_pipeline_name(self, seeded_session, in_memory_handler):
        """TransformationCompleted carries pipeline_name."""
        pipeline, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["pipeline_name"] == pipeline.pipeline_name

    def test_completed_has_timestamp(self, seeded_session, in_memory_handler):
        """timestamp is present and valid ISO string."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert "timestamp" in completed
        assert isinstance(completed["timestamp"], str)
        from datetime import datetime
        parsed = datetime.fromisoformat(completed["timestamp"])
        assert parsed is not None


# -- Tests: TransformationStarting (Cached Path) -------------------------------


class TestTransformationStartingCachedPath:
    """Verify TransformationStarting emitted on cached (cache hit) path."""

    def test_starting_emitted_cached(self, seeded_session, in_memory_handler):
        """TransformationStarting emitted on second run (cached=True)."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"]
        assert len(starting) == 1, "Expected 1 TransformationStarting on cached run"

    def test_starting_cached_true(self, seeded_session, in_memory_handler):
        """cached=True on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["cached"] is True, "Expected cached=True on cached path"

    def test_starting_transformation_class_cached(self, seeded_session, in_memory_handler):
        """transformation_class is 'TransformationTransformation' on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["transformation_class"] == "TransformationTransformation"

    def test_starting_step_name_cached(self, seeded_session, in_memory_handler):
        """step_name is 'transformation' on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["step_name"] == "transformation"


# -- Tests: TransformationCompleted (Cached Path) ------------------------------


class TestTransformationCompletedCachedPath:
    """Verify TransformationCompleted emitted on cached (cache hit) path."""

    def test_completed_emitted_cached(self, seeded_session, in_memory_handler):
        """TransformationCompleted emitted on second run (cached=True)."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"]
        assert len(completed) == 1, "Expected 1 TransformationCompleted on cached run"

    def test_completed_cached_true(self, seeded_session, in_memory_handler):
        """cached=True on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["cached"] is True, "Expected cached=True on cached path"

    def test_completed_execution_time_positive_cached(self, seeded_session, in_memory_handler):
        """execution_time_ms > 0 even on cached path (transformation still runs)."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["execution_time_ms"] > 0, (
            f"Expected execution_time_ms > 0, got {completed['execution_time_ms']}"
        )

    def test_completed_data_key_equals_step_name_cached(self, seeded_session, in_memory_handler):
        """data_key equals step_name on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["data_key"] == "transformation"
        assert completed["data_key"] == completed["step_name"]


# -- Tests: Event Ordering -----------------------------------------------------


class TestTransformationEventOrdering:
    """Verify TransformationStarting precedes TransformationCompleted."""

    def test_starting_before_completed_fresh(self, seeded_session, in_memory_handler):
        """TransformationStarting appears before TransformationCompleted on fresh path."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        types = [e["event_type"] for e in events]
        starting_idx = types.index("transformation_starting")
        completed_idx = types.index("transformation_completed")
        assert starting_idx < completed_idx, "TransformationStarting must precede TransformationCompleted"

    def test_starting_before_completed_cached(self, seeded_session, in_memory_handler):
        """TransformationStarting appears before TransformationCompleted on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        types = [e["event_type"] for e in events]
        starting_idx = types.index("transformation_starting")
        completed_idx = types.index("transformation_completed")
        assert starting_idx < completed_idx, "TransformationStarting must precede TransformationCompleted"

    def test_transformation_sequence_fresh(self, seeded_session, in_memory_handler):
        """Transformation events sequence: Starting -> Completed on fresh path."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        te = _transformation_events(events)
        types = [e["event_type"] for e in te]
        assert types == [
            "transformation_starting",
            "transformation_completed",
        ]

    def test_transformation_sequence_cached(self, seeded_session, in_memory_handler):
        """Transformation events sequence: Starting -> Completed on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        te = _transformation_events(events)
        types = [e["event_type"] for e in te]
        assert types == [
            "transformation_starting",
            "transformation_completed",
        ]

    def test_starting_timestamp_before_completed(self, seeded_session, in_memory_handler):
        """TransformationStarting.timestamp <= TransformationCompleted.timestamp."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert starting["timestamp"] <= completed["timestamp"], (
            f"Starting timestamp ({starting['timestamp']}) should be <= "
            f"Completed timestamp ({completed['timestamp']})"
        )


# -- Tests: Zero Overhead (No Emitter) -----------------------------------------


class TestTransformationZeroOverhead:
    """Verify no crash when event_emitter=None."""

    def test_no_events_without_emitter_fresh(self, seeded_session):
        """Pipeline with transformation but no event_emitter runs without error."""
        pipeline = TransformationPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=None,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_transformation_run_result(count=5, operation="transform")):
            result = pipeline.execute(
                data={"input_key": "input_value"},
                initial_context={},
                use_cache=False,
            )
        assert result is not None
        assert "operation" in result.context
        assert result.context["operation"] == "transform"

    def test_no_events_without_emitter_cached(self, seeded_session):
        """Pipeline with transformation on cached path runs without error when event_emitter=None."""
        # Run 1: populate cache
        pipeline1 = TransformationPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=None,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_transformation_run_result(count=5, operation="transform")):
            pipeline1.execute(
                data={"input_key": "input_value"},
                initial_context={},
                use_cache=True,
            )

        # Run 2: cache hit
        pipeline2 = TransformationPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=None,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_transformation_run_result(count=5, operation="transform")):
            result = pipeline2.execute(
                data={"input_key": "input_value"},
                initial_context={},
                use_cache=True,
            )
        assert result is not None


# -- Tests: Cached Field Distinguishes Paths ----------------------------------


class TestTransformationCachedFieldDistinguishesPaths:
    """Verify cached field correctly distinguishes fresh vs cached paths."""

    def test_cached_false_on_fresh_starting(self, seeded_session, in_memory_handler):
        """TransformationStarting.cached=False on fresh path."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["cached"] is False

    def test_cached_false_on_fresh_completed(self, seeded_session, in_memory_handler):
        """TransformationCompleted.cached=False on fresh path."""
        _, events = _run_transformation_fresh(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["cached"] is False

    def test_cached_true_on_cached_starting(self, seeded_session, in_memory_handler):
        """TransformationStarting.cached=True on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "transformation_starting"][0]
        assert starting["cached"] is True

    def test_cached_true_on_cached_completed(self, seeded_session, in_memory_handler):
        """TransformationCompleted.cached=True on cached path."""
        _, events = _run_transformation_cached(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "transformation_completed"][0]
        assert completed["cached"] is True

    def test_both_starting_events_match_cached_field(self, seeded_session, in_memory_handler):
        """Starting and Completed events share same cached field value on same run."""
        # Fresh path
        _, fresh_events = _run_transformation_fresh(seeded_session, in_memory_handler)
        fresh_starting = [e for e in fresh_events if e["event_type"] == "transformation_starting"][0]
        fresh_completed = [e for e in fresh_events if e["event_type"] == "transformation_completed"][0]
        assert fresh_starting["cached"] == fresh_completed["cached"]
        assert fresh_starting["cached"] is False

        # Clear handler for second run
        in_memory_handler.clear()

        # Cached path
        _, cached_events = _run_transformation_cached(seeded_session, in_memory_handler)
        cached_starting = [e for e in cached_events if e["event_type"] == "transformation_starting"][0]
        cached_completed = [e for e in cached_events if e["event_type"] == "transformation_completed"][0]
        assert cached_starting["cached"] == cached_completed["cached"]
        assert cached_starting["cached"] is True
