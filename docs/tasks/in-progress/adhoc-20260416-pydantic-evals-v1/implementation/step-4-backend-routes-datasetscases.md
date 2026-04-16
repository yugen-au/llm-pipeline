# IMPLEMENTATION - STEP 4: BACKEND ROUTES DATASETS+CASES
**Status:** completed

## Summary
Created evals API router with full dataset and case CRUD endpoints at `/api/evals/`. Follows reviews.py patterns: Pydantic response models, DBSession/WritableDBSession dependency injection, HTTPException for errors.

## Files
**Created:** `llm_pipeline/ui/routes/evals.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/evals.py`
New file with:
- 9 Pydantic request/response models (DatasetListItem, DatasetListResponse, DatasetDetail, DatasetCreateRequest, DatasetUpdateRequest, CaseItem, CaseCreateRequest, CaseUpdateRequest, CaseCreateRequest)
- 4 dataset endpoints: GET list (with case_count subquery + last_run_pass_rate), GET detail, POST create, PUT update, DELETE with cascade
- 3 case endpoints: POST create, PUT update, DELETE
- Sentinel comment at EOF for Step 5 to append run + introspection endpoints

## Decisions
### ReadOnly vs Writable sessions
**Choice:** Used DBSession (ReadOnlySession) for GET endpoints, WritableDBSession for POST/PUT/DELETE
**Rationale:** Matches deps.py design intent; GET routes only read, mutation routes need write access

### Cascade delete strategy
**Choice:** Manual cascade: delete case_results -> runs -> cases -> dataset
**Rationale:** SQLModel doesn't auto-cascade without relationship config; explicit deletion is safer and matches the lack of cascade FK constraints in the models

### last_run_pass_rate as helper function
**Choice:** Separate `_last_run_pass_rate()` helper querying latest completed run per dataset
**Rationale:** Avoids complex window-function join in list query; acceptable N+1 for dataset lists (typically small). Reusable in both list and detail endpoints.

## Verification
[x] Python syntax check passes
[x] Follows reviews.py patterns (DBSession dep, HTTPException, Pydantic response_model)
[x] All 7 endpoints match SCOPE spec
[x] Step 5 sentinel comment present at EOF
[x] No imports from uninstalled packages
