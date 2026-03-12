"""Integration tests for consensus event emissions.

Verifies ConsensusStarted, ConsensusAttempt, ConsensusReached, and
ConsensusFailed events emitted by PipelineConfig._execute_with_consensus()
via InMemoryEventHandler. Tests use Agent.run_sync patching with response
lists to control consensus outcomes (identical outputs -> consensus reached,
different outputs -> consensus failed).
"""
import pytest
from unittest.mock import patch, MagicMock

from llm_pipeline import MajorityVoteStrategy, PipelineStrategy
from llm_pipeline.events.types import (
    ConsensusStarted,
    ConsensusAttempt,
    ConsensusReached,
    ConsensusFailed,
)
from conftest import (
    SuccessPipeline, SimpleStep,
    make_simple_run_result,
)


# -- Helpers -------------------------------------------------------------------


def _make_responses(counts):
    """Build a list of MagicMock run results from a list of count values."""
    results = []
    for count in counts:
        results.append(make_simple_run_result(count=count))
    return results


def _consensus_strategies(threshold, max_calls):
    """Build strategy instances with MajorityVoteStrategy on both steps."""
    mv = MajorityVoteStrategy(threshold=threshold, max_attempts=max_calls)

    class ConsensusTestStrategy(PipelineStrategy):
        def can_handle(self, context):
            return True
        def get_steps(self):
            return [
                SimpleStep.create_definition(consensus_strategy=mv),
                SimpleStep.create_definition(consensus_strategy=mv),
            ]
    return [ConsensusTestStrategy()]


def _run_consensus_pipeline(seeded_session, handler, counts, threshold=2, max_calls=5):
    """Execute SuccessPipeline with per-step MajorityVoteStrategy.

    SuccessPipeline has 2 SimpleSteps. Each step produces 1 call_params entry,
    so _execute_with_consensus runs once per step.

    counts: list of int values, consumed sequentially as run_sync return values.
    Two counts with the same value will produce identical instructions (consensus).

    Returns (pipeline, events).
    """
    responses = _make_responses(counts)
    call_count = [0]

    def _side_effect(*args, **kwargs):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(responses):
            return responses[idx]
        return make_simple_run_result(count=counts[-1] if counts else 1)

    pipeline = SuccessPipeline(
        session=seeded_session,
        model="test-model",
        event_emitter=handler,
        strategies=_consensus_strategies(threshold, max_calls),
    )
    with patch("pydantic_ai.Agent.run_sync", side_effect=_side_effect):
        pipeline.execute(
            data="test data",
            initial_context={},
        )
    return pipeline, handler.get_events()


def _consensus_events(events):
    """Filter only consensus-related events from full event stream."""
    consensus_types = {
        "consensus_started",
        "consensus_attempt",
        "consensus_reached",
        "consensus_failed",
    }
    return [e for e in events if e["event_type"] in consensus_types]


# -- Tests: ConsensusReached Path ---------------------------------------------


class TestConsensusReachedPath:
    """Verify events when consensus is reached (identical responses)."""

    def test_consensus_reached_fires(self, seeded_session, in_memory_handler):
        """Identical responses -> ConsensusReached fires."""
        # 2 identical for step 1 consensus (threshold=2), then 2 identical for step 2
        counts = [1, 1, 1, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)

        started = [e for e in ce if e["event_type"] == "consensus_started"]
        attempts = [e for e in ce if e["event_type"] == "consensus_attempt"]
        reached = [e for e in ce if e["event_type"] == "consensus_reached"]
        failed = [e for e in ce if e["event_type"] == "consensus_failed"]

        # 2 steps -> 2 ConsensusStarted
        assert len(started) == 2, f"Expected 2 ConsensusStarted, got {len(started)}"
        assert started[0]["threshold"] == 2
        assert started[0]["max_calls"] == 5

        # Each step reaches consensus on attempt 2 -> 2 attempts per step = 4 total
        assert len(attempts) == 4, f"Expected 4 ConsensusAttempt, got {len(attempts)}"

        # ConsensusReached fires once per step
        assert len(reached) == 2, f"Expected 2 ConsensusReached, got {len(reached)}"
        assert reached[0]["attempt"] == 2
        assert reached[0]["threshold"] == 2

        # No ConsensusFailed
        assert len(failed) == 0, "No ConsensusFailed expected on success path"

    def test_consensus_reached_event_type_string(self, seeded_session, in_memory_handler):
        """Verify event_type strings match expected snake_case names."""
        counts = [1, 1, 1, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        types = {e["event_type"] for e in ce}
        assert "consensus_started" in types
        assert "consensus_attempt" in types
        assert "consensus_reached" in types

    def test_both_attempt_and_reached_fire_on_winning_attempt(self, seeded_session, in_memory_handler):
        """Winning attempt emits both ConsensusAttempt then ConsensusReached."""
        counts = [1, 1, 1, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)

        step1_attempts = [e for e in ce if e["event_type"] == "consensus_attempt"]
        step1_reached = [e for e in ce if e["event_type"] == "consensus_reached"]

        winning_attempt_events = [e for e in step1_attempts if e["attempt"] == 2]
        assert len(winning_attempt_events) >= 1, "ConsensusAttempt should fire for winning attempt"
        assert len(step1_reached) >= 1, "ConsensusReached should fire"
        assert step1_reached[0]["attempt"] == 2

        # Verify ordering: ConsensusAttempt(attempt=2) appears before ConsensusReached
        attempt_idx = None
        reached_idx = None
        for i, e in enumerate(ce):
            if e["event_type"] == "consensus_attempt" and e["attempt"] == 2 and attempt_idx is None:
                attempt_idx = i
        for i, e in enumerate(ce):
            if e["event_type"] == "consensus_reached" and reached_idx is None:
                reached_idx = i
        assert attempt_idx < reached_idx, "ConsensusAttempt must fire before ConsensusReached"


# -- Tests: ConsensusFailed Path ----------------------------------------------


class TestConsensusFailedPath:
    """Verify events when consensus fails (all different responses)."""

    def test_consensus_failed_fires(self, seeded_session, in_memory_handler):
        """Different responses -> ConsensusFailed fires."""
        # 3 different for step 1 (threshold=3, max_calls=3 -> fails)
        # then 3 different for step 2 (also fails)
        counts = [1, 2, 3, 4, 5, 6]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=3, max_calls=3,
        )
        ce = _consensus_events(events)

        started = [e for e in ce if e["event_type"] == "consensus_started"]
        attempts = [e for e in ce if e["event_type"] == "consensus_attempt"]
        reached = [e for e in ce if e["event_type"] == "consensus_reached"]
        failed = [e for e in ce if e["event_type"] == "consensus_failed"]

        # 2 steps -> 2 ConsensusStarted
        assert len(started) == 2
        assert started[0]["threshold"] == 3
        assert started[0]["max_calls"] == 3

        # Each step exhausts all 3 attempts -> 3 per step = 6 total
        assert len(attempts) == 6, f"Expected 6 ConsensusAttempt, got {len(attempts)}"

        # ConsensusFailed fires once per step
        assert len(failed) == 2, f"Expected 2 ConsensusFailed, got {len(failed)}"
        assert failed[0]["max_calls"] == 3
        assert failed[0]["largest_group_size"] == 1  # all different -> group size 1

        # No ConsensusReached
        assert len(reached) == 0, "No ConsensusReached expected on failure path"

    def test_consensus_failed_largest_group_size(self, seeded_session, in_memory_handler):
        """ConsensusFailed.largest_group_size reflects actual largest group."""
        # 5 responses for step 1: 2 identical (count=1) + 3 different (threshold=3, max=5)
        # largest group = 2, but threshold=3 -> fails
        # Then 5 for step 2 with same pattern
        counts = [1, 1, 2, 3, 4, 1, 1, 2, 3, 4]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=3, max_calls=5,
        )
        ce = _consensus_events(events)
        failed = [e for e in ce if e["event_type"] == "consensus_failed"]
        assert len(failed) == 2
        assert failed[0]["largest_group_size"] == 2, "Largest group has 2 identical responses"


# -- Tests: Event Ordering ----------------------------------------------------


class TestConsensusEventOrdering:
    """Verify ConsensusStarted -> ConsensusAttempt*N -> ConsensusReached/Failed ordering."""

    def test_started_before_attempts(self, seeded_session, in_memory_handler):
        """ConsensusStarted appears before any ConsensusAttempt for each step."""
        counts = [1, 1, 1, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        types = [e["event_type"] for e in ce]

        first_started = types.index("consensus_started")
        first_attempt = types.index("consensus_attempt")
        assert first_started < first_attempt, "ConsensusStarted must precede ConsensusAttempt"

    def test_attempts_before_reached(self, seeded_session, in_memory_handler):
        """ConsensusAttempt events precede ConsensusReached."""
        counts = [1, 1, 1, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        types = [e["event_type"] for e in ce]

        first_attempt = types.index("consensus_attempt")
        first_reached = types.index("consensus_reached")
        assert first_attempt < first_reached, "ConsensusAttempt must precede ConsensusReached"

    def test_full_sequence_reached(self, seeded_session, in_memory_handler):
        """Full sequence for reached path: Started -> Attempt -> Attempt -> Reached."""
        counts = [1, 1, 1, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)

        # Extract step 1 consensus events (first batch before second ConsensusStarted)
        step1_events = []
        started_count = 0
        for e in ce:
            if e["event_type"] == "consensus_started":
                started_count += 1
                if started_count > 1:
                    break
            step1_events.append(e)

        step1_types = [e["event_type"] for e in step1_events]
        assert step1_types == [
            "consensus_started",
            "consensus_attempt",
            "consensus_attempt",
            "consensus_reached",
        ]

    def test_full_sequence_failed(self, seeded_session, in_memory_handler):
        """Full sequence for failed path: Started -> Attempt*N -> Failed."""
        counts = [1, 2, 3, 4, 5, 6]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=3, max_calls=3,
        )
        ce = _consensus_events(events)

        # Extract step 1 events
        step1_events = []
        started_count = 0
        for e in ce:
            if e["event_type"] == "consensus_started":
                started_count += 1
                if started_count > 1:
                    break
            step1_events.append(e)

        step1_types = [e["event_type"] for e in step1_events]
        assert step1_types == [
            "consensus_started",
            "consensus_attempt",
            "consensus_attempt",
            "consensus_attempt",
            "consensus_failed",
        ]

    def test_attempt_numbers_sequential(self, seeded_session, in_memory_handler):
        """ConsensusAttempt.attempt values are sequential (1, 2, ...)."""
        counts = [1, 2, 3, 4, 5, 6]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=3, max_calls=3,
        )
        ce = _consensus_events(events)

        # Step 1 attempts (first 3 ConsensusAttempt events)
        attempts = [e for e in ce if e["event_type"] == "consensus_attempt"]
        step1_attempts = attempts[:3]
        assert [a["attempt"] for a in step1_attempts] == [1, 2, 3]


# -- Tests: Event Fields ------------------------------------------------------


class TestConsensusEventFields:
    """Verify run_id, pipeline_name, step_name, timestamp populated correctly."""

    def test_started_fields(self, seeded_session, in_memory_handler):
        """ConsensusStarted has all required fields."""
        counts = [1, 1, 1, 1]
        pipeline, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        started = [e for e in ce if e["event_type"] == "consensus_started"][0]

        assert started["run_id"] == pipeline.run_id
        assert started["pipeline_name"] == pipeline.pipeline_name
        assert started["step_name"] == "simple"
        assert "timestamp" in started
        assert isinstance(started["timestamp"], str)
        assert started["threshold"] == 2
        assert started["max_calls"] == 5

    def test_attempt_fields(self, seeded_session, in_memory_handler):
        """ConsensusAttempt has all required fields."""
        counts = [1, 1, 1, 1]
        pipeline, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        attempt = [e for e in ce if e["event_type"] == "consensus_attempt"][0]

        assert attempt["run_id"] == pipeline.run_id
        assert attempt["pipeline_name"] == pipeline.pipeline_name
        assert attempt["step_name"] == "simple"
        assert "timestamp" in attempt
        assert attempt["attempt"] == 1
        assert isinstance(attempt["group_count"], int)
        assert attempt["group_count"] >= 1

    def test_reached_fields(self, seeded_session, in_memory_handler):
        """ConsensusReached has all required fields."""
        counts = [1, 1, 1, 1]
        pipeline, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        reached = [e for e in ce if e["event_type"] == "consensus_reached"][0]

        assert reached["run_id"] == pipeline.run_id
        assert reached["pipeline_name"] == pipeline.pipeline_name
        assert reached["step_name"] == "simple"
        assert "timestamp" in reached
        assert reached["attempt"] == 2
        assert reached["threshold"] == 2

    def test_failed_fields(self, seeded_session, in_memory_handler):
        """ConsensusFailed has all required fields."""
        counts = [1, 2, 3, 4, 5, 6]
        pipeline, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=3, max_calls=3,
        )
        ce = _consensus_events(events)
        failed = [e for e in ce if e["event_type"] == "consensus_failed"][0]

        assert failed["run_id"] == pipeline.run_id
        assert failed["pipeline_name"] == pipeline.pipeline_name
        assert failed["step_name"] == "simple"
        assert "timestamp" in failed
        assert failed["max_calls"] == 3
        assert failed["largest_group_size"] == 1

    def test_run_id_consistent_across_consensus_events(self, seeded_session, in_memory_handler):
        """All consensus events share the same run_id."""
        counts = [1, 1, 1, 1]
        pipeline, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        for e in ce:
            assert e["run_id"] == pipeline.run_id


# -- Tests: Zero Overhead (No Emitter) ----------------------------------------


class TestConsensusZeroOverhead:
    """Verify no crash when event_emitter=None."""

    def test_no_events_without_emitter(self, seeded_session):
        """Pipeline with consensus_strategy but no event_emitter runs without error."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=None,
            strategies=_consensus_strategies(threshold=2, max_calls=5),
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=1)):
            result = pipeline.execute(
                data="test data",
                initial_context={},
            )
        assert result is not None
        assert "total" in result.context


# -- Tests: Multi-Group Consensus ---------------------------------------------


class TestConsensusMultiGroup:
    """Verify group_count evolution and ConsensusReached on first group hitting threshold."""

    def test_group_count_evolution(self, seeded_session, in_memory_handler):
        """ConsensusAttempt.group_count tracks number of distinct response groups.

        Responses for step 1: A(1), B(2), A(1) -> groups evolve 1 -> 2 -> 2.
        Consensus reached on attempt 3 (group A has 2 members, threshold=2).
        Then identical pattern for step 2.
        """
        counts = [1, 2, 1, 1, 2, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        attempts = [e for e in ce if e["event_type"] == "consensus_attempt"]

        # Step 1 attempts (first 3)
        step1_attempts = attempts[:3]
        group_counts = [a["group_count"] for a in step1_attempts]
        assert group_counts == [1, 2, 2], f"Expected [1, 2, 2], got {group_counts}"

    def test_reached_on_first_group_hitting_threshold(self, seeded_session, in_memory_handler):
        """ConsensusReached fires when first group reaches threshold."""
        counts = [1, 2, 1, 1, 2, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        reached = [e for e in ce if e["event_type"] == "consensus_reached"]

        assert len(reached) == 2, f"Expected 2 ConsensusReached, got {len(reached)}"
        assert reached[0]["attempt"] == 3, "Consensus should be reached on attempt 3"

    def test_multi_group_no_failed(self, seeded_session, in_memory_handler):
        """When consensus is reached via multi-group, no ConsensusFailed fires."""
        counts = [1, 2, 1, 1, 2, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)
        failed = [e for e in ce if e["event_type"] == "consensus_failed"]
        assert len(failed) == 0

    def test_multi_group_step1_sequence(self, seeded_session, in_memory_handler):
        """Step 1 event sequence: Started, Attempt(1), Attempt(2), Attempt(3), Reached."""
        counts = [1, 2, 1, 1, 2, 1]
        _, events = _run_consensus_pipeline(
            seeded_session, in_memory_handler, counts, threshold=2, max_calls=5,
        )
        ce = _consensus_events(events)

        # Extract step 1 events
        step1_events = []
        started_count = 0
        for e in ce:
            if e["event_type"] == "consensus_started":
                started_count += 1
                if started_count > 1:
                    break
            step1_events.append(e)

        step1_types = [e["event_type"] for e in step1_events]
        assert step1_types == [
            "consensus_started",
            "consensus_attempt",
            "consensus_attempt",
            "consensus_attempt",
            "consensus_reached",
        ]
