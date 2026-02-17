# IMPLEMENTATION - STEP 1: ADD EVENT IMPORTS
**Status:** completed

## Summary
Added 4 new event type imports (InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved) to the `from llm_pipeline.events.types import (...)` block in pipeline.py. These are prerequisites for Steps 2-7 which add emission blocks.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Added 4 event types to the existing import block at L35-43, after TransformationCompleted, following the established grouping pattern.

```
# Before (L41-42)
    TransformationStarting, TransformationCompleted,
)

# After (L41-43)
    TransformationStarting, TransformationCompleted,
    InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved,
)
```

## Decisions
None

## Verification
- [x] All 4 types exist in events/types.py (confirmed via grep)
- [x] All 4 types present in runtime import block (confirmed via AST parse)
- [x] pipeline.py syntax valid (confirmed via ast.parse)
- [x] Import grouping follows existing pattern (one line, trailing comma)
