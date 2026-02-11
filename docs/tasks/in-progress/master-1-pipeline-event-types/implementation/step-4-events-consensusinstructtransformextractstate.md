# IMPLEMENTATION - STEP 4: EVENTS: CONSENSUS+INSTRUCT+TRANSFORM+EXTRACT+STATE
**Status:** completed

## Summary
Added 13 event dataclasses across 5 categories (Consensus 4, Instructions & Context 3, Transformation 2, Extraction 3, State 1) to types.py. All use frozen+slots pattern, inherit StepScopedEvent, auto-register via __init_subclass__. Updated __all__ exports. Registry now contains 31 total events.

## Files
**Created:** none
**Modified:** llm_pipeline/events/types.py
**Deleted:** none

## Changes
### File: `llm_pipeline/events/types.py`
Appended 13 event dataclasses after LLM Call section with section header comments per category. Updated __all__ list with all new exports.

```
# Before
# File ended after LLMCallRateLimited and __all__ with 18 events

# After
# Added 5 new sections after LLM Call Events:
# -- Consensus Events (ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed)
# -- Instructions & Context Events (InstructionsStored, InstructionsLogged, ContextUpdated)
# -- Transformation Events (TransformationStarting, TransformationCompleted)
# -- Extraction Events (ExtractionStarting, ExtractionCompleted, ExtractionError)
# -- State Events (StateSaved)
# __all__ updated with all 13 new event names in categorized sections
```

## Decisions
### Field names follow task spec over PLAN.md
**Choice:** Used field names from task description (e.g. threshold, max_calls, group_count) rather than PLAN.md step descriptions (e.g. num_calls, responses)
**Rationale:** Task description represents refined/final spec; PLAN.md was earlier planning phase with different field names

### ContextUpdated mutable container docstring
**Choice:** Added explicit mutable container warning on ContextUpdated (new_keys: list, context_snapshot: dict)
**Rationale:** Follows PipelineEvent base docstring convention; these are the only new events with mutable containers

## Verification
[x] All 31 events in _EVENT_REGISTRY (was 18, added 13)
[x] All new events: frozen=True, slots=True, kw_only=True
[x] All new events inherit StepScopedEvent
[x] EVENT_CATEGORY ClassVar set on all new events using correct CATEGORY_* constants
[x] event_type auto-derived correctly (e.g. consensus_started, state_saved)
[x] Serialization round-trip via to_dict/resolve_event works
[x] __all__ updated with all 13 new exports
[x] 32 existing tests pass, no regressions
