"""Integration tests for context and state event emissions.

Verifies InstructionsStored, InstructionsLogged, ContextUpdated, and StateSaved
events emitted by Pipeline.execute() via InMemoryEventHandler, covering both
fresh (cache miss) and cached (cache hit) code paths.

Test strategy: Use SuccessPipeline fixture (SimpleStep) for most tests.
EmptyContextStep (defined inline) covers ContextUpdated with new_keys=[].
Run once for fresh path, run twice for cached path (run 1 populates cache,
run 2 hits cache -- events cleared between runs).
"""
import pytest
from typing import List, ClassVar, Optional

from llm_pipeline.events.types import (
    InstructionsStored,
    InstructionsLogged,
    ContextUpdated,
    StateSaved,
)
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
from llm_pipeline.types import StepCallParams
from conftest import MockProvider, SuccessPipeline


# -- EmptyContextStep (inline) ------------------------------------------------
# Needed for TestContextUpdatedEmptyContext: step that returns None so that
# _validate_and_merge_context merges {} -> ContextUpdated.new_keys == []


class EmptyContextInstructions(LLMResultMixin):
    """Instruction model for empty-context step."""
    count: int

    example: ClassVar[dict] = {"count": 1, "notes": "test"}


@step_definition(
    instructions=EmptyContextInstructions,
    default_system_key="simple.system",
    default_user_key="simple.user",
)
class EmptyContextStep(LLMStep):
    """Step that returns None from process_instructions (no context update)."""

    def prepare_calls(self) -> List[StepCallParams]:
        return [self.create_llm_call(variables={"data": "test"})]

    def process_instructions(self, instructions):
        return None


class EmptyContextStrategy(PipelineStrategy):
    """Strategy with a single empty-context step."""

    def can_handle(self, context):
        return True

    def get_steps(self):
        return [EmptyContextStep.create_definition()]


class EmptyContextRegistry(PipelineDatabaseRegistry, models=[]):
    pass


class EmptyContextStrategies(PipelineStrategies, strategies=[EmptyContextStrategy]):
    pass


class EmptyContextPipeline(PipelineConfig, registry=EmptyContextRegistry, strategies=EmptyContextStrategies):
    pass


# -- Helpers -------------------------------------------------------------------


def _run_fresh(seeded_session, handler):
    """Execute SuccessPipeline on fresh DB (cache miss path).

    Returns (pipeline, events).
    """
    provider = MockProvider(responses=[
        {"count": 5},
        {"count": 3},
    ])
    pipeline = SuccessPipeline(
        session=seeded_session,
        provider=provider,
        event_emitter=handler,
    )
    pipeline.execute(data={"input_key": "input_value"}, initial_context={}, use_cache=False)
    return pipeline, handler.get_events()


def _run_cached(seeded_session, handler):
    """Execute SuccessPipeline twice: run 1 populates cache, run 2 hits cache.

    Returns (pipeline2, events2) from the second run only.
    """
    # Run 1: cache miss, saves state
    provider1 = MockProvider(responses=[
        {"count": 5},
        {"count": 3},
    ])
    pipeline1 = SuccessPipeline(
        session=seeded_session,
        provider=provider1,
        event_emitter=handler,
    )
    pipeline1.execute(data={"input_key": "input_value"}, initial_context={}, use_cache=True)

    # Clear events from first run
    handler.clear()

    # Run 2: cache hit path
    provider2 = MockProvider(responses=[])  # no LLM calls expected on cache hit
    pipeline2 = SuccessPipeline(
        session=seeded_session,
        provider=provider2,
        event_emitter=handler,
    )
    pipeline2.execute(data={"input_key": "input_value"}, initial_context={}, use_cache=True)
    return pipeline2, handler.get_events()


def _run_empty_ctx_fresh(seeded_session, handler):
    """Execute EmptyContextPipeline on fresh DB.

    Returns (pipeline, events).
    """
    provider = MockProvider(responses=[{"count": 1}])
    pipeline = EmptyContextPipeline(
        session=seeded_session,
        provider=provider,
        event_emitter=handler,
    )
    pipeline.execute(data={"input_key": "input_value"}, initial_context={}, use_cache=False)
    return pipeline, handler.get_events()


def _ctx_state_events(events):
    """Filter context and state events from full event stream."""
    target_types = {
        "instructions_stored",
        "instructions_logged",
        "context_updated",
        "state_saved",
    }
    return [e for e in events if e["event_type"] in target_types]


# -- Tests: InstructionsStored (Fresh Path) ------------------------------------


class TestInstructionsStoredFreshPath:
    """Verify InstructionsStored emitted on fresh (cache miss) path."""

    def test_stored_emitted_fresh(self, seeded_session, in_memory_handler):
        """InstructionsStored emitted for each step on fresh run."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        # SuccessPipeline has 2 steps (SimpleStep x2)
        assert len(stored) == 2, f"Expected 2 InstructionsStored on fresh run, got {len(stored)}"

    def test_stored_instruction_count_positive(self, seeded_session, in_memory_handler):
        """instruction_count >= 1 on fresh path."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        for e in stored:
            assert e["instruction_count"] >= 1, (
                f"Expected instruction_count >= 1, got {e['instruction_count']}"
            )

    def test_stored_step_name_populated(self, seeded_session, in_memory_handler):
        """step_name is populated on each InstructionsStored event."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        for e in stored:
            assert e["step_name"] is not None
            assert isinstance(e["step_name"], str)
            assert len(e["step_name"]) > 0

    def test_stored_has_run_id(self, seeded_session, in_memory_handler):
        """InstructionsStored carries run_id from pipeline."""
        pipeline, events = _run_fresh(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        for e in stored:
            assert e["run_id"] == pipeline.run_id

    def test_stored_has_pipeline_name(self, seeded_session, in_memory_handler):
        """InstructionsStored carries pipeline_name."""
        pipeline, events = _run_fresh(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        for e in stored:
            assert e["pipeline_name"] == pipeline.pipeline_name

    def test_stored_has_timestamp(self, seeded_session, in_memory_handler):
        """timestamp is present and valid ISO string."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        from datetime import datetime
        for e in stored:
            assert "timestamp" in e
            assert isinstance(e["timestamp"], str)
            parsed = datetime.fromisoformat(e["timestamp"])
            assert parsed is not None


# -- Tests: InstructionsStored (Cached Path) -----------------------------------


class TestInstructionsStoredCachedPath:
    """Verify InstructionsStored emitted on cached (cache hit) path."""

    def test_stored_emitted_cached(self, seeded_session, in_memory_handler):
        """InstructionsStored emitted on second run (cache hit)."""
        _, events = _run_cached(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        assert len(stored) == 2, f"Expected 2 InstructionsStored on cached run, got {len(stored)}"

    def test_stored_instruction_count_positive_cached(self, seeded_session, in_memory_handler):
        """instruction_count >= 1 on cached path."""
        _, events = _run_cached(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        for e in stored:
            assert e["instruction_count"] >= 1, (
                f"Expected instruction_count >= 1, got {e['instruction_count']}"
            )

    def test_stored_step_name_matches_simple(self, seeded_session, in_memory_handler):
        """step_name is 'simple' on cached path (SuccessPipeline uses SimpleStep)."""
        _, events = _run_cached(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        for e in stored:
            assert e["step_name"] == "simple"

    def test_stored_has_run_id_cached(self, seeded_session, in_memory_handler):
        """InstructionsStored carries run_id from second pipeline run."""
        pipeline2, events = _run_cached(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        for e in stored:
            assert e["run_id"] == pipeline2.run_id


# -- Tests: InstructionsLogged (Fresh Path) ------------------------------------


class TestInstructionsLoggedFreshPath:
    """Verify InstructionsLogged emitted on fresh (cache miss) path."""

    def test_logged_emitted_fresh(self, seeded_session, in_memory_handler):
        """InstructionsLogged emitted for each step on fresh run."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        assert len(logged) == 2, f"Expected 2 InstructionsLogged on fresh run, got {len(logged)}"

    def test_logged_keys_equals_step_name_fresh(self, seeded_session, in_memory_handler):
        """logged_keys == [step.step_name] on fresh path."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        for e in logged:
            assert e["logged_keys"] == [e["step_name"]], (
                f"Expected logged_keys==[{e['step_name']!r}], got {e['logged_keys']!r}"
            )

    def test_logged_step_name_is_simple(self, seeded_session, in_memory_handler):
        """step_name is 'simple' for SimpleStep."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        for e in logged:
            assert e["step_name"] == "simple"

    def test_logged_has_run_id(self, seeded_session, in_memory_handler):
        """InstructionsLogged carries run_id from pipeline."""
        pipeline, events = _run_fresh(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        for e in logged:
            assert e["run_id"] == pipeline.run_id

    def test_logged_has_pipeline_name(self, seeded_session, in_memory_handler):
        """InstructionsLogged carries pipeline_name."""
        pipeline, events = _run_fresh(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        for e in logged:
            assert e["pipeline_name"] == pipeline.pipeline_name

    def test_logged_has_timestamp(self, seeded_session, in_memory_handler):
        """timestamp is present and valid ISO string."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        from datetime import datetime
        for e in logged:
            assert "timestamp" in e
            assert isinstance(e["timestamp"], str)
            parsed = datetime.fromisoformat(e["timestamp"])
            assert parsed is not None


# -- Tests: InstructionsLogged (Cached Path) -----------------------------------


class TestInstructionsLoggedCachedPath:
    """Verify InstructionsLogged emitted on cached (cache hit) path."""

    def test_logged_emitted_cached(self, seeded_session, in_memory_handler):
        """InstructionsLogged emitted on second run (cache hit)."""
        _, events = _run_cached(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        assert len(logged) == 2, f"Expected 2 InstructionsLogged on cached run, got {len(logged)}"

    def test_logged_keys_equals_step_name_cached(self, seeded_session, in_memory_handler):
        """logged_keys == [step.step_name] on cached path (CEO decision)."""
        _, events = _run_cached(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        for e in logged:
            assert e["logged_keys"] == [e["step_name"]], (
                f"Expected logged_keys==[{e['step_name']!r}], got {e['logged_keys']!r}"
            )

    def test_logged_step_name_is_simple_cached(self, seeded_session, in_memory_handler):
        """step_name is 'simple' on cached path."""
        _, events = _run_cached(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        for e in logged:
            assert e["step_name"] == "simple"

    def test_logged_has_run_id_cached(self, seeded_session, in_memory_handler):
        """InstructionsLogged carries run_id from second pipeline run."""
        pipeline2, events = _run_cached(seeded_session, in_memory_handler)
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        for e in logged:
            assert e["run_id"] == pipeline2.run_id


# -- Tests: ContextUpdated (Fresh Path) ----------------------------------------


class TestContextUpdatedFreshPath:
    """Verify ContextUpdated emitted on fresh (cache miss) path."""

    def test_ctx_updated_emitted_fresh(self, seeded_session, in_memory_handler):
        """ContextUpdated emitted for each step on fresh run."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        assert len(updated) == 2, f"Expected 2 ContextUpdated on fresh run, got {len(updated)}"

    def test_ctx_updated_new_keys_populated(self, seeded_session, in_memory_handler):
        """new_keys contains keys from SimpleContext (total)."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        # SimpleContext has field 'total'; process_instructions returns SimpleContext(total=...)
        for e in updated:
            assert "total" in e["new_keys"], (
                f"Expected 'total' in new_keys, got {e['new_keys']!r}"
            )

    def test_ctx_updated_context_snapshot_contains_merged_keys(self, seeded_session, in_memory_handler):
        """context_snapshot reflects post-merge state (contains keys from all prior steps)."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        # After second step, context_snapshot must contain 'total' (merged from both steps)
        last_update = updated[-1]
        assert "total" in last_update["context_snapshot"], (
            f"Expected 'total' in context_snapshot, got {last_update['context_snapshot']!r}"
        )

    def test_ctx_updated_new_keys_is_list(self, seeded_session, in_memory_handler):
        """new_keys is a list."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        for e in updated:
            assert isinstance(e["new_keys"], list)

    def test_ctx_updated_context_snapshot_is_dict(self, seeded_session, in_memory_handler):
        """context_snapshot is a dict."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        for e in updated:
            assert isinstance(e["context_snapshot"], dict)

    def test_ctx_updated_has_run_id(self, seeded_session, in_memory_handler):
        """ContextUpdated carries run_id from pipeline."""
        pipeline, events = _run_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        for e in updated:
            assert e["run_id"] == pipeline.run_id

    def test_ctx_updated_has_pipeline_name(self, seeded_session, in_memory_handler):
        """ContextUpdated carries pipeline_name."""
        pipeline, events = _run_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        for e in updated:
            assert e["pipeline_name"] == pipeline.pipeline_name

    def test_ctx_updated_has_timestamp(self, seeded_session, in_memory_handler):
        """timestamp is present and valid ISO string."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        from datetime import datetime
        for e in updated:
            assert "timestamp" in e
            assert isinstance(e["timestamp"], str)
            parsed = datetime.fromisoformat(e["timestamp"])
            assert parsed is not None


# -- Tests: ContextUpdated (Empty Context) -------------------------------------


class TestContextUpdatedEmptyContext:
    """Verify ContextUpdated always emits even when step returns no new context.

    CEO decision: emit with new_keys=[] when process_instructions returns None.
    Useful for tracing that _validate_and_merge_context ran.
    """

    def test_ctx_updated_emitted_on_empty_context(self, seeded_session, in_memory_handler):
        """ContextUpdated emitted even when step returns None (no context)."""
        _, events = _run_empty_ctx_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"]
        assert len(updated) == 1, (
            f"Expected 1 ContextUpdated even on empty context, got {len(updated)}"
        )

    def test_ctx_updated_new_keys_empty_on_none_return(self, seeded_session, in_memory_handler):
        """new_keys == [] when process_instructions returns None."""
        _, events = _run_empty_ctx_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"][0]
        assert updated["new_keys"] == [], (
            f"Expected new_keys==[], got {updated['new_keys']!r}"
        )

    def test_ctx_updated_context_snapshot_is_dict_on_empty(self, seeded_session, in_memory_handler):
        """context_snapshot is a dict (possibly empty) on empty-context step."""
        _, events = _run_empty_ctx_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"][0]
        assert isinstance(updated["context_snapshot"], dict)

    def test_ctx_updated_step_name_populated_on_empty(self, seeded_session, in_memory_handler):
        """step_name is populated even when context is empty."""
        _, events = _run_empty_ctx_fresh(seeded_session, in_memory_handler)
        updated = [e for e in events if e["event_type"] == "context_updated"][0]
        assert updated["step_name"] is not None
        assert updated["step_name"] == "empty_context"


# -- Tests: StateSaved (Fresh Path) --------------------------------------------


class TestStateSavedFreshPath:
    """Verify StateSaved emitted on fresh (cache miss) path."""

    def test_state_saved_emitted_fresh(self, seeded_session, in_memory_handler):
        """StateSaved emitted for each step on fresh run."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        assert len(saved) == 2, f"Expected 2 StateSaved on fresh run, got {len(saved)}"

    def test_state_saved_step_number_non_negative(self, seeded_session, in_memory_handler):
        """step_number >= 0 on fresh path."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        for e in saved:
            assert e["step_number"] >= 0, (
                f"Expected step_number >= 0, got {e['step_number']}"
            )

    def test_state_saved_input_hash_non_empty(self, seeded_session, in_memory_handler):
        """input_hash is non-empty string on fresh path."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        for e in saved:
            assert isinstance(e["input_hash"], str)
            assert len(e["input_hash"]) > 0, "input_hash must not be empty"

    def test_state_saved_execution_time_non_negative(self, seeded_session, in_memory_handler):
        """execution_time_ms >= 0.0 on fresh path."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        for e in saved:
            assert e["execution_time_ms"] >= 0.0, (
                f"Expected execution_time_ms >= 0.0, got {e['execution_time_ms']}"
            )

    def test_state_saved_execution_time_is_float(self, seeded_session, in_memory_handler):
        """execution_time_ms is float (int cast in _save_step_state)."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        for e in saved:
            assert isinstance(e["execution_time_ms"], (int, float))

    def test_state_saved_has_run_id(self, seeded_session, in_memory_handler):
        """StateSaved carries run_id from pipeline."""
        pipeline, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        for e in saved:
            assert e["run_id"] == pipeline.run_id

    def test_state_saved_has_pipeline_name(self, seeded_session, in_memory_handler):
        """StateSaved carries pipeline_name."""
        pipeline, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        for e in saved:
            assert e["pipeline_name"] == pipeline.pipeline_name

    def test_state_saved_step_name_is_simple(self, seeded_session, in_memory_handler):
        """step_name is 'simple' for SimpleStep."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        for e in saved:
            assert e["step_name"] == "simple"

    def test_state_saved_has_timestamp(self, seeded_session, in_memory_handler):
        """timestamp is present and valid ISO string."""
        _, events = _run_fresh(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        from datetime import datetime
        for e in saved:
            assert "timestamp" in e
            assert isinstance(e["timestamp"], str)
            parsed = datetime.fromisoformat(e["timestamp"])
            assert parsed is not None


# -- Tests: StateSaved NOT on Cached Path ---------------------------------------


class TestStateSavedNotOnCachedPath:
    """Verify StateSaved is NOT emitted on cached (cache hit) path.

    _save_step_state is only called from the fresh branch; cache-hit path
    reconstructs from DB without calling _save_step_state again.
    """

    def test_state_saved_absent_cached(self, seeded_session, in_memory_handler):
        """StateSaved not emitted on second run (cache hit)."""
        _, events = _run_cached(seeded_session, in_memory_handler)
        saved = [e for e in events if e["event_type"] == "state_saved"]
        assert len(saved) == 0, (
            f"Expected 0 StateSaved on cached run, got {len(saved)}: {saved!r}"
        )

    def test_other_events_still_fire_on_cached(self, seeded_session, in_memory_handler):
        """InstructionsStored and InstructionsLogged still fire on cached path."""
        _, events = _run_cached(seeded_session, in_memory_handler)
        stored = [e for e in events if e["event_type"] == "instructions_stored"]
        logged = [e for e in events if e["event_type"] == "instructions_logged"]
        assert len(stored) >= 1, "InstructionsStored should still fire on cached path"
        assert len(logged) >= 1, "InstructionsLogged should still fire on cached path"


# -- Tests: Zero Overhead (No Emitter) -----------------------------------------


class TestCtxStateZeroOverhead:
    """Verify no crash and correct behavior when event_emitter=None."""

    def test_no_events_without_emitter_fresh(self, seeded_session):
        """Pipeline with no event_emitter runs without error on fresh path."""
        provider = MockProvider(responses=[
            {"count": 5},
            {"count": 3},
        ])
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=None,
        )
        result = pipeline.execute(
            data={"input_key": "input_value"},
            initial_context={},
            use_cache=False,
        )
        assert result is not None
        assert "total" in result.context

    def test_no_events_without_emitter_cached(self, seeded_session):
        """Pipeline with no event_emitter runs without error on cached path."""
        provider1 = MockProvider(responses=[
            {"count": 5},
            {"count": 3},
        ])
        pipeline1 = SuccessPipeline(
            session=seeded_session,
            provider=provider1,
            event_emitter=None,
        )
        pipeline1.execute(
            data={"input_key": "input_value"},
            initial_context={},
            use_cache=True,
        )

        provider2 = MockProvider(responses=[])
        pipeline2 = SuccessPipeline(
            session=seeded_session,
            provider=provider2,
            event_emitter=None,
        )
        result = pipeline2.execute(
            data={"input_key": "input_value"},
            initial_context={},
            use_cache=True,
        )
        assert result is not None

    def test_no_events_without_emitter_empty_ctx(self, seeded_session):
        """EmptyContextPipeline with no event_emitter runs without error."""
        provider = MockProvider(responses=[{"count": 1}])
        pipeline = EmptyContextPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=None,
        )
        result = pipeline.execute(
            data={"input_key": "input_value"},
            initial_context={},
            use_cache=False,
        )
        assert result is not None
