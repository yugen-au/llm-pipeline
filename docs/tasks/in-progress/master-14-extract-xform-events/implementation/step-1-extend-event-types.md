# IMPLEMENTATION - STEP 1: EXTEND EVENT TYPES
**Status:** completed

## Summary
Added three fields to event type dataclasses: `execution_time_ms: float` to ExtractionCompleted, `cached: bool` to TransformationStarting and TransformationCompleted.

## Files
**Created:** none
**Modified:** llm_pipeline/events/types.py
**Deleted:** none

## Changes
### File: `llm_pipeline/events/types.py`
Added fields to three frozen dataclass event types to support extraction/transformation event emission in subsequent steps.

```python
# Before - TransformationStarting (L465-471)
class TransformationStarting(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TRANSFORMATION
    transformation_class: str

# After
class TransformationStarting(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TRANSFORMATION
    transformation_class: str
    cached: bool
```

```python
# Before - TransformationCompleted (L475-482)
class TransformationCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TRANSFORMATION
    data_key: str
    execution_time_ms: float

# After
class TransformationCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TRANSFORMATION
    data_key: str
    execution_time_ms: float
    cached: bool
```

```python
# Before - ExtractionCompleted (L499-506)
class ExtractionCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION
    extraction_class: str
    model_class: str
    instance_count: int

# After
class ExtractionCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION
    extraction_class: str
    model_class: str
    instance_count: int
    execution_time_ms: float
```

## Decisions
None -- all three additions follow established patterns in existing event types.

## Verification
- [x] All 149 existing event tests pass (pytest tests/events/ -x -q)
- [x] Fields added as kw_only (inherited from class decorator) matching existing pattern
- [x] No default values needed -- all fields required at construction time
- [x] execution_time_ms on ExtractionCompleted matches same field on TransformationCompleted and StepCompleted
- [x] cached: bool on both Transformation events enables cached/fresh path distinction
