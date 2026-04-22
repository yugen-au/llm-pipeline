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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Medium #3 — Backend `case_id` default of `0` is an undocumented sentinel that silently propagates to clients
[x] Low #6 — `case_id: int = 0` breaks `Optional[T] = None` convention used by other optional run-model fields (`variant_id`, `delta_snapshot`, `case_versions`)

### Decision
Chose Option A (change to `Optional[int] = None`) over Option B (document `0` sentinel). Cleaner because it aligns with the project convention for optional run-model fields and removes the magic 0 from the API surface. Runner.py is unchanged (ORM column is non-null `int` FK, and runner stores `0` as the "unresolved case name" sentinel — see `runner.py` lines 222, 237). The route handler now converts the 0 sentinel to `None` when serializing the Pydantic response, so clients receive an explicit `null` instead of a magic number.

### Changes Made
#### File: `llm_pipeline/ui/routes/evals.py`
Changed `CaseResultItem.case_id` from `int = 0` to `Optional[int] = None`, added docstring explaining nullable semantics, and updated the route handler to map the runner's `0` sentinel to `None`.

```
# Before
class CaseResultItem(BaseModel):
    id: int
    case_id: int = 0
    case_name: str
    ...

CaseResultItem(
    id=cr.id,
    case_id=cr.case_id,
    ...

# After
class CaseResultItem(BaseModel):
    id: int
    # case_id is None when the runner could not resolve the case name to a DB id
    # (see runner.py lines 222, 237: name_to_id.get(..., 0) sentinel). The ORM
    # column is non-null int; the route handler maps the 0 sentinel to None so
    # clients receive an explicit null instead of a magic 0.
    case_id: Optional[int] = None
    case_name: str
    ...

CaseResultItem(
    id=cr.id,
    # Map runner's 0 sentinel (unresolved case name) to None for clients
    case_id=cr.case_id if cr.case_id else None,
    ...
```

#### File: `llm_pipeline/ui/frontend/src/api/evals.ts`
Changed `CaseResultItem.case_id` type from `number` to `number | null`, added TSDoc referencing backend sentinel semantics.

```
# Before
export interface CaseResultItem {
  id: number
  case_id: number
  ...

# After
export interface CaseResultItem {
  id: number
  /**
   * DB id of the eval case, or null when the runner could not resolve the
   * case name to a case row (see backend `runner.py` lines 222, 237 —
   * `name_to_id.get(name, 0)`; the 0 sentinel is mapped to null by the
   * route handler). Consumers that key into `RunListItem.case_versions`
   * by `case_id` must treat null as "unmatched".
   */
  case_id: number | null
  ...
```

#### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`
Updated `computeCaseBucket` to short-circuit to `'unmatched'` when either side has `case_id === null` (cannot key into `case_versions` without an id).

```
# Before
if (!baseResult || !compareResult) return 'unmatched'
const baseCv = baseRun.case_versions
const compareCv = compareRun.case_versions
...

# After
if (!baseResult || !compareResult) return 'unmatched'
// case_id may be null if the runner couldn't resolve the case name to a DB id;
// without an id we cannot key into case_versions -> treat as unmatched.
if (baseResult.case_id === null || compareResult.case_id === null) return 'unmatched'
const baseCv = baseRun.case_versions
const compareCv = compareRun.case_versions
...
```

### Verification
[x] pytest `tests/test_eval_runner.py tests/ui/test_evals_routes.py` — 58 passed
[x] `tsc --noEmit` on frontend — no errors
[x] `eslint` on modified frontend files — no errors
[x] Backend sentinel semantics documented in Pydantic model docstring
[x] Frontend sentinel semantics documented in TSDoc
[x] Convention aligned with `variant_id: Optional[int] = None` pattern
