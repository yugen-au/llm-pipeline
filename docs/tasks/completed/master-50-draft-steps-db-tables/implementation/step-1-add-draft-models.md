# IMPLEMENTATION - STEP 1: ADD DRAFT MODELS
**Status:** completed

## Summary
Added DraftStep and DraftPipeline SQLModel table definitions to state.py with UniqueConstraint on name, JSON columns, status fields, and indexes.

## Files
**Created:** none
**Modified:** llm_pipeline/state.py
**Deleted:** none

## Changes
### File: `llm_pipeline/state.py`
Added UniqueConstraint to sqlalchemy import. Added DraftStep and DraftPipeline classes after PipelineRun, before __all__. Updated __all__ to include both new models.

```
# Before
from sqlalchemy import Index

# After
from sqlalchemy import Index, UniqueConstraint
```

```
# Before
__all__ = ["PipelineStepState", "PipelineRunInstance", "PipelineRun"]

# After (DraftStep + DraftPipeline classes added before __all__)
__all__ = [
    "PipelineStepState",
    "PipelineRunInstance",
    "PipelineRun",
    "DraftStep",
    "DraftPipeline",
]
```

DraftStep fields: id (PK), name (str 100, unique), description (optional str), generated_code (JSON dict), test_results (optional JSON), validation_errors (optional JSON), status (str 20, default 'draft'), run_id (optional str 36, no FK), created_at, updated_at.

DraftPipeline fields: id (PK), name (str 100, unique), structure (JSON dict), compilation_errors (optional JSON), status (str 20, default 'draft'), created_at, updated_at.

## Decisions
None - all decisions pre-made in PLAN.md and followed exactly.

## Verification
[x] UniqueConstraint added to sqlalchemy import
[x] DraftStep placed after PipelineRun, before __all__
[x] DraftPipeline placed after DraftStep, before __all__
[x] Both models added to __all__
[x] All fields match PLAN.md spec exactly
[x] __table_args__ use tuple form with UniqueConstraint + Index entries
[x] Python import verification passes
[x] Follows existing patterns (utc_now, Column(JSON), Field, Optional)
