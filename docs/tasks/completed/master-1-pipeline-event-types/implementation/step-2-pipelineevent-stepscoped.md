# IMPLEMENTATION - STEP 2: PIPELINEEVENT + STEPSCOPED
**Status:** completed

## Summary
Expanded prototype PipelineEvent base with 9 category constants, improved mutable-container docstring, and _skip_registry mechanism for intermediate bases. Added StepScopedEvent intermediate with optional step_name. Kept PipelineStarted as concrete event with EVENT_CATEGORY ClassVar.

## Files
**Created:** none
**Modified:** llm_pipeline/events/types.py
**Deleted:** none

## Changes
### File: `llm_pipeline/events/types.py`
Replaced prototype with full implementation. Key additions:

```
# Before
# No category constants
# __init_subclass__ only skipped underscore-prefixed classes
# No StepScopedEvent
# PipelineStarted had no EVENT_CATEGORY

# After
# 9 CATEGORY_* constants at module top
# __init_subclass__ also skips classes with _skip_registry in __dict__
# StepScopedEvent intermediate with step_name: str | None = None
# PipelineStarted has EVENT_CATEGORY ClassVar
```

Added 9 category constants: CATEGORY_PIPELINE_LIFECYCLE, CATEGORY_STEP_LIFECYCLE, CATEGORY_CACHE, CATEGORY_LLM_CALL, CATEGORY_CONSENSUS, CATEGORY_INSTRUCTIONS_CONTEXT, CATEGORY_TRANSFORMATION, CATEGORY_EXTRACTION, CATEGORY_STATE.

Added `_skip_registry` ClassVar mechanism to `__init_subclass__` - checks `cls.__dict__` (not getattr) so concrete subclasses of intermediate bases still register.

Improved PipelineEvent docstring: clarified frozen prevents reassignment but not container mutation.

Added StepScopedEvent with `_skip_registry: ClassVar[bool] = True` and `step_name: str | None = None`.

Added `EVENT_CATEGORY: ClassVar[str]` to PipelineStarted.

## Decisions
### _skip_registry via __dict__ check
**Choice:** Use `"_skip_registry" in cls.__dict__` instead of `getattr(cls, "_skip_registry", False)`
**Rationale:** getattr would inherit the flag to concrete subclasses, preventing their registration. __dict__ check ensures only the class that directly declares _skip_registry is skipped.

### StepScopedEvent naming (not underscore-prefixed)
**Choice:** Public name `StepScopedEvent` with `_skip_registry` ClassVar instead of `_StepScopedEvent`
**Rationale:** StepScopedEvent is part of public API (isinstance checks, type hints). Underscore prefix would signal private/internal. _skip_registry is the correct mechanism for public intermediate bases.

## Verification
[x] 9 category constants defined and importable
[x] StepScopedEvent excluded from _EVENT_REGISTRY
[x] Concrete subclasses of StepScopedEvent register correctly
[x] step_name defaults to None
[x] PipelineStarted has EVENT_CATEGORY = CATEGORY_PIPELINE_LIFECYCLE
[x] Serialization round-trip works
[x] Frozen + slots enforced on all classes
[x] isinstance chain: concrete -> StepScopedEvent -> PipelineEvent
[x] Two-pass regex handles LLM-prefixed names correctly
[x] All 32 existing tests pass
