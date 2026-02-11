# IMPLEMENTATION - STEP 1: LLMCALLRESULT + PROTOTYPE
**Status:** completed

## Summary
Created LLMCallResult frozen dataclass in llm/result.py and prototyped the frozen+slots+__init_subclass__ pattern in events/types.py with PipelineEvent base, _derive_event_type helper, _EVENT_REGISTRY, to_dict/to_json/resolve_event, and one test event (PipelineStarted). All verifications pass.

## Files
**Created:** llm_pipeline/llm/result.py, llm_pipeline/events/__init__.py, llm_pipeline/events/types.py
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/llm/result.py`
New file. Frozen+slots dataclass with 5 fields: parsed, raw_response, model_name, attempt_count, validation_errors. Docstring warns about mutable container mutation.

### File: `llm_pipeline/events/__init__.py`
Minimal package init (placeholder for Step 14 exports).

### File: `llm_pipeline/events/types.py`
New file with:
- `_derive_event_type()` helper using two-pass regex from strategy.py:189-190
- `_EVENT_REGISTRY` module-level dict for event type -> class mapping
- `PipelineEvent` base dataclass (frozen=True, slots=True) with:
  - Fields: run_id, pipeline_name, timestamp (utc_now default), event_type (init=False)
  - `__init_subclass__` auto-registering subclasses with derived event_type
  - `__post_init__` setting event_type via object.__setattr__ (frozen bypass)
  - `to_dict()` with datetime->isoformat conversion
  - `to_json()` wrapping to_dict
  - `resolve_event()` classmethod for deserialization with datetime handling
- `PipelineStarted` test event to verify the pattern

## Decisions
### No `from __future__ import annotations`
**Choice:** Removed PEP 563 import from types.py
**Rationale:** `slots=True` on @dataclass creates a new class object that replaces the original, breaking the implicit `__class__` cell that zero-arg `super()` relies on in `__init_subclass__`. With `from __future__ import annotations`, the class reference becomes a string and the closure breaks. Using explicit `super(PipelineEvent, cls)` fixes the super() call, but removing the future import entirely is cleaner and avoids other potential annotation-related edge cases with slots. String-quoted annotations used where forward references needed.

### Explicit super() in __init_subclass__
**Choice:** `super(PipelineEvent, cls).__init_subclass__(**kwargs)` instead of `super().__init_subclass__(**kwargs)`
**Rationale:** CPython `slots=True` replaces the class object, invalidating the `__class__` cell. Explicit form is the documented workaround (CPython issue #90562). Documented in code comment.

### _derived_event_type as class attribute
**Choice:** Store derived event type string on cls._derived_event_type in __init_subclass__, read in __post_init__
**Rationale:** frozen=True prevents normal attribute assignment. __post_init__ uses object.__setattr__ to set the init=False event_type field. The class attribute is set during class creation (before slots restrict instance attrs), so it's accessible.

## Verification
[x] LLMCallResult frozen=True verified (AttributeError on mutation)
[x] LLMCallResult slots=True verified (__slots__ present)
[x] PipelineEvent frozen=True verified
[x] PipelineEvent slots=True verified
[x] _EVENT_REGISTRY populated with PipelineStarted -> 'pipeline_started'
[x] event_type auto-derived correctly
[x] Two-pass regex: LLMCallStarting -> llm_call_starting
[x] Two-pass regex: PipelineStarted -> pipeline_started
[x] Two-pass regex: CacheHit -> cache_hit
[x] to_dict serializes datetime to isoformat string
[x] to_json produces valid JSON
[x] resolve_event roundtrip: serialize -> deserialize -> matching fields
[x] resolve_event raises ValueError for unknown event_type
[x] utc_now imported from llm_pipeline.state for timestamp default
