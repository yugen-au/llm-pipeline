"""Integration tests for LLM call event emissions.

Verifies LLMCallPrepared, LLMCallStarting, LLMCallCompleted events emitted
by Pipeline.execute() via InMemoryEventHandler. Tests cover happy path,
error path, event pairing, and zero-overhead when no emitter is configured.
"""
import pytest
from unittest.mock import patch

from llm_pipeline.events.types import (
    LLMCallPrepared,
    LLMCallStarting,
    LLMCallCompleted,
)
from conftest import (
    MockProvider,
    SuccessPipeline,
)


# -- Helpers -------------------------------------------------------------------


def _run_success_pipeline(seeded_session, handler):
    """Execute SuccessPipeline with 2 responses and return (pipeline, events)."""
    provider = MockProvider(responses=[
        {"count": 1, "notes": "first"},
        {"count": 2, "notes": "second"},
    ])
    pipeline = SuccessPipeline(
        session=seeded_session,
        provider=provider,
        event_emitter=handler,
    )
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
    """Verify LLMCallStarting emitted before provider call with rendered prompts."""

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
            # Should be the rendered content, not the key
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
                # find next completed after this starting
                rest = types[i + 1:]
                assert "llm_call_completed" in rest


class TestLLMCallCompleted:
    """Verify LLMCallCompleted emitted after provider call with result fields."""

    def test_completed_emitted_per_call(self, seeded_session, in_memory_handler):
        """LLMCallCompleted emitted once per LLM call."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert len(completed) == 2

    def test_raw_response_present(self, seeded_session, in_memory_handler):
        """raw_response contains MockProvider's response string."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert c["raw_response"] == "mock response"

    def test_parsed_result_is_dict(self, seeded_session, in_memory_handler):
        """parsed_result is a dict from MockProvider response."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert isinstance(c["parsed_result"], dict)

    def test_model_name(self, seeded_session, in_memory_handler):
        """model_name matches MockProvider's model_name ('mock-model')."""
        _, events = _run_success_pipeline(seeded_session, in_memory_handler)
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        for c in completed:
            assert c["model_name"] == "mock-model"

    def test_attempt_count(self, seeded_session, in_memory_handler):
        """attempt_count=1 from MockProvider (single attempt)."""
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
        # First step events
        assert llm_events[0]["event_type"] == "llm_call_prepared"
        assert llm_events[1]["event_type"] == "llm_call_starting"
        assert llm_events[2]["event_type"] == "llm_call_completed"
        # Second step events
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
    """Verify LLMCallCompleted emitted with error data on provider exception."""

    def test_completed_emitted_on_error(self, seeded_session, in_memory_handler):
        """LLMCallCompleted emitted even when provider raises."""
        provider = MockProvider(should_fail=True)
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=in_memory_handler,
        )
        with pytest.raises(ValueError, match="Mock provider failure"):
            pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert len(completed) == 1, "Expected 1 LLMCallCompleted on error path"

    def test_error_raw_response_none(self, seeded_session, in_memory_handler):
        """raw_response=None on exception."""
        provider = MockProvider(should_fail=True)
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=in_memory_handler,
        )
        with pytest.raises(ValueError):
            pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert completed[0]["raw_response"] is None

    def test_error_parsed_result_none(self, seeded_session, in_memory_handler):
        """parsed_result=None on exception."""
        provider = MockProvider(should_fail=True)
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=in_memory_handler,
        )
        with pytest.raises(ValueError):
            pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert completed[0]["parsed_result"] is None

    def test_error_validation_errors_contains_message(self, seeded_session, in_memory_handler):
        """validation_errors contains the exception message."""
        provider = MockProvider(should_fail=True)
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=in_memory_handler,
        )
        with pytest.raises(ValueError):
            pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert len(completed[0]["validation_errors"]) > 0
        assert "Mock provider failure" in completed[0]["validation_errors"][0]

    def test_error_starting_still_emitted(self, seeded_session, in_memory_handler):
        """LLMCallStarting still emitted before the failed call."""
        provider = MockProvider(should_fail=True)
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=in_memory_handler,
        )
        with pytest.raises(ValueError):
            pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        assert len(starting) == 1, "LLMCallStarting should still be emitted before error"

    def test_error_starting_completed_paired(self, seeded_session, in_memory_handler):
        """Starting and Completed are paired even on error (same call_index)."""
        provider = MockProvider(should_fail=True)
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=in_memory_handler,
        )
        with pytest.raises(ValueError):
            pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        starting = [e for e in events if e["event_type"] == "llm_call_starting"]
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert starting[0]["call_index"] == completed[0]["call_index"]

    def test_error_model_name_none(self, seeded_session, in_memory_handler):
        """model_name=None on exception (provider never returned)."""
        provider = MockProvider(should_fail=True)
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=in_memory_handler,
        )
        with pytest.raises(ValueError):
            pipeline.execute(data="test data", initial_context={})

        events = in_memory_handler.get_events()
        completed = [e for e in events if e["event_type"] == "llm_call_completed"]
        assert completed[0]["model_name"] is None


class TestNoEmitterZeroOverhead:
    """Verify no event params injected when event_emitter is None."""

    def test_no_events_without_emitter(self, seeded_session):
        """Pipeline without event_emitter emits no events (no crash)."""
        provider = MockProvider(responses=[
            {"count": 1, "notes": "first"},
            {"count": 2, "notes": "second"},
        ])
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=None,
        )
        result = pipeline.execute(data="test data", initial_context={})
        assert result is not None
        assert result.context["total"] == 2

    def test_no_event_params_in_call_kwargs(self, seeded_session, monkeypatch):
        """execute_llm_step not called with event params when no emitter."""
        provider = MockProvider(responses=[
            {"count": 1, "notes": "first"},
            {"count": 2, "notes": "second"},
        ])
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=None,
        )

        captured_kwargs = []
        original_execute = __import__(
            "llm_pipeline.llm.executor", fromlist=["execute_llm_step"]
        ).execute_llm_step

        def spy_execute(**kwargs):
            captured_kwargs.append(dict(kwargs))
            return original_execute(**kwargs)

        monkeypatch.setattr(
            "llm_pipeline.llm.executor.execute_llm_step",
            spy_execute,
        )

        pipeline.execute(data="test data", initial_context={})

        assert len(captured_kwargs) >= 1
        for kw in captured_kwargs:
            assert "event_emitter" not in kw, "event_emitter should not be injected without emitter"
            assert "run_id" not in kw, "run_id should not be injected without emitter"
            assert "pipeline_name" not in kw, "pipeline_name should not be injected without emitter"
            assert "step_name" not in kw, "step_name should not be injected without emitter"
            assert "call_index" not in kw, "call_index should not be injected without emitter"
