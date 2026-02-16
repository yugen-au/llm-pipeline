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
