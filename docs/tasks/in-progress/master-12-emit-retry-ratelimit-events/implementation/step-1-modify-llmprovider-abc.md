# IMPLEMENTATION - STEP 1: MODIFY LLMPROVIDER ABC
**Status:** completed

## Summary
Added optional `event_emitter` and `step_name` params to LLMProvider.call_structured() abstract method signature, with docstring documentation.

## Files
**Created:** none
**Modified:** llm_pipeline/llm/provider.py
**Deleted:** none

## Changes
### File: `llm_pipeline/llm/provider.py`
Added two optional parameters after `validation_context` and before `**kwargs`, plus docstring entries.

```
# Before
        validation_context: Optional[Any] = None,
        **kwargs,

# After
        validation_context: Optional[Any] = None,
        event_emitter: Optional[Any] = None,
        step_name: Optional[str] = None,
        **kwargs,
```

Docstring additions:
```
            event_emitter: Optional EventEmitter for emitting retry/failure events
            step_name: Optional step name for event scoping
```

## Decisions
None - all decisions pre-made by CEO in PLAN.md (explicit params on ABC, Option A).

## Verification
[x] Import succeeds: `from llm_pipeline.llm.provider import LLMProvider` - OK
[x] All 189 existing tests pass (no breakage)
[x] Params are Optional with None defaults (backward compatible)
[x] **kwargs preserved after new params (existing implementations unaffected)
[x] Docstring updated with new param descriptions
[x] Param order matches PLAN.md: event_emitter, then step_name, before **kwargs

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] MEDIUM: ABC signature asymmetry - run_id and pipeline_name missing from ABC but present on GeminiProvider
[x] LOW: event_emitter typed as Optional[Any] instead of more specific type

### Changes Made
#### File: `llm_pipeline/llm/provider.py`
Added run_id and pipeline_name explicit params. Changed event_emitter type from Optional[Any] to Optional["PipelineEventEmitter"] using TYPE_CHECKING guard (no circular import - emitter.py has zero runtime llm_pipeline imports).

```
# Before (imports)
from typing import Any, List, Optional, Type

# After (imports)
from typing import TYPE_CHECKING, Any, List, Optional, Type

if TYPE_CHECKING:
    from llm_pipeline.events.emitter import PipelineEventEmitter
```

```
# Before (signature)
        event_emitter: Optional[Any] = None,
        step_name: Optional[str] = None,
        **kwargs,

# After (signature)
        event_emitter: Optional["PipelineEventEmitter"] = None,
        step_name: Optional[str] = None,
        run_id: Optional[str] = None,
        pipeline_name: Optional[str] = None,
        **kwargs,
```

```
# Before (docstring)
            event_emitter: Optional EventEmitter for emitting retry/failure events
            step_name: Optional step name for event scoping

# After (docstring)
            event_emitter: Optional PipelineEventEmitter for emitting retry/failure events
            step_name: Optional step name for event scoping
            run_id: Optional run identifier for event correlation
            pipeline_name: Optional pipeline name for event scoping
```

### Verification
[x] Import succeeds: `from llm_pipeline.llm.provider import LLMProvider` - OK
[x] No circular import: emitter.py has zero runtime imports from llm_pipeline.*
[x] TYPE_CHECKING guard keeps PipelineEventEmitter import type-only (zero runtime cost)
[x] ABC now fully symmetric with GeminiProvider: all 4 event params explicit
[x] Backward compatible: all new params Optional with None defaults, **kwargs preserved
