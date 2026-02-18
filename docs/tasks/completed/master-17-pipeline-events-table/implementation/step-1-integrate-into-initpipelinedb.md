# IMPLEMENTATION - STEP 1: INTEGRATE INTO INIT_PIPELINE_DB
**Status:** completed

## Summary
Added PipelineEventRecord to init_pipeline_db() so the pipeline_events table is automatically created alongside existing tables (PipelineStepState, PipelineRunInstance, Prompt).

## Files
**Created:** none
**Modified:** llm_pipeline/db/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/db/__init__.py`
Added import for PipelineEventRecord, added its table to the explicit allowlist in create_all(), updated docstring.

```python
# Before (imports, lines 14-15)
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.state import PipelineStepState, PipelineRunInstance

# After (imports, lines 14-16)
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.state import PipelineStepState, PipelineRunInstance
from llm_pipeline.events.models import PipelineEventRecord
```

```python
# Before (docstring, line 39)
    Creates PipelineStepState, PipelineRunInstance, and Prompt tables.

# After (docstring, lines 40-41)
    Creates PipelineStepState, PipelineRunInstance, Prompt, and
    PipelineEventRecord (pipeline_events) tables.
```

```python
# Before (tables list, lines 60-64)
        tables=[
            PipelineStepState.__table__,
            PipelineRunInstance.__table__,
            Prompt.__table__,
        ],

# After (tables list, lines 62-67)
        tables=[
            PipelineStepState.__table__,
            PipelineRunInstance.__table__,
            Prompt.__table__,
            PipelineEventRecord.__table__,
        ],
```

## Decisions
None -- all choices were pre-decided in PLAN.md (explicit table list pattern, import placement).

## Verification
[x] init_pipeline_db() creates pipeline_events table (verified with in-memory SQLite)
[x] All 4 expected tables present: pipeline_events, pipeline_run_instances, pipeline_step_states, prompts
[x] No circular import issues
[x] Existing test suite passes (465 passed; 16 pre-existing google module failures unrelated)
