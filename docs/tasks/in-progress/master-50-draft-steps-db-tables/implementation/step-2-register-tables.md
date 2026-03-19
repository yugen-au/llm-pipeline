# IMPLEMENTATION - STEP 2: REGISTER TABLES
**Status:** completed

## Summary
Registered DraftStep and DraftPipeline tables in init_pipeline_db() so they are created alongside existing pipeline tables.

## Files
**Created:** none
**Modified:** llm_pipeline/db/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/db/__init__.py`
Added DraftStep and DraftPipeline to the import from llm_pipeline.state, added both `__table__` entries to the `tables=[...]` list in `init_pipeline_db()`, and updated the docstring.

```
# Before
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun

# After
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun, DraftStep, DraftPipeline
```

```
# Before (tables list)
tables=[
    PipelineStepState.__table__,
    PipelineRunInstance.__table__,
    PipelineRun.__table__,
    Prompt.__table__,
    PipelineEventRecord.__table__,
],

# After (tables list)
tables=[
    PipelineStepState.__table__,
    PipelineRunInstance.__table__,
    PipelineRun.__table__,
    Prompt.__table__,
    PipelineEventRecord.__table__,
    DraftStep.__table__,
    DraftPipeline.__table__,
],
```

```
# Before (docstring)
Creates PipelineStepState, PipelineRunInstance, Prompt, and
PipelineEventRecord (pipeline_events) tables.

# After (docstring)
Creates PipelineStepState, PipelineRunInstance, Prompt,
PipelineEventRecord (pipeline_events), DraftStep (draft_steps),
and DraftPipeline (draft_pipelines) tables.
```

## Decisions
None - followed existing pattern exactly.

## Verification
[x] Import succeeds: `from llm_pipeline.db import init_pipeline_db` with DraftStep/DraftPipeline
[x] In-memory SQLite: `init_pipeline_db(engine)` creates `draft_steps` table
[x] In-memory SQLite: `init_pipeline_db(engine)` creates `draft_pipelines` table
[x] All 7 expected tables present after init
