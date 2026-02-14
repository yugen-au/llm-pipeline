"""Integration tests for cache event emissions (CacheLookup + CacheMiss path).

Verifies CacheLookup and CacheMiss events emitted by Pipeline.execute()
when use_cache=True and no cached state exists (fresh DB).

Note: SuccessPipeline has 2 identical SimpleStep instances. Because both
produce identical prepare_calls() output, step 1 misses cache (fresh DB)
and saves state; step 2 then finds that cached state (cache hit). This
means we get 2 CacheLookup, 1 CacheMiss, 1 CacheHit per run.
"""
import pytest

from llm_pipeline.events.types import CacheLookup, CacheMiss
from conftest import MockProvider, SuccessPipeline


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
