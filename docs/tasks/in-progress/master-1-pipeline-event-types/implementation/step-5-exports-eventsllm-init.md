# IMPLEMENTATION - STEP 5: EXPORTS: EVENTS+LLM __INIT__
**Status:** completed

## Summary
Created events/__init__.py with categorized re-exports of all 31 event classes, base classes, LLMCallResult, category constants, and helpers. Updated llm/__init__.py to export LLMCallResult.

## Files
**Created:** none (events/__init__.py existed as stub)
**Modified:** llm_pipeline/events/__init__.py, llm_pipeline/llm/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/events/__init__.py`
Replaced single-line stub with full categorized re-exports: 2 base classes, LLMCallResult, 9 category constants, 3 helpers (_EVENT_REGISTRY, _derive_event_type, resolve_event), and 31 concrete events organized by category. __all__ has 46 entries with section comments matching llm_pipeline/__init__.py pattern.

```
# Before
"""Pipeline event system."""

# After
"""Pipeline event system - typed, immutable event dataclasses."""
# Full imports from events.types + llm.result
# resolve_event = PipelineEvent.resolve_event convenience alias
# __all__ with 46 categorized entries
```

### File: `llm_pipeline/llm/__init__.py`
Added LLMCallResult import from llm_pipeline.llm.result and added to __all__ with section comment.

```
# Before
__all__ = ["LLMProvider", "RateLimiter", "flatten_schema", "format_schema_for_llm"]

# After
__all__ = ["LLMProvider", "RateLimiter", "LLMCallResult", "flatten_schema", "format_schema_for_llm"]
```

## Decisions
### resolve_event convenience alias
**Choice:** Added `resolve_event = PipelineEvent.resolve_event` as module-level alias
**Rationale:** Plan Step 14 lists resolve_event as a helper to export. Alias provides cleaner import path (`from llm_pipeline.events import resolve_event`) vs requiring knowledge of PipelineEvent classmethod.

## Verification
[x] All 31 events importable via `from llm_pipeline.events import *`
[x] LLMCallResult importable from both llm_pipeline.events and llm_pipeline.llm
[x] _EVENT_REGISTRY contains 31 entries
[x] resolve_event callable from events package
[x] __all__ has 46 entries (2 base + 1 result + 9 constants + 3 helpers + 31 events)
[x] All 32 existing tests pass

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] _EVENT_REGISTRY and _derive_event_type exported in __all__ despite underscore-prefix (mixed signals)
[x] Verify Step 4 field additions (logged_keys on InstructionsLogged, error_type+validation_errors on ExtractionError) covered by existing exports

### Changes Made
#### File: `llm_pipeline/events/types.py`
Removed _EVENT_REGISTRY and _derive_event_type from __all__. Added comment noting they are internal and consumers should use resolve_event().

```
# Before
    "CATEGORY_STATE",
    # Pipeline Lifecycle

# After
    "CATEGORY_STATE",
    # Helpers (public only; _EVENT_REGISTRY and _derive_event_type are internal)
    # -- use PipelineEvent.resolve_event() for registry access
    # Pipeline Lifecycle
```

#### File: `llm_pipeline/events/__init__.py`
Removed _EVENT_REGISTRY and _derive_event_type from __all__. Kept imports so they remain accessible as llm_pipeline.events._EVENT_REGISTRY if needed.

```
# Before
    # Helpers
    "_EVENT_REGISTRY",
    "_derive_event_type",
    "resolve_event",

# After
    # Helpers (public only; _EVENT_REGISTRY and _derive_event_type are internal)
    "resolve_event",
```

### Verification
[x] No private symbols in events/__init__.py __all__ (was 2, now 0)
[x] No private symbols in events/types.py __all__ (was 0, confirmed)
[x] _EVENT_REGISTRY still accessible via import (31 entries)
[x] _derive_event_type still accessible via import
[x] resolve_event still in __all__
[x] events/__init__.py __all__ count: 44 (was 46, -2 private)
[x] events/types.py __all__ count: 42 (unchanged, privates were never in it -- comment added for clarity)
[x] Step 4 fields (logged_keys, error_type, validation_errors) are instance fields on already-exported classes -- no new __all__ entries needed
[x] All 32 tests pass
