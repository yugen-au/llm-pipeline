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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] InstructionsLogged has no fields beyond inherited -- added logged_keys: list[str] = field(default_factory=list)
[x] ExtractionError missing error_type and validation_errors -- added error_type: str (before error_message) and validation_errors: list[str] = field(default_factory=list)

### Changes Made
#### File: `llm_pipeline/events/types.py`
Added logged_keys field to InstructionsLogged with default empty list and mutable container docstring warning.
Added error_type (required str) before error_message and validation_errors (default empty list) to ExtractionError with mutable container docstring warning.

```
# Before - InstructionsLogged
class InstructionsLogged(StepScopedEvent):
    """Emitted when instructions are logged during step execution."""
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_INSTRUCTIONS_CONTEXT

# After - InstructionsLogged
class InstructionsLogged(StepScopedEvent):
    """Emitted when instructions are logged during step execution.
    logged_keys lists the instruction keys that were logged. Must not be
    mutated after creation (convention, not enforced at runtime).
    """
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_INSTRUCTIONS_CONTEXT
    logged_keys: list[str] = field(default_factory=list)

# Before - ExtractionError
class ExtractionError(StepScopedEvent):
    """Emitted when an extraction step fails."""
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION
    extraction_class: str
    error_message: str

# After - ExtractionError
class ExtractionError(StepScopedEvent):
    """Emitted when an extraction step fails.
    validation_errors contains Pydantic validation details if applicable.
    Must not be mutated after creation (convention, not enforced at runtime).
    """
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION
    extraction_class: str
    error_type: str
    error_message: str
    validation_errors: list[str] = field(default_factory=list)
```

### Verification
[x] InstructionsLogged instantiates with default empty logged_keys
[x] InstructionsLogged accepts logged_keys kwarg
[x] ExtractionError requires error_type as positional kwarg
[x] ExtractionError instantiates with default empty validation_errors
[x] ExtractionError accepts validation_errors kwarg
[x] Serialization round-trip works for both modified events
[x] Registry still 31 events (no new classes added)
[x] No changes needed to __all__ or __init__.py (same symbols, only fields changed)
[x] 32 existing tests pass, no regressions
