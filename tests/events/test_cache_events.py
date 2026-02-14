"""Integration tests for cache event emissions.

Verifies CacheLookup, CacheMiss, CacheHit, and CacheReconstruction events
emitted by Pipeline.execute() via InMemoryEventHandler.

Note: SuccessPipeline has 2 identical SimpleStep instances. Because both
produce identical prepare_calls() output, step 1 misses cache (fresh DB)
and saves state; step 2 then finds that cached state (cache hit). This
means we get 2 CacheLookup, 1 CacheMiss, 1 CacheHit per run.
"""
import pytest

from llm_pipeline.events.types import CacheLookup, CacheMiss, CacheHit, CacheReconstruction
from llm_pipeline.events.handlers import InMemoryEventHandler
from conftest import MockProvider, SuccessPipeline, ExtractionPipeline


# -- Helpers -------------------------------------------------------------------


def _run_pipeline_with_cache(seeded_session, handler):
    """Execute SuccessPipeline with use_cache=True on fresh DB."""
    provider = MockProvider(responses=[
        {"count": 1, "notes": "first"},
        {"count": 2, "notes": "second"},
    ])
    pipeline = SuccessPipeline(
        session=seeded_session,
        provider=provider,
        event_emitter=handler,
    )
    pipeline.execute(data="test data", initial_context={}, use_cache=True)
    return pipeline, handler.get_events()


# -- Tests: CacheLookup -------------------------------------------------------


class TestCacheLookupEmitted:
    """Verify CacheLookup emitted for each step when use_cache=True."""

    def test_lookup_emitted_per_step(self, seeded_session, in_memory_handler):
        """CacheLookup emitted once per step (2 steps in SuccessPipeline)."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        assert len(lookups) == 2, "Expected 2 CacheLookup (one per step)"

    def test_lookup_has_input_hash(self, seeded_session, in_memory_handler):
        """input_hash is a non-empty string in CacheLookup."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        for lk in lookups:
            assert isinstance(lk["input_hash"], str)
            assert len(lk["input_hash"]) > 0

    def test_lookup_has_run_id(self, seeded_session, in_memory_handler):
        """CacheLookup carries run_id from pipeline."""
        pipeline, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        for lk in lookups:
            assert lk["run_id"] == pipeline.run_id

    def test_lookup_has_pipeline_name(self, seeded_session, in_memory_handler):
        """CacheLookup carries pipeline_name."""
        pipeline, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        for lk in lookups:
            assert lk["pipeline_name"] == pipeline.pipeline_name

    def test_lookup_step_name(self, seeded_session, in_memory_handler):
        """step_name is 'simple' for SimpleStep."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        for lk in lookups:
            assert lk["step_name"] == "simple"


# -- Tests: CacheMiss ---------------------------------------------------------


class TestCacheMissEmitted:
    """Verify CacheMiss emitted when cache has no matching state.

    With 2 identical SimpleSteps, step 1 misses (fresh DB) and step 2
    hits (state saved by step 1). So exactly 1 CacheMiss per run.
    """

    def test_miss_emitted_on_fresh_db(self, seeded_session, in_memory_handler):
        """CacheMiss emitted once (first step) on fresh DB."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        misses = [e for e in events if e["event_type"] == "cache_miss"]
        assert len(misses) == 1, "Expected 1 CacheMiss (first step only; second hits cache)"

    def test_miss_has_input_hash(self, seeded_session, in_memory_handler):
        """input_hash is a non-empty string in CacheMiss."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        misses = [e for e in events if e["event_type"] == "cache_miss"]
        for m in misses:
            assert isinstance(m["input_hash"], str)
            assert len(m["input_hash"]) > 0

    def test_miss_has_run_id(self, seeded_session, in_memory_handler):
        """CacheMiss carries run_id from pipeline."""
        pipeline, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        misses = [e for e in events if e["event_type"] == "cache_miss"]
        for m in misses:
            assert m["run_id"] == pipeline.run_id

    def test_miss_has_pipeline_name(self, seeded_session, in_memory_handler):
        """CacheMiss carries pipeline_name."""
        pipeline, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        misses = [e for e in events if e["event_type"] == "cache_miss"]
        for m in misses:
            assert m["pipeline_name"] == pipeline.pipeline_name

    def test_miss_step_name(self, seeded_session, in_memory_handler):
        """step_name is 'simple' for SimpleStep."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        misses = [e for e in events if e["event_type"] == "cache_miss"]
        for m in misses:
            assert m["step_name"] == "simple"


# -- Tests: input_hash consistency --------------------------------------------


class TestCacheEventInputHashConsistency:
    """Verify input_hash present and consistent across cache events."""

    def test_first_lookup_miss_hash_matches(self, seeded_session, in_memory_handler):
        """First CacheLookup.input_hash == CacheMiss.input_hash (same step)."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        misses = [e for e in events if e["event_type"] == "cache_miss"]
        assert len(misses) >= 1
        assert lookups[0]["input_hash"] == misses[0]["input_hash"], (
            "input_hash should match between CacheLookup and CacheMiss for same step"
        )

    def test_input_hash_is_hex_string(self, seeded_session, in_memory_handler):
        """input_hash is a 16-char hex string (sha256[:16])."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        cache_events = [
            e for e in events
            if e["event_type"] in ("cache_lookup", "cache_miss")
        ]
        for e in cache_events:
            h = e["input_hash"]
            assert len(h) == 16, f"Expected 16-char hash, got {len(h)}"
            assert all(c in "0123456789abcdef" for c in h), "Expected hex string"

    def test_all_cache_events_share_input_hash(self, seeded_session, in_memory_handler):
        """All cache events from identical steps share the same input_hash."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        cache_events = [
            e for e in events
            if e["event_type"] in ("cache_lookup", "cache_miss", "cache_hit")
        ]
        hashes = {e["input_hash"] for e in cache_events}
        assert len(hashes) == 1, "Identical steps should produce identical input_hash"


# -- Tests: Ordering -----------------------------------------------------------


class TestCacheEventOrdering:
    """Verify CacheLookup always precedes CacheMiss/CacheHit in event stream."""

    def test_lookup_before_miss(self, seeded_session, in_memory_handler):
        """CacheLookup appears before CacheMiss in the event stream."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        types = [e["event_type"] for e in events]
        lookup_idx = types.index("cache_lookup")
        miss_idx = types.index("cache_miss")
        assert lookup_idx < miss_idx, "CacheLookup must precede CacheMiss"

    def test_cache_event_sequence(self, seeded_session, in_memory_handler):
        """Cache events follow: lookup, miss (step 1), lookup, hit (step 2)."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        cache_events = [
            e for e in events
            if e["event_type"] in ("cache_lookup", "cache_miss", "cache_hit")
        ]
        assert len(cache_events) == 4
        assert cache_events[0]["event_type"] == "cache_lookup"
        assert cache_events[1]["event_type"] == "cache_miss"
        assert cache_events[2]["event_type"] == "cache_lookup"
        assert cache_events[3]["event_type"] == "cache_hit"

    def test_lookup_timestamp_before_miss(self, seeded_session, in_memory_handler):
        """First CacheLookup.timestamp <= CacheMiss.timestamp."""
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        misses = [e for e in events if e["event_type"] == "cache_miss"]
        assert lookups[0]["timestamp"] <= misses[0]["timestamp"]


# -- Tests: No emitter (zero overhead) ----------------------------------------


class TestCacheEventsNoEmitter:
    """Verify no crash and no events when event_emitter=None."""

    def test_no_events_without_emitter(self, seeded_session):
        """Pipeline with use_cache=True but no event_emitter runs without error."""
        provider = MockProvider(responses=[
            {"count": 1, "notes": "first"},
            {"count": 2, "notes": "second"},
        ])
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=None,
        )
        result = pipeline.execute(data="test data", initial_context={}, use_cache=True)
        assert result is not None
        # Step 2 hits cache from step 1's saved state (count=1), so total=1
        assert result.context["total"] == 1


# -- Tests: No cache events when use_cache=False -------------------------------


class TestNoCacheEventsWithoutCacheFlag:
    """Verify no cache events emitted when use_cache=False (default)."""

    def test_no_cache_events_default(self, seeded_session, in_memory_handler):
        """No CacheLookup/CacheMiss when use_cache=False (default)."""
        provider = MockProvider(responses=[
            {"count": 1, "notes": "first"},
            {"count": 2, "notes": "second"},
        ])
        pipeline = SuccessPipeline(
            session=seeded_session,
            provider=provider,
            event_emitter=in_memory_handler,
        )
        pipeline.execute(data="test data", initial_context={})
        events = in_memory_handler.get_events()
        cache_events = [
            e for e in events
            if e["event_type"] in ("cache_lookup", "cache_miss", "cache_hit")
        ]
        assert len(cache_events) == 0, "No cache events when use_cache=False"


# -- Helpers: Two-run CacheHit (SuccessPipeline) --------------------------------


def _two_run_success(seeded_session, handler):
    """Run SuccessPipeline twice: run 1 populates cache, run 2 hits cache.

    Returns (pipeline2, events2) from the second run only.
    """
    responses = [
        {"count": 1, "notes": "first"},
        {"count": 2, "notes": "second"},
    ]

    # Run 1: populates cache (discard events)
    provider1 = MockProvider(responses=list(responses))
    pipeline1 = SuccessPipeline(
        session=seeded_session,
        provider=provider1,
        event_emitter=InMemoryEventHandler(),  # discard run-1 events
    )
    pipeline1.execute(data="test data", initial_context={}, use_cache=True)

    # Run 2: cache hit path (capture events)
    provider2 = MockProvider(responses=[])  # no LLM calls expected
    pipeline2 = SuccessPipeline(
        session=seeded_session,
        provider=provider2,
        event_emitter=handler,
    )
    pipeline2.execute(data="test data", initial_context={}, use_cache=True)
    return pipeline2, handler.get_events()


# -- Tests: Two-run CacheLookup + CacheHit ------------------------------------


class TestTwoRunCacheHitEmitted:
    """Verify CacheLookup + CacheHit on second run (all steps hit cache)."""

    def test_all_steps_hit_cache(self, seeded_session, in_memory_handler):
        """Both steps emit CacheHit on second run (no CacheMiss)."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        hits = [e for e in events if e["event_type"] == "cache_hit"]
        misses = [e for e in events if e["event_type"] == "cache_miss"]
        assert len(hits) == 2, f"Expected 2 CacheHit events, got {len(hits)}"
        assert len(misses) == 0, f"Expected 0 CacheMiss events, got {len(misses)}"

    def test_lookup_emitted_per_step(self, seeded_session, in_memory_handler):
        """CacheLookup emitted once per step on second run."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        assert len(lookups) == 2

    def test_no_llm_calls_on_cache_hit(self, seeded_session, in_memory_handler):
        """No LLM call events on fully cached run."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        llm_events = [
            e for e in events
            if e["event_type"] in ("llm_call_prepared", "llm_call_starting", "llm_call_completed")
        ]
        assert len(llm_events) == 0


class TestTwoRunCacheHitTimestamp:
    """Verify cached_at timestamp from first run is present in CacheHit."""

    def test_cached_at_present(self, seeded_session, in_memory_handler):
        """CacheHit carries cached_at as ISO string (serialized by to_dict)."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        hits = [e for e in events if e["event_type"] == "cache_hit"]
        for h in hits:
            assert "cached_at" in h
            assert isinstance(h["cached_at"], str)
            # Verify it's a valid ISO datetime string
            from datetime import datetime
            parsed = datetime.fromisoformat(h["cached_at"])
            assert parsed is not None

    def test_cached_at_before_event_timestamp(self, seeded_session, in_memory_handler):
        """cached_at (from run 1) precedes event timestamp (from run 2)."""
        from datetime import datetime, timezone
        _, events = _two_run_success(seeded_session, in_memory_handler)
        hits = [e for e in events if e["event_type"] == "cache_hit"]
        for h in hits:
            cached_at = datetime.fromisoformat(h["cached_at"])
            event_ts = datetime.fromisoformat(h["timestamp"])
            # Normalize both to UTC-aware for comparison
            if cached_at.tzinfo is None:
                cached_at = cached_at.replace(tzinfo=timezone.utc)
            if event_ts.tzinfo is None:
                event_ts = event_ts.replace(tzinfo=timezone.utc)
            assert cached_at <= event_ts, (
                f"cached_at ({cached_at}) should be <= event timestamp ({event_ts})"
            )


class TestTwoRunInputHashConsistency:
    """Verify same input_hash in CacheLookup and CacheHit on second run."""

    def test_lookup_and_hit_share_hash(self, seeded_session, in_memory_handler):
        """CacheLookup.input_hash == CacheHit.input_hash for each step."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        lookups = [e for e in events if e["event_type"] == "cache_lookup"]
        hits = [e for e in events if e["event_type"] == "cache_hit"]
        assert len(lookups) == len(hits)
        for lk, h in zip(lookups, hits):
            assert lk["input_hash"] == h["input_hash"], (
                f"CacheLookup hash ({lk['input_hash']}) != CacheHit hash ({h['input_hash']})"
            )

    def test_input_hash_is_hex(self, seeded_session, in_memory_handler):
        """input_hash is a 16-char hex string in CacheHit events."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        hits = [e for e in events if e["event_type"] == "cache_hit"]
        for h in hits:
            assert len(h["input_hash"]) == 16
            assert all(c in "0123456789abcdef" for c in h["input_hash"])


class TestTwoRunCacheHitOrdering:
    """Verify event ordering on fully cached second run."""

    def test_lookup_before_hit_per_step(self, seeded_session, in_memory_handler):
        """Each CacheHit is preceded by a CacheLookup."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        types = [e["event_type"] for e in events]
        for i, t in enumerate(types):
            if t == "cache_hit":
                assert "cache_lookup" in types[:i], (
                    f"CacheHit at index {i} has no preceding CacheLookup"
                )

    def test_cache_sequence_on_second_run(self, seeded_session, in_memory_handler):
        """Second run: lookup, hit (step 1), lookup, hit (step 2)."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        cache_events = [
            e for e in events
            if e["event_type"] in ("cache_lookup", "cache_miss", "cache_hit")
        ]
        assert len(cache_events) == 4
        assert cache_events[0]["event_type"] == "cache_lookup"
        assert cache_events[1]["event_type"] == "cache_hit"
        assert cache_events[2]["event_type"] == "cache_lookup"
        assert cache_events[3]["event_type"] == "cache_hit"

    def test_step_completed_after_each_hit(self, seeded_session, in_memory_handler):
        """StepCompleted emitted after each CacheHit."""
        _, events = _two_run_success(seeded_session, in_memory_handler)
        types = [e["event_type"] for e in events]
        for i, t in enumerate(types):
            if t == "cache_hit":
                assert "step_completed" in types[i + 1:], (
                    f"CacheHit at index {i} has no following StepCompleted"
                )

    def test_run_id_consistent_across_cache_events(self, seeded_session, in_memory_handler):
        """All cache events share the same run_id on second run."""
        pipeline, events = _two_run_success(seeded_session, in_memory_handler)
        cache_events = [
            e for e in events
            if e["event_type"] in ("cache_lookup", "cache_hit")
        ]
        for e in cache_events:
            assert e["run_id"] == pipeline.run_id


# -- Helpers: ExtractionPipeline -----------------------------------------------


def _run_extraction_pipeline(seeded_session, handler):
    """Execute ExtractionPipeline with use_cache=True on fresh DB (cache miss).

    Returns (pipeline, events).
    """
    provider = MockProvider(responses=[
        {"item_count": 3, "category": "widgets", "notes": "ok"},
    ])
    pipeline = ExtractionPipeline(
        session=seeded_session,
        provider=provider,
        event_emitter=handler,
    )
    pipeline.execute(data="test data", initial_context={}, use_cache=True)
    return pipeline, handler.get_events()


def _two_run_extraction(seeded_session, handler):
    """Run ExtractionPipeline twice: run 1 populates cache, run 2 hits cache.

    Returns (pipeline2, events2) from the second run only.
    """
    # Run 1: cache miss, saves state + extractions
    provider1 = MockProvider(responses=[
        {"item_count": 3, "category": "widgets", "notes": "ok"},
    ])
    pipeline1 = ExtractionPipeline(
        session=seeded_session,
        provider=provider1,
        event_emitter=InMemoryEventHandler(),  # discard run-1 events
    )
    pipeline1.execute(data="test data", initial_context={}, use_cache=True)
    pipeline1.save()  # persist instances + PipelineRunInstance records for reconstruction

    # Run 2: cache hit, reconstructs extractions
    provider2 = MockProvider(responses=[])  # no LLM calls expected
    pipeline2 = ExtractionPipeline(
        session=seeded_session,
        provider=provider2,
        event_emitter=handler,
    )
    pipeline2.execute(data="test data", initial_context={}, use_cache=True)
    return pipeline2, handler.get_events()


# -- Tests: CacheReconstruction -----------------------------------------------


class TestCacheReconstructionEmitted:
    """Verify CacheReconstruction emitted after CacheHit when step has extractions."""

    def test_reconstruction_emitted_on_cache_hit(self, seeded_session, in_memory_handler):
        """CacheReconstruction emitted once on second run (cache hit path)."""
        _, events = _two_run_extraction(seeded_session, in_memory_handler)
        recons = [e for e in events if e["event_type"] == "cache_reconstruction"]
        assert len(recons) == 1, "Expected 1 CacheReconstruction on cache-hit run"

    def test_reconstruction_model_count(self, seeded_session, in_memory_handler):
        """model_count = len(step_def.extractions) = 1 (ItemExtraction only)."""
        _, events = _two_run_extraction(seeded_session, in_memory_handler)
        recon = [e for e in events if e["event_type"] == "cache_reconstruction"][0]
        assert recon["model_count"] == 1, "ExtractionPipeline has 1 extraction class"

    def test_reconstruction_instance_count(self, seeded_session, in_memory_handler):
        """instance_count = 3 (ItemExtraction creates 3 items from item_count=3)."""
        _, events = _two_run_extraction(seeded_session, in_memory_handler)
        recon = [e for e in events if e["event_type"] == "cache_reconstruction"][0]
        assert recon["instance_count"] == 3, "Expected 3 reconstructed Item instances"

    def test_reconstruction_has_run_id(self, seeded_session, in_memory_handler):
        """CacheReconstruction carries run_id from pipeline."""
        pipeline, events = _two_run_extraction(seeded_session, in_memory_handler)
        recon = [e for e in events if e["event_type"] == "cache_reconstruction"][0]
        assert recon["run_id"] == pipeline.run_id

    def test_reconstruction_has_step_name(self, seeded_session, in_memory_handler):
        """step_name is 'item_detection' for ItemDetectionStep."""
        _, events = _two_run_extraction(seeded_session, in_memory_handler)
        recon = [e for e in events if e["event_type"] == "cache_reconstruction"][0]
        assert recon["step_name"] == "item_detection"


class TestCacheReconstructionNotEmittedWithoutExtractions:
    """Verify CacheReconstruction NOT emitted when step has no extractions."""

    def test_no_reconstruction_for_simple_pipeline(self, seeded_session, in_memory_handler):
        """SuccessPipeline has no extractions; CacheReconstruction must not appear."""
        # SuccessPipeline: 2 identical SimpleSteps, step 2 hits cache from step 1
        _, events = _run_pipeline_with_cache(seeded_session, in_memory_handler)
        recons = [e for e in events if e["event_type"] == "cache_reconstruction"]
        assert len(recons) == 0, "No CacheReconstruction when step has no extractions"

    def test_no_reconstruction_on_cache_miss(self, seeded_session, in_memory_handler):
        """CacheReconstruction not emitted on cache-miss path (fresh ExtractionPipeline)."""
        _, events = _run_extraction_pipeline(seeded_session, in_memory_handler)
        recons = [e for e in events if e["event_type"] == "cache_reconstruction"]
        assert len(recons) == 0, "No CacheReconstruction on first run (cache miss)"


class TestCacheReconstructionOrdering:
    """Verify CacheHit -> CacheReconstruction -> StepCompleted ordering."""

    def test_hit_before_reconstruction(self, seeded_session, in_memory_handler):
        """CacheHit appears before CacheReconstruction in event stream."""
        _, events = _two_run_extraction(seeded_session, in_memory_handler)
        types = [e["event_type"] for e in events]
        hit_idx = types.index("cache_hit")
        recon_idx = types.index("cache_reconstruction")
        assert hit_idx < recon_idx, "CacheHit must precede CacheReconstruction"

    def test_reconstruction_before_step_completed(self, seeded_session, in_memory_handler):
        """CacheReconstruction appears before StepCompleted in event stream."""
        _, events = _two_run_extraction(seeded_session, in_memory_handler)
        types = [e["event_type"] for e in events]
        recon_idx = types.index("cache_reconstruction")
        completed_idx = types.index("step_completed")
        assert recon_idx < completed_idx, "CacheReconstruction must precede StepCompleted"

    def test_full_cache_hit_sequence(self, seeded_session, in_memory_handler):
        """Full sequence: CacheLookup -> CacheHit -> CacheReconstruction -> StepCompleted."""
        _, events = _two_run_extraction(seeded_session, in_memory_handler)
        relevant = [
            e for e in events
            if e["event_type"] in (
                "cache_lookup", "cache_hit", "cache_reconstruction", "step_completed",
            )
        ]
        types = [e["event_type"] for e in relevant]
        assert types[0] == "cache_lookup"
        assert types[1] == "cache_hit"
        assert types[2] == "cache_reconstruction"
        assert types[3] == "step_completed"
