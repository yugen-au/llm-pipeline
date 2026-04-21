# IMPLEMENTATION - STEP 1: ADD CASE_ID TO CASERESULTITEM
**Status:** completed

## Summary
Added case_id field to CaseResultItem Pydantic response model and mapped it from the ORM EvaluationCaseResult row.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/evals.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/evals.py`
Added `case_id: int = 0` to CaseResultItem model and mapped `cr.case_id` in the route handler.

```
# Before
class CaseResultItem(BaseModel):
    id: int
    case_name: str
    ...

CaseResultItem(
    id=cr.id,
    case_name=cr.case_name,
    ...

# After
class CaseResultItem(BaseModel):
    id: int
    case_id: int = 0
    case_name: str
    ...

CaseResultItem(
    id=cr.id,
    case_id=cr.case_id,
    case_name=cr.case_name,
    ...
```

## Decisions
### Default value for case_id
**Choice:** default=0 as specified in contract
**Rationale:** matches contract spec; 0 signals "unset" for any legacy data without case_id

## Verification
[x] Field added to CaseResultItem Pydantic model
[x] Field mapped from ORM row in route handler
[x] pytest run - 1554 passed, 15 pre-existing failures unrelated to change
