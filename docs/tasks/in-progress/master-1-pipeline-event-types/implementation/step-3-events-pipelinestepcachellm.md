# IMPLEMENTATION - STEP 3: EVENTS: PIPELINE+STEP+CACHE+LLM
**Status:** completed

## Summary
Added 17 concrete event dataclasses (PipelineCompleted, PipelineError, 5 Step Lifecycle, 4 Cache, 6 LLM Call) to types.py. PipelineStarted already existed. All use `@dataclass(frozen=True, slots=True, kw_only=True)` and auto-register via `__init_subclass__`. Added `__all__` exports list.

## Files
**Created:** none
**Modified:** llm_pipeline/events/types.py
**Deleted:** none

## Changes
### File: `llm_pipeline/events/types.py`
Added 17 event dataclasses after existing PipelineStarted, plus `__all__` list.

```
# Before
PipelineStarted(PipelineEvent) - only concrete event

# After
Pipeline Lifecycle: PipelineStarted, PipelineCompleted, PipelineError
Step Lifecycle: StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted
Cache: CacheLookup, CacheHit, CacheMiss, CacheReconstruction
LLM Call: LLMCallPrepared, LLMCallStarting, LLMCallCompleted, LLMCallRetry, LLMCallFailed, LLMCallRateLimited
```

## Decisions
### kw_only=True on all subclasses with required fields
**Choice:** Added `kw_only=True` to dataclass decorator on all subclasses that define required (non-default) fields
**Rationale:** PipelineEvent.timestamp has `default_factory=utc_now`. Python dataclass inheritance requires non-default fields cannot follow default fields. `kw_only=True` resolves this by making all subclass fields keyword-only, bypassing the ordering constraint. All events must be constructed with keyword arguments.

### PipelineStarted kept as-is (no kw_only)
**Choice:** PipelineStarted has no subclass-specific fields, so no kw_only needed
**Rationale:** Only inherits PipelineEvent fields, no ordering conflict

## Verification
[x] All 18 events register in _EVENT_REGISTRY with correct snake_case keys
[x] All events have __slots__ (slots=True verified)
[x] Frozen immutability works (AttributeError on reassignment)
[x] EVENT_CATEGORY ClassVar correct per category
[x] Serialization round-trip (to_dict -> resolve_event) works
[x] CacheHit.cached_at datetime serialization/deserialization works
[x] LLMCallCompleted.validation_errors defaults to empty list
[x] StepSelecting.step_name defaults to None
[x] PipelineError.traceback defaults to None
[x] __all__ list contains all 18 events + bases + category constants
