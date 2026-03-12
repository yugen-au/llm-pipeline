"""Unit tests for llm_pipeline/events/types.py internals.

Covers: _EVENT_REGISTRY, _derive_event_type, serialization round-trip
(to_dict / to_json / resolve_event), frozen immutability, mutable-container
convention boundary, PipelineStarted positional-arg asymmetry, and context
snapshot depth.

All 31 concrete event types are exercised via parametrized EVENT_FIXTURES.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import patch

from conftest import SuccessPipeline, make_simple_run_result
from llm_pipeline.events.types import (
    PipelineEvent,
    StepScopedEvent,
    _EVENT_REGISTRY,
    _derive_event_type,
    # Category constants
    CATEGORY_PIPELINE_LIFECYCLE,
    CATEGORY_STEP_LIFECYCLE,
    CATEGORY_CACHE,
    CATEGORY_LLM_CALL,
    CATEGORY_CONSENSUS,
    CATEGORY_INSTRUCTIONS_CONTEXT,
    CATEGORY_TRANSFORMATION,
    CATEGORY_EXTRACTION,
    CATEGORY_STATE,
    # All 31 concrete event classes
    PipelineStarted,
    PipelineCompleted,
    PipelineError,
    StepSelecting,
    StepSelected,
    StepSkipped,
    StepStarted,
    StepCompleted,
    CacheLookup,
    CacheHit,
    CacheMiss,
    CacheReconstruction,
    LLMCallPrepared,
    LLMCallStarting,
    LLMCallCompleted,
    LLMCallRetry,
    LLMCallFailed,
    LLMCallRateLimited,
    ConsensusStarted,
    ConsensusAttempt,
    ConsensusReached,
    ConsensusFailed,
    InstructionsStored,
    InstructionsLogged,
    ContextUpdated,
    TransformationStarting,
    TransformationCompleted,
    ExtractionStarting,
    ExtractionCompleted,
    ExtractionError,
    StateSaved,
)


# -- Shared base kwargs --------------------------------------------------------

_BASE = dict(run_id="test-run-id", pipeline_name="test_pipeline")
_STEP = dict(**_BASE, step_name="test_step")

# -- EVENT_FIXTURES: (event_type_str, kwargs_dict) for all 31 events -----------

EVENT_FIXTURES = [
    # Pipeline Lifecycle (3)
    ("pipeline_started", {**_BASE}),
    ("pipeline_completed", {**_BASE, "execution_time_ms": 100.0, "steps_executed": 2}),
    ("pipeline_error", {**_STEP, "error_type": "ValueError", "error_message": "test error", "traceback": None}),
    # Step Lifecycle (5)
    ("step_selecting", {**_STEP, "step_index": 0, "strategy_count": 1}),
    ("step_selected", {**_STEP, "step_number": 1, "strategy_name": "test_strategy"}),
    ("step_skipped", {**_STEP, "step_number": 1, "reason": "should_skip returned True"}),
    ("step_started", {**_STEP, "step_number": 1}),
    ("step_completed", {**_STEP, "step_number": 1, "execution_time_ms": 50.0}),
    # Cache (4)
    ("cache_lookup", {**_STEP, "input_hash": "abc123"}),
    ("cache_hit", {**_STEP, "input_hash": "abc123", "cached_at": datetime(2024, 1, 1, 12, 0, 0)}),
    ("cache_miss", {**_STEP, "input_hash": "abc123"}),
    ("cache_reconstruction", {**_STEP, "model_count": 2, "instance_count": 5}),
    # LLM Call (6)
    ("llm_call_prepared", {**_STEP, "call_count": 1}),
    ("llm_call_starting", {**_STEP, "call_index": 0, "rendered_system_prompt": "sys", "rendered_user_prompt": "usr"}),
    ("llm_call_completed", {**_STEP, "call_index": 0, "raw_response": "resp", "parsed_result": {"key": "val"}, "model_name": "mock-model", "attempt_count": 1}),
    ("llm_call_retry", {**_STEP, "attempt": 1, "max_retries": 3, "error_type": "ValueError", "error_message": "err"}),
    ("llm_call_failed", {**_STEP, "max_retries": 3, "last_error": "failed"}),
    ("llm_call_rate_limited", {**_STEP, "attempt": 1, "wait_seconds": 1.0, "backoff_type": "exponential"}),
    # Consensus (4)
    ("consensus_started", {**_STEP, "threshold": 2, "max_calls": 6}),
    ("consensus_attempt", {**_STEP, "attempt": 1, "group_count": 3}),
    ("consensus_reached", {**_STEP, "attempt": 2, "threshold": 2}),
    ("consensus_failed", {**_STEP, "max_calls": 6, "largest_group_size": 1}),
    # Instructions & Context (3)
    ("instructions_stored", {**_STEP, "instruction_count": 3}),
    ("instructions_logged", {**_STEP, "logged_keys": ["test_step"]}),
    ("context_updated", {**_STEP, "new_keys": ["total"], "context_snapshot": {"total": 5}}),
    # Transformation (2)
    ("transformation_starting", {**_STEP, "transformation_class": "TestTransformation", "cached": False}),
    ("transformation_completed", {**_STEP, "data_key": "output", "execution_time_ms": 10.0, "cached": False}),
    # Extraction (3)
    ("extraction_starting", {**_STEP, "extraction_class": "TestExtraction", "model_class": "Item"}),
    ("extraction_completed", {**_STEP, "extraction_class": "TestExtraction", "model_class": "Item", "instance_count": 2, "execution_time_ms": 5.0}),
    ("extraction_error", {**_STEP, "extraction_class": "TestExtraction", "error_type": "ValueError", "error_message": "extraction failed"}),
    # State (1)
    ("state_saved", {**_STEP, "step_number": 1, "input_hash": "abc123", "execution_time_ms": 20.0}),
]


# -- TestDeriveEventType -------------------------------------------------------


class TestDeriveEventType:
    """Verify _derive_event_type converts CamelCase to snake_case correctly."""

    @pytest.mark.parametrize("camel,expected_snake", [
        ("PipelineStarted", "pipeline_started"),
        ("LLMCallStarting", "llm_call_starting"),
        ("LLMCallCompleted", "llm_call_completed"),
        ("CacheHit", "cache_hit"),
        ("StepCompleted", "step_completed"),
        ("ConsensusReached", "consensus_reached"),
        ("ExtractionError", "extraction_error"),
        ("StateSaved", "state_saved"),
        ("LLMCallRateLimited", "llm_call_rate_limited"),
        ("InstructionsLogged", "instructions_logged"),
        ("ContextUpdated", "context_updated"),
    ])
    def test_derive_event_type(self, camel, expected_snake):
        assert _derive_event_type(camel) == expected_snake


# -- TestEventRegistry ---------------------------------------------------------


class TestEventRegistry:
    """Verify _EVENT_REGISTRY contents and lookup behavior."""

    def test_registry_has_31_event_types(self):
        assert len(_EVENT_REGISTRY) == 31

    def test_step_scoped_event_not_in_registry(self):
        assert "step_scoped_event" not in _EVENT_REGISTRY

    def test_pipeline_event_base_not_in_registry(self):
        assert "pipeline_event" not in _EVENT_REGISTRY

    def test_all_values_are_pipeline_event_subclasses(self):
        for cls in _EVENT_REGISTRY.values():
            assert issubclass(cls, PipelineEvent)

    def test_resolve_event_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown event_type"):
            PipelineEvent.resolve_event("no_such_type", {})

    @pytest.mark.parametrize("event_type,kwargs", EVENT_FIXTURES, ids=[e[0] for e in EVENT_FIXTURES])
    def test_each_event_type_registered(self, event_type, kwargs):
        assert event_type in _EVENT_REGISTRY


# -- TestEventCategory ---------------------------------------------------------


EXPECTED_CATEGORIES = {
    "pipeline_started": CATEGORY_PIPELINE_LIFECYCLE,
    "pipeline_completed": CATEGORY_PIPELINE_LIFECYCLE,
    "pipeline_error": CATEGORY_PIPELINE_LIFECYCLE,
    "step_selecting": CATEGORY_STEP_LIFECYCLE,
    "step_selected": CATEGORY_STEP_LIFECYCLE,
    "step_skipped": CATEGORY_STEP_LIFECYCLE,
    "step_started": CATEGORY_STEP_LIFECYCLE,
    "step_completed": CATEGORY_STEP_LIFECYCLE,
    "cache_lookup": CATEGORY_CACHE,
    "cache_hit": CATEGORY_CACHE,
    "cache_miss": CATEGORY_CACHE,
    "cache_reconstruction": CATEGORY_CACHE,
    "llm_call_prepared": CATEGORY_LLM_CALL,
    "llm_call_starting": CATEGORY_LLM_CALL,
    "llm_call_completed": CATEGORY_LLM_CALL,
    "llm_call_retry": CATEGORY_LLM_CALL,
    "llm_call_failed": CATEGORY_LLM_CALL,
    "llm_call_rate_limited": CATEGORY_LLM_CALL,
    "consensus_started": CATEGORY_CONSENSUS,
    "consensus_attempt": CATEGORY_CONSENSUS,
    "consensus_reached": CATEGORY_CONSENSUS,
    "consensus_failed": CATEGORY_CONSENSUS,
    "instructions_stored": CATEGORY_INSTRUCTIONS_CONTEXT,
    "instructions_logged": CATEGORY_INSTRUCTIONS_CONTEXT,
    "context_updated": CATEGORY_INSTRUCTIONS_CONTEXT,
    "transformation_starting": CATEGORY_TRANSFORMATION,
    "transformation_completed": CATEGORY_TRANSFORMATION,
    "extraction_starting": CATEGORY_EXTRACTION,
    "extraction_completed": CATEGORY_EXTRACTION,
    "extraction_error": CATEGORY_EXTRACTION,
    "state_saved": CATEGORY_STATE,
}


class TestEventCategory:
    """Verify each event type has the correct EVENT_CATEGORY."""

    @pytest.mark.parametrize(
        "event_type,expected_category",
        list(EXPECTED_CATEGORIES.items()),
        ids=list(EXPECTED_CATEGORIES.keys()),
    )
    def test_event_category(self, event_type, expected_category):
        cls = _EVENT_REGISTRY[event_type]
        assert cls.EVENT_CATEGORY == expected_category


# -- TestEventImmutability -----------------------------------------------------


class TestEventImmutability:
    """Verify frozen dataclass prevents field reassignment."""

    def test_frozen_prevents_run_id_reassignment(self):
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        with pytest.raises(AttributeError):
            event.run_id = "x"

    def test_frozen_prevents_pipeline_name_reassignment(self):
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        with pytest.raises(AttributeError):
            event.pipeline_name = "x"

    def test_frozen_prevents_new_attribute(self):
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        # slots=True + frozen=True raises TypeError (not AttributeError)
        # due to __init_subclass__ class-object replacement breaking super()
        with pytest.raises((AttributeError, TypeError)):
            event.new_attr = "x"

    def test_frozen_prevents_event_type_reassignment(self):
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        with pytest.raises(AttributeError):
            event.event_type = "x"

    def test_event_type_field_set_correctly_by_post_init(self):
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        assert event.event_type == "pipeline_started"


# -- TestMutableContainerConvention --------------------------------------------


class TestMutableContainerConvention:
    """Document convention boundary: frozen prevents reassignment but not
    mutation of mutable container contents (list/dict)."""

    def test_frozen_prevents_list_field_reassignment(self):
        event = InstructionsLogged(
            run_id="r1", pipeline_name="p1", step_name="s1",
            logged_keys=["a"],
        )
        with pytest.raises(AttributeError):
            event.logged_keys = ["b"]

    def test_list_contents_can_be_mutated_by_convention(self):
        event = InstructionsLogged(
            run_id="r1", pipeline_name="p1", step_name="s1",
            logged_keys=["a"],
        )
        # frozen prevents reassignment but not mutation of the container's contents
        event.logged_keys.append("b")
        assert event.logged_keys == ["a", "b"]

    def test_frozen_prevents_dict_field_reassignment(self):
        event = ContextUpdated(
            run_id="r1", pipeline_name="p1", step_name="s1",
            new_keys=[], context_snapshot={"k": "v"},
        )
        with pytest.raises(AttributeError):
            event.context_snapshot = {}

    def test_dict_contents_can_be_mutated_by_convention(self):
        event = ContextUpdated(
            run_id="r1", pipeline_name="p1", step_name="s1",
            new_keys=[], context_snapshot={"k": "v"},
        )
        # frozen prevents reassignment but not mutation of the container's contents
        event.context_snapshot["new_key"] = "x"
        assert "new_key" in event.context_snapshot


# -- TestEventSerialization ----------------------------------------------------


class TestEventSerialization:
    """Verify to_dict() and to_json() serialization."""

    def test_to_dict_contains_event_type(self):
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        d = event.to_dict()
        assert d["event_type"] == "pipeline_started"

    def test_to_dict_timestamp_is_iso_string(self):
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        d = event.to_dict()
        assert isinstance(d["timestamp"], str)
        datetime.fromisoformat(d["timestamp"])  # should not raise

    def test_to_dict_cached_at_is_iso_string(self):
        event = CacheHit(
            run_id="r1", pipeline_name="p1", step_name="s1",
            input_hash="abc", cached_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        d = event.to_dict()
        assert isinstance(d["cached_at"], str)
        parsed = datetime.fromisoformat(d["cached_at"])
        assert parsed == datetime(2024, 1, 1, 12, 0, 0)

    def test_to_json_returns_valid_json(self):
        event = PipelineCompleted(
            run_id="r1", pipeline_name="p1",
            execution_time_ms=100.0, steps_executed=2,
        )
        result = event.to_json()
        parsed = json.loads(result)
        assert parsed["event_type"] == "pipeline_completed"

    def test_to_dict_all_required_fields_present(self):
        event = PipelineStarted(run_id="r1", pipeline_name="p1")
        d = event.to_dict()
        assert "run_id" in d
        assert "pipeline_name" in d
        assert "timestamp" in d
        assert "event_type" in d

    @pytest.mark.parametrize("event_type,kwargs", EVENT_FIXTURES, ids=[e[0] for e in EVENT_FIXTURES])
    def test_to_dict_contains_event_type_parametrized(self, event_type, kwargs):
        cls = _EVENT_REGISTRY[event_type]
        event = cls(**kwargs)
        d = event.to_dict()
        assert d["event_type"] == event_type


# -- TestResolveEvent ----------------------------------------------------------


class TestResolveEvent:
    """Verify resolve_event() round-trip deserialization."""

    @pytest.mark.parametrize("event_type,kwargs", EVENT_FIXTURES, ids=[e[0] for e in EVENT_FIXTURES])
    def test_round_trip_all_event_types(self, event_type, kwargs):
        cls = _EVENT_REGISTRY[event_type]
        event = cls(**kwargs)
        d = event.to_dict()
        restored = PipelineEvent.resolve_event(event_type, d)
        assert restored.event_type == event_type
        assert restored.run_id == kwargs["run_id"]

    def test_round_trip_preserves_all_base_fields(self):
        event = PipelineCompleted(
            run_id="r1", pipeline_name="p1",
            execution_time_ms=123.45, steps_executed=3,
        )
        d = event.to_dict()
        restored = PipelineEvent.resolve_event("pipeline_completed", d)
        assert restored.execution_time_ms == 123.45
        assert restored.steps_executed == 3
        assert restored.pipeline_name == "p1"

    def test_cache_hit_cached_at_deserialized_as_datetime(self):
        event = CacheHit(
            run_id="r1", pipeline_name="p1", step_name="s1",
            input_hash="abc", cached_at=datetime(2024, 1, 1, 12, 0, 0),
        )
        d = event.to_dict()
        restored = PipelineEvent.resolve_event("cache_hit", d)
        assert isinstance(restored.cached_at, datetime)
        assert restored.cached_at == datetime(2024, 1, 1, 12, 0, 0)

    def test_resolve_event_strips_event_type_from_data(self):
        data = {
            "run_id": "r1",
            "pipeline_name": "p1",
            "timestamp": datetime(2024, 1, 1).isoformat(),
            "event_type": "pipeline_started",
        }
        restored = PipelineEvent.resolve_event("pipeline_started", data)
        assert restored.event_type == "pipeline_started"

    def test_resolve_event_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown event_type"):
            PipelineEvent.resolve_event("nonexistent_type", {})


# -- TestPipelineStartedPositionalArgs -----------------------------------------


class TestPipelineStartedPositionalArgs:
    """PipelineStarted is the only event accepting positional args (no kw_only)."""

    def test_pipeline_started_accepts_positional_args(self):
        event = PipelineStarted("run-1", "my_pipeline")
        assert event.run_id == "run-1"
        assert event.pipeline_name == "my_pipeline"
        assert event.event_type == "pipeline_started"

    def test_pipeline_completed_requires_kw_only(self):
        with pytest.raises(TypeError):
            PipelineCompleted("run-1", "my_pipeline", 100.0, 2)


# -- TestContextSnapshotDepth --------------------------------------------------


class TestContextSnapshotDepth:
    """Context snapshot depth coverage per task 15 recommendation #3.

    Direct construction test reveals that frozen dataclasses do NOT deep-copy
    on construction -- the event holds a reference to the original dict.
    This is by-convention: callers must not mutate after passing.
    """

    def test_context_snapshot_holds_reference_not_copy(self):
        """Frozen prevents reassignment but NOT mutation via reference.

        Dataclass construction stores the reference directly. If the caller
        mutates the source dict after construction, the event sees the change.
        This documents the convention: callers must pass a copy if isolation
        is needed. The pipeline code is responsible for snapshot isolation.
        """
        source_dict = {"total": 5}
        event = ContextUpdated(
            run_id="r1", pipeline_name="p1", step_name="s1",
            new_keys=["total"], context_snapshot=source_dict,
        )
        # Mutate source -- event holds a reference, so it sees the mutation
        source_dict["total"] = 999
        # Document: frozen dataclass does NOT copy on construction
        assert event.context_snapshot["total"] == 999

    def test_context_snapshot_contains_all_merged_keys_integration(
        self, seeded_session, in_memory_handler
    ):
        """Integration: ContextUpdated snapshot contains merged keys after pipeline run."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=1)):
            pipeline.execute(data="test data", initial_context={})

        ctx_events = [
            e for e in in_memory_handler.get_events()
            if e["event_type"] == "context_updated"
        ]
        assert len(ctx_events) >= 1, "Expected at least 1 ContextUpdated event"
        last_ctx = ctx_events[-1]
        assert "total" in last_ctx["context_snapshot"]

    def test_context_snapshot_new_keys_reflects_step_output(
        self, seeded_session, in_memory_handler
    ):
        """Integration: new_keys for each step contains 'total' (SimpleStep output)."""
        pipeline = SuccessPipeline(
            session=seeded_session,
            model="test-model",
            event_emitter=in_memory_handler,
        )
        with patch("pydantic_ai.Agent.run_sync", return_value=make_simple_run_result(count=2)):
            pipeline.execute(data="test data", initial_context={})

        ctx_events = [
            e for e in in_memory_handler.get_events()
            if e["event_type"] == "context_updated"
        ]
        for ctx_event in ctx_events:
            assert "total" in ctx_event["new_keys"]
