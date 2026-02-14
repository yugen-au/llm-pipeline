# IMPLEMENTATION - STEP 8: TEST CACHELOOKUP+HIT
**Status:** completed

## Summary
Added two-run CacheLookup + CacheHit integration tests to tests/events/test_cache_events.py. First run populates cache for all steps, second run verifies all steps hit cache with correct events, timestamps, and input_hash consistency.

## Files
**Created:** none
**Modified:** tests/events/test_cache_events.py
**Deleted:** none

## Changes
### File: `tests/events/test_cache_events.py`
Added `_two_run_success` helper and 4 test classes (11 tests total) between existing single-run tests and ExtractionPipeline helpers.

```python
# Helper: two-run pattern for SuccessPipeline
def _two_run_success(seeded_session, handler):
    # Run 1: populates cache (discard events via separate InMemoryEventHandler)
    # Run 2: cache hit path (capture events in provided handler)

# TestTwoRunCacheHitEmitted (3 tests)
#   - test_all_steps_hit_cache: 2 CacheHit, 0 CacheMiss on second run
#   - test_lookup_emitted_per_step: 2 CacheLookup on second run
#   - test_no_llm_calls_on_cache_hit: 0 LLM call events on cached run

# TestTwoRunCacheHitTimestamp (2 tests)
#   - test_cached_at_present: CacheHit carries cached_at as ISO string
#   - test_cached_at_before_event_timestamp: cached_at (run 1) <= event timestamp (run 2)

# TestTwoRunInputHashConsistency (2 tests)
#   - test_lookup_and_hit_share_hash: CacheLookup.input_hash == CacheHit.input_hash per step
#   - test_input_hash_is_hex: 16-char hex string

# TestTwoRunCacheHitOrdering (4 tests)
#   - test_lookup_before_hit_per_step: each CacheHit preceded by CacheLookup
#   - test_cache_sequence_on_second_run: lookup, hit, lookup, hit
#   - test_step_completed_after_each_hit: StepCompleted follows each CacheHit
#   - test_run_id_consistent_across_cache_events: all events share run_id
```

## Decisions
### cached_at type assertion
**Choice:** Assert cached_at is ISO string (not datetime), parse with `datetime.fromisoformat`
**Rationale:** InMemoryEventHandler stores events via `to_dict()` which converts datetimes to ISO strings. Testing the serialized form matches what consumers actually see.

### Timezone normalization in timestamp comparison
**Choice:** Normalize both cached_at and event timestamp to UTC-aware before comparison
**Rationale:** PipelineStepState.created_at is naive UTC, PipelineEvent.timestamp is aware UTC. After ISO deserialization, comparison requires normalization to avoid TypeError.

## Verification
[x] _two_run_success helper: run 1 populates cache, run 2 finds cache
[x] Both steps emit CacheHit on second run (2 hits, 0 misses)
[x] cached_at timestamp from first run present in CacheHit
[x] Same input_hash in CacheLookup and CacheHit per step
[x] Event ordering: lookup -> hit per step, StepCompleted after each hit
[x] No LLM call events on fully cached second run
[x] All 39 tests in test_cache_events.py pass
[x] All 113 tests in tests/events/ pass
[x] No warnings
