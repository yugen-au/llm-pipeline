# IMPLEMENTATION - STEP 1: BASE CLASS
**Status:** completed

## Summary
Added PipelineInputData base class to context.py as a Pydantic v2 BaseModel subclass, following same pattern as PipelineContext.

## Files
**Created:** none
**Modified:** llm_pipeline/context.py
**Deleted:** none

## Changes
### File: `llm_pipeline/context.py`
Added PipelineInputData class after PipelineContext (L36-41), updated __all__ export (L44).

```python
# Before
__all__ = ["PipelineContext"]

# After
class PipelineInputData(BaseModel):
    """
    Base class for pipeline input data. Pipelines that require structured
    input should define an InputData class inheriting from this base.
    """
    pass


__all__ = ["PipelineContext", "PipelineInputData"]
```

## Decisions
None - all decisions pre-made in PLAN.md and VALIDATED_RESEARCH.md.

## Verification
[x] Class inherits from pydantic BaseModel (same as PipelineContext)
[x] Docstring matches spec from plan
[x] Placed after PipelineContext at L36
[x] __all__ updated to include "PipelineInputData"
[x] No model_config needed - intentionally minimal base
[x] Graphiti updated with new codebase context
