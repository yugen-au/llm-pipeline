# IMPLEMENTATION - STEP 12: API RESPONSE SHAPE FOR SNAPSHOTS
**Status:** completed

## Summary
Verified that all four snapshot fields (case_versions, prompt_versions, model_snapshot, instructions_schema_snapshot) are already present in RunListItem/RunDetail Pydantic models and threaded through both list and detail endpoints. Test #12 (null snapshot tolerability) already exists and passes.

## Files
**Created:** none
**Modified:** none (already implemented in Step 8)
**Deleted:** none

## Changes
All changes were already implemented in Step 8:
- RunListItem model has the four Optional[dict] fields (lines 122-125 of evals.py)
- RunDetail inherits from RunListItem
- list_eval_runs endpoint threads all four fields (lines 991-994)
- get_eval_run endpoint threads all four fields (lines 1035-1038)
- TestRunDetailToleratesNullSnapshots test class covers both endpoints (line 1327 of test_evals_routes.py)

## Decisions
### No additional code changes needed
**Choice:** Mark as complete without modifications
**Rationale:** Step 8 already fully implemented the API response shape including the snapshot fields and the null tolerability test. Both tests pass.

## Verification
[x] RunListItem has case_versions, prompt_versions, model_snapshot, instructions_schema_snapshot as Optional[dict]
[x] RunDetail inherits these fields from RunListItem
[x] list_eval_runs endpoint threads fields from DB model
[x] get_eval_run endpoint threads fields from DB model
[x] Test #12 exists and passes (TestRunDetailToleratesNullSnapshots)
[x] No server-side mismatch computation present
