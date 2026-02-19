# IMPLEMENTATION - STEP 1: IMPLEMENT STEPS.PY
**Status:** completed

## Summary
Replaced 4-line stub in `steps.py` with full step list and step detail endpoints. Two sync GET endpoints using DBSession, plain BaseModel responses, manual field mapping.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/steps.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/steps.py`
Replaced stub with full implementation: 3 response models, 1 helper, 2 endpoints.

```
# Before
"""Pipeline run steps route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/runs/{run_id}/steps", tags=["steps"])

# After
Full module with:
- StepListItem, StepListResponse, StepDetail (BaseModel, not SQLModel)
- _get_run_or_404 helper
- GET "" (list_steps) - validates run, returns steps ordered by step_number
- GET "/{step_number}" (get_step) - single query by (run_id, step_number), 404 if None
```

## Decisions
### StepDetail field types for result_data/context_snapshot
**Choice:** `dict` (not `Optional[dict]`) matching PipelineStepState column types
**Rationale:** PipelineStepState defines both as `dict` with `sa_column=Column(JSON)`, no `Optional`. Seed data uses `{}` for empty. Consistent with ORM model.

## Verification
[x] Module imports without error
[x] Routes register at correct paths: /runs/{run_id}/steps, /runs/{run_id}/steps/{step_number}
[x] Existing test_runs.py passes (23 passed, 0 regressions)
[x] Uses sync def, DBSession, List[T], BaseModel -- matches runs.py patterns
[x] All 13 PipelineStepState data columns mapped in StepDetail
