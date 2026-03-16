# IMPLEMENTATION - STEP 5: TOOL CALL EVENT TYPES
**Status:** completed

## Summary
Added `CATEGORY_TOOL_CALL` constant and two new frozen dataclass event types (`ToolCallStarting`, `ToolCallCompleted`) to the pipeline event system. Both auto-register via `__init_subclass__` and are exported from `llm_pipeline.events`.

## Files
**Created:** none
**Modified:** `llm_pipeline/events/types.py`, `llm_pipeline/events/__init__.py`, `tests/events/test_event_types.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/events/types.py`
Added `CATEGORY_TOOL_CALL = "tool_call"` after existing category constants. Added two new event dataclasses after the State Events section. Added all three symbols to `__all__`.

```python
# Before
CATEGORY_STATE = "state"

# After
CATEGORY_STATE = "state"
CATEGORY_TOOL_CALL = "tool_call"
```

```python
# Added after StateSaved
@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallStarting(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TOOL_CALL
    tool_name: str
    tool_args: dict[str, Any]
    call_index: int

@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TOOL_CALL
    tool_name: str
    result_preview: str | None
    execution_time_ms: float
    call_index: int
    error: str | None = None
```

### File: `llm_pipeline/events/__init__.py`
Added `CATEGORY_TOOL_CALL`, `ToolCallStarting`, `ToolCallCompleted` to both the import block and `__all__`.

### File: `tests/events/test_event_types.py`
Updated registry count assertion from 31 to 33. Added two tool call fixtures to `EVENT_FIXTURES` for full round-trip parametrized coverage. Updated docstring and comment to reflect 33 events.

## Decisions
### ToolCallCompleted.error as optional field with default None
**Choice:** `error: str | None = None` as last field (after required fields)
**Rationale:** Follows same pattern as other events with optional trailing fields. Default None means success path doesn't need to specify error. Dataclass field ordering requires defaults after non-defaults.

## Verification
[x] Both events auto-register in _EVENT_REGISTRY (33 total, includes tool_call_starting and tool_call_completed)
[x] _derive_event_type correctly produces tool_call_starting / tool_call_completed from class names
[x] Round-trip serialization (to_dict -> resolve_event) works for both events
[x] All 169 event type tests pass
[x] All 384 event tests pass (no regressions)
[x] Frozen dataclass pattern matches existing events (frozen=True, slots=True, kw_only=True)
[x] StepScopedEvent inheritance gives run_id, pipeline_name, timestamp, step_name

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] MEDIUM - Stale comment line 32 said "All 31 concrete event classes" but registry has 33; updated to 33
[x] LOW - EXPECTED_CATEGORIES dict missing tool_call_starting and tool_call_completed entries; added both with CATEGORY_TOOL_CALL

### Changes Made
#### File: `tests/events/test_event_types.py`
Updated stale import comment from 31 to 33, added CATEGORY_TOOL_CALL import, added two entries to EXPECTED_CATEGORIES dict.

```python
# Before (line 32)
    # All 31 concrete event classes

# After
    # All 33 concrete event classes
```

```python
# Before (line 206-207)
    "state_saved": CATEGORY_STATE,
}

# After
    "state_saved": CATEGORY_STATE,
    "tool_call_starting": CATEGORY_TOOL_CALL,
    "tool_call_completed": CATEGORY_TOOL_CALL,
}
```

### Verification
[x] All 171 event type tests pass (up from 169; 2 new category parametrized tests)
[x] tool_call_starting category verified as CATEGORY_TOOL_CALL
[x] tool_call_completed category verified as CATEGORY_TOOL_CALL
