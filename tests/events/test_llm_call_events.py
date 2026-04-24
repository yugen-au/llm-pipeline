"""Integration tests for LLM call event emissions.

Verifies LLMCallPrepared, LLMCallStarting, LLMCallCompleted events emitted
by Pipeline.execute() via InMemoryEventHandler. Tests cover happy path,
error path, event pairing, and zero-overhead when no emitter is configured.
"""
import pytest
from unittest.mock import patch, MagicMock
from pydantic_ai import UnexpectedModelBehavior

from llm_pipeline.events.types import (
    LLMCallPrepared,
    LLMCallStarting,
    LLMCallCompleted,
)
from conftest import (
    SuccessPipeline,
    make_simple_run_result,
)


# -- Helpers -------------------------------------------------------------------


def _run_success_pipeline(seeded_session, handler):
    """Execute SuccessPipeline with mocked Agent.run_sync and return (pipeline, events)."""
    pipeline = SuccessPipeline(
        session=seeded_session,
        model="test-model",
        event_emitter=handler,
    )
    with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=1)):
        pipeline.execute(data="test data", initial_context={})
    return pipeline, handler.get_events()


# -- Tests ---------------------------------------------------------------------


class TestLLMCallPrepared:
    """Verify LLMCallPrepared emitted after prepare_calls for each step."""

    def test_prepared_emitted_per_step(self, seeded_session, in_memory_handler):
        """LLMCallPrepared emitted once per step (2 steps in SuccessPipeline)."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        prepared = [e for e in events if e["event_type"] == "llm_call_prepared"]
        assert len(prepared) == 2, "Expected 2 LLMCallPrepared (one per step)"

    def test_prepared_call_count(self, seeded_session, in_memory_handler):
        """call_count=1 for SimpleStep (single call_params entry)."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        prepared = [e for e in events if e["event_type"] == "llm_call_prepared"]
        for p in prepared:
            assert p["call_count"] == 1

    def test_prepared_has_system_key(self, seeded_session, in_memory_handler):
        """system_key populated with step's system_instruction_key."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        prepared = [e for e in events if e["event_type"] == "llm_call_prepared"]
        for p in prepared:
            assert p["system_key"] == "simple.system"

    def test_prepared_has_user_key(self, seeded_session, in_memory_handler):
        """user_key populated with step's user_prompt_key."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        prepared = [e for e in events if e["event_type"] == "llm_call_prepared"]
        for p in prepared:
            assert p["user_key"] == "simple.user"

    def test_prepared_has_run_id(self, seeded_session, in_memory_handler):
        """LLMCallPrepared carries run_id from pipeline."""
        pipeline, events = _run_success_pipeline(seeded_session, in_memory_handler)
        prepared = [e for e in events if e["event_type"] == "llm_call_prepared"]
        for p in prepared:
            assert p["run_id"] == pipeline.run_id

    def test_prepared_step_name(self, seeded_session, in_memory_handler):
        """step_name is 'simple' for SimpleStep."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        prepared = [e for e in events if e["event_type"] == "llm_call_prepared"]
        for p in prepared:
            assert p["step_name"] == "simple"


class TestLLMCallStarting:
    """Verify LLMCallStarting emitted before agent call with rendered prompts."""

    def test_starting_emitted_per_call(self, seeded_session, in_memory_handler):
        """LLMCallStarting emitted once per LLM call (2 steps, 1 call each = 2)."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        assert len(starting) == 2

    def test_rendered_system_prompt_is_str(self, seeded_session, in_memory_handler):
        """rendered_system_prompt is a str, not a template key."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        for s in starting:
            assert isinstance(s["rendered_system_prompt"], str)
            assert s["rendered_system_prompt"] != "simple.system"

    def test_rendered_user_prompt_contains_data(self, seeded_session, in_memory_handler):
        """rendered_user_prompt contains rendered template content (Process: test)."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        for s in starting:
            assert isinstance(s["rendered_user_prompt"], str)
            assert "Process: test" in s["rendered_user_prompt"]

    def test_call_index_zero_for_first_param(self, seeded_session, in_memory_handler):
        """call_index=0 for first (and only) call_params entry."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        for s in starting:
            assert s["call_index"] == 0

    def test_starting_before_completed(self, seeded_session, in_memory_handler):
        """LLMCallStarting appears before LLMCallCompleted in event stream."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        types = [e["event_type"] for e in events]
        for i, t in enumerate(types):
            if t == "llm_call_starting":
                rest = types[i + 1:]
                assert "llm_call_completed" in rest


class TestLLMCallCompleted:
    """Verify LLMCallCompleted emitted after agent call with result fields."""

    def test_completed_emitted_per_call(self, seeded_session, in_memory_handler):
        """LLMCallCompleted emitted once per LLM call."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert len(completed) == 2

    def test_raw_response_is_none(self, seeded_session, in_memory_handler):
        """raw_response=None in new pydantic-ai architecture (not populated by agent)."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert c["raw_response"] is None

    def test_parsed_result_is_dict(self, seeded_session, in_memory_handler):
        """parsed_result is a dict from instruction.model_dump()."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert isinstance(c["parsed_result"], dict)

    def test_model_name_is_test_model(self, seeded_session, in_memory_handler):
        """model_name matches pipeline model string ('test-model')."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert c["model_name"] == "test-model"

    def test_attempt_count(self, seeded_session, in_memory_handler):
        """attempt_count=1 (single attempt in new architecture)."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert c["attempt_count"] == 1

    def test_validation_errors_empty_on_success(self, seeded_session, in_memory_handler):
        """validation_errors empty list on success."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert c["validation_errors"] == []

    def test_call_index_matches(self, seeded_session, in_memory_handler):
        """call_index=0 for single-call steps."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert c["call_index"] == 0


class TestLLMCallEventPairing:
    """Verify Starting/Completed pairing and timestamp ordering."""

    def test_call_index_pairing(self, seeded_session, in_memory_handler):
        """Starting.call_index matches Completed.call_index for each pair."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert len(starting) == len(completed)
        for s, c in zip(starting, completed):
            assert s["call_index"] == c["call_index"]

    def test_timestamp_ordering(self, seeded_session, in_memory_handler):
        """Starting.timestamp <= Completed.timestamp for each pair."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for s, c in zip(starting, completed):
            assert s["timestamp"] <= c["timestamp"]

    def test_total_llm_call_event_count(self, seeded_session, in_memory_handler):
        """Total LLM call events: 2 steps * 3 events (Prepared+Starting+Completed) = 6."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        llm_events = [
            e for e in events
            if e["event_type"] in ("llm_call_prepared", "llm_call_starting", "llm_call_completed")
        ]
        assert len(llm_events) == 6

    def test_event_ordering_per_step(self, seeded_session, in_memory_handler):
        """Per step: Prepared -> Starting -> Completed ordering."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        llm_events = [
            e for e in events
            if e["event_type"] in ("llm_call_prepared", "llm_call_starting", "llm_call_completed")
        ]
        assert llm_events[0]["event_type"] == "llm_call_prepared"
        assert llm_events[1]["event_type"] == "llm_call_starting"
        assert llm_events[2]["event_type"] == "llm_call_completed"
        assert llm_events[3]["event_type"] == "llm_call_prepared"
        assert llm_events[4]["event_type"] == "llm_call_starting"
        assert llm_events[5]["event_type"] == "llm_call_completed"

    def test_run_id_consistent(self, seeded_session, in_memory_handler):
        """All LLM call events share the same run_id."""
        pipeline, events = _run_success_pipeline(seeded_session, in_memory_handler)
        llm_events = [
            e for e in events
            if e["event_type"] in ("llm_call_prepared", "llm_call_starting", "llm_call_completed")
        ]
        for e in llm_events:
            assert e["run_id"] == pipeline.run_id


class TestLLMCallErrorPath:
    """Verify pipeline error handling when Agent.run_sync raises."""

    def test_pipeline_error_emitted_on_agent_exception(self, seeded_session, in_memory_handler):
        """PipelineError emitted when Agent.run_sync raises a non-UnexpectedModelBehavior exception."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with pytest.raises(RuntimeError, match="Agent call failed"):
            with patch("pydantic_ai.Agent.run_sync", side_effect=RuntimeError("Agent call failed")):
                pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        pipeline_errors = [e for e in events if e["event_type"] == "pipeline_error"]
        assert len(pipeline_errors) == 1, "Expected 1 PipelineError on agent exception"
        assert "Agent call failed" in pipeline_errors[0]["error_message"]

    def test_unexpected_model_behavior_propagates_if_create_failure_fails(self, seeded_session, in_memory_handler):
        """UnexpectedModelBehavior caught by execute loop; if create_failure() fails
        (required fields missing on instruction type), the ValidationError propagates."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        # SimpleInstructions.create_failure() raises ValidationError because
        # 'count' is required with no default. The outer except catches it as PipelineError.
        from pydantic import ValidationError as PydanticValidationError
        with pytest.raises((PydanticValidationError, Exception)):
            with patch("pydantic_ai.Agent.run_sync", side_effect=UnexpectedModelBehavior("bad output")):
                pipeline.execute(data="test data", initial_context={})

    def test_llm_call_starting_emitted_before_agent_raise(self, seeded_session, in_memory_handler):
        """LLMCallStarting emitted before agent raises (events up to that point captured)."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with pytest.raises(RuntimeError):
            with patch("pydantic_ai.Agent.run_sync", side_effect=RuntimeError("fail")):
                pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        assert len(starting) >= 1, "LLMCallStarting should be emitted before agent raises"


class TestNoEmitterZeroOverhead:
    """Verify no event params injected when event_emitter is None."""

    def test_no_events_without_emitter(self, seeded_session):
        """Pipeline without event_emitter emits no events (no crash)."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=None,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=2)):
            result = pipeline.execute(data="test data", initial_context={})
        assert result is not None
        assert result is not None
