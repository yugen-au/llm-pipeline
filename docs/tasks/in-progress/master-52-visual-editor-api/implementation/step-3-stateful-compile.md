# IMPLEMENTATION - STEP 3: STATEFUL COMPILE
**Status:** completed

## Summary
Added stateful compile write path to compile_pipeline(). When draft_id is provided in CompileRequest, fetches DraftPipeline by id, persists compilation_errors and updates status/updated_at, then commits.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/editor.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/editor.py`
After all 5 validation passes and `has_errors` computation, added stateful write path block (lines 293-307).

```
# Before
has_errors = any(e.severity == "error" for e in errors)
return CompileResponse(valid=not has_errors, errors=errors)

# After
has_errors = any(e.severity == "error" for e in errors)

# --- Stateful write path: persist compilation results to DraftPipeline ---
if body.draft_id is not None:
    with Session(engine) as session:
        draft = session.get(DraftPipeline, body.draft_id)
        if draft is None:
            raise HTTPException(
                status_code=404, detail="Draft pipeline not found"
            )
        draft.compilation_errors = {
            "errors": [e.model_dump() for e in errors]
        }
        draft.status = "error" if errors else "draft"
        draft.updated_at = utc_now()
        session.add(draft)
        session.commit()

return CompileResponse(valid=not has_errors, errors=errors)
```

## Decisions
### Status value on clean compile
**Choice:** Set status="draft" when no errors (not "tested" or "accepted")
**Rationale:** Plan explicitly states "draft" for valid, "error" for errors. "tested"/"accepted" are downstream states set by other flows.

### Session scope
**Choice:** Separate `with Session(engine)` block for the stateful write, not reusing earlier sessions
**Rationale:** Matches existing endpoint patterns (create_draft_pipeline, update_draft_pipeline). Earlier sessions for validation are already closed. Clean separation of read-validate vs write concerns.

### Error list always persisted
**Choice:** compilation_errors is written even when errors list is empty (stores `{"errors": []}`)
**Rationale:** Explicit empty list signals "compilation ran and passed" vs None which signals "never compiled". Plan confirms this in success criteria.

## Verification
[x] Module imports cleanly
[x] Stateful path only triggers when draft_id is not None (backward compatible)
[x] 404 raised when DraftPipeline not found (matches existing CRUD pattern)
[x] compilation_errors format matches plan: `{"errors": [<model_dump dicts>]}`
[x] status set to "error" if has_errors (error-severity only), "draft" otherwise
[x] updated_at set via utc_now() (matches update_draft_pipeline pattern)

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] Status logic uses `errors` list truthiness instead of `has_errors`, causing warning-only compiles to set status="error" while CompileResponse.valid=True

### Changes Made
#### File: `llm_pipeline/ui/routes/editor.py`
Changed status assignment to use `has_errors` so DB state matches API response.
```
# Before
draft.status = "error" if errors else "draft"

# After
draft.status = "error" if has_errors else "draft"
```

### Verification
[x] Warning-only compile now sets status="draft" (consistent with valid=True)
[x] Error-severity compile still sets status="error" (consistent with valid=False)
[x] No-errors compile still sets status="draft"
