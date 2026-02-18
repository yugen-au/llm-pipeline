# IMPLEMENTATION - STEP 2: EXPORT FROM EVENTS/__INIT__
**Status:** completed

## Summary
Added `PipelineEventRecord` import and `__all__` export to `llm_pipeline/events/__init__.py` so the model is accessible via `from llm_pipeline.events import PipelineEventRecord`.

## Files
**Created:** none
**Modified:** llm_pipeline/events/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/events/__init__.py`
Added import of `PipelineEventRecord` from `llm_pipeline.events.models` after the emitter import line. Added `"PipelineEventRecord"` to `__all__` under a new `# DB Models` comment grouping between `"StepScopedEvent"` and `# Emitters`.

```
# Before
from llm_pipeline.events.emitter import CompositeEmitter, PipelineEventEmitter
from llm_pipeline.llm.result import LLMCallResult

# After
from llm_pipeline.events.emitter import CompositeEmitter, PipelineEventEmitter
from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.llm.result import LLMCallResult
```

```
# Before (__all__)
    # Base Classes
    "PipelineEvent",
    "StepScopedEvent",
    # Emitters

# After (__all__)
    # Base Classes
    "PipelineEvent",
    "StepScopedEvent",
    # DB Models
    "PipelineEventRecord",
    # Emitters
```

## Decisions
### Placement of DB Models grouping
**Choice:** New `# DB Models` comment section between Base Classes and Emitters in `__all__`
**Rationale:** PLAN.md suggested either under Base Classes or a new DB Models grouping. Separate grouping is cleaner since PipelineEventRecord is a SQLModel table, not an event dataclass.

## Verification
[x] `from llm_pipeline.events import PipelineEventRecord` resolves without error
[x] `"PipelineEventRecord"` present in `llm_pipeline.events.__all__`
