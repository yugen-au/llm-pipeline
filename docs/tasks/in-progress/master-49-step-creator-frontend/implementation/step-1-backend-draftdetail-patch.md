# IMPLEMENTATION - STEP 1: BACKEND DRAFTDETAIL + PATCH
**Status:** completed

## Summary
Extended creator API: GET /drafts/{id} now returns DraftDetail (with generated_code + test_results), added PATCH /drafts/{id} for rename with 409 collision handling, added IntegrityError retry loop in run_creator() background task for LLM-generated name collisions.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/routes/creator.py`, `tests/ui/test_creator.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/creator.py`
Added DraftDetail model (extends DraftItem with generated_code + test_results), RenameRequest model, JSONResponse import, IntegrityError import. Changed GET /drafts/{id} response_model from DraftItem to DraftDetail. Added PATCH /drafts/{id} rename_draft endpoint with writable Session (not DBSession/ReadOnlySession). Wrapped run_creator() name assignment in collision retry loop with _2.._9 suffixes.

```
# Before (GET /drafts/{id})
@router.get("/drafts/{draft_id}", response_model=DraftItem)
def get_draft(...) -> DraftItem:
    return DraftItem(...)

# After
@router.get("/drafts/{draft_id}", response_model=DraftDetail)
def get_draft(...) -> DraftDetail:
    return DraftDetail(..., generated_code=draft.generated_code, test_results=draft.test_results)
```

```
# Before (run_creator name assignment)
draft.name = gen_rec.step_name_generated
post_session.add(draft)
post_session.commit()

# After
candidates = [base_name] + [f"{base_name}_{i}" for i in range(2, 10)]
for candidate_name in candidates:
    draft.name = candidate_name
    try:
        post_session.commit()
        break
    except IntegrityError:
        post_session.rollback()
        # re-fetch + log warning
```

### File: `tests/ui/test_creator.py`
Added 8 new test cases: DraftDetail fields present on GET, test_results populated when present, list excludes generated_code/test_results, rename success, rename 404, rename 409 conflict with suggested_name, conflict suggestion skips taken suffixes.

## Decisions
### PATCH endpoint uses writable Session (not DBSession)
**Choice:** Use `Request` + `Session(engine)` instead of `DBSession` dependency
**Rationale:** DBSession yields ReadOnlySession which blocks .add()/.commit(). All other write endpoints in creator.py already use this pattern.

### 409 response via JSONResponse (not HTTPException)
**Choice:** Return `JSONResponse(status_code=409, content={...})` directly
**Rationale:** Spec requires `{"detail": "name_conflict", "suggested_name": "..."}` as flat JSON body. HTTPException wraps detail in `{"detail": <value>}` envelope which would nest it.

## Verification
[x] All 25 tests pass (pytest tests/ui/test_creator.py)
[x] GET /drafts/{id} returns generated_code and test_results
[x] GET /drafts (list) excludes generated_code and test_results
[x] PATCH /drafts/{id} renames successfully
[x] PATCH /drafts/{id} returns 409 with suggested_name on collision
[x] Suggested name skips already-taken suffixes
[x] run_creator() retry loop catches IntegrityError and appends suffixes
[x] No hardcoded values
[x] Error handling present
