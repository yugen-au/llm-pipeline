# IMPLEMENTATION - STEP 1: BACKEND EDITOR ROUTER
**Status:** completed

## Summary
Created editor.py router with 7 endpoints (compile, available-steps, 5x DraftPipeline CRUD) and registered in app.py.

## Files
**Created:** `llm_pipeline/ui/routes/editor.py`
**Modified:** `llm_pipeline/ui/app.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/editor.py`
New file with:
- 12 Pydantic request/response models (EditorStep, EditorStrategy, CompileRequest, CompileError, CompileResponse, AvailableStep, AvailableStepsResponse, DraftPipelineItem, DraftPipelineDetail, CreateDraftPipelineRequest, UpdateDraftPipelineRequest, DraftPipelineListResponse)
- `_collect_registered_steps()` helper: introspects registry to build step_name -> pipeline_names map
- `POST /compile`: validates step_refs against registered steps + non-errored DraftSteps
- `GET /available-steps`: merges registered + draft steps, deduplicated by step_ref (registered wins)
- `POST /drafts`: create DraftPipeline, 409 on IntegrityError
- `GET /drafts`: list ordered by created_at desc
- `GET /drafts/{id}`: get by id, 404 if missing
- `PATCH /drafts/{id}`: update name/structure, explicit `updated_at = utc_now()`, 409 with suggested_name on collision
- `DELETE /drafts/{id}`: delete, 404 if missing, returns 204

### File: `llm_pipeline/ui/app.py`
```
# Before
from llm_pipeline.ui.routes.creator import router as creator_router

# After
from llm_pipeline.ui.routes.creator import router as creator_router
from llm_pipeline.ui.routes.editor import router as editor_router
```
Added `app.include_router(editor_router, prefix="/api")` after creator_router.

## Decisions
### Session pattern for write endpoints
**Choice:** `with Session(engine) as session:` for all endpoints (reads and writes)
**Rationale:** Plan specifies writes use explicit Session(engine), not DBSession (which yields ReadOnlySession). For consistency and since compile/available-steps also need direct DraftStep queries, used Session(engine) throughout rather than mixing patterns.

### Available-steps deduplication order
**Choice:** Registered steps win on name clash; draft steps only added if step_ref not already seen
**Rationale:** Per PLAN.md and VALIDATED_RESEARCH -- registered steps are authoritative. Draft steps with same name as registered step are likely the same step at a different lifecycle stage.

### GET /drafts uses Session(engine) not DBSession
**Choice:** All editor endpoints use Session(engine) directly
**Rationale:** Creator uses DBSession (ReadOnlySession) for read-only list/get endpoints but Session(engine) for writes. Editor could mix both, but using Session(engine) consistently is simpler and avoids importing DBSession dependency. All reads are simple selects so ReadOnlySession wrapper adds no safety benefit here.

## Verification
[x] Router imports without error
[x] Router has exactly 7 routes
[x] App creates with editor routes at /api/editor/* paths
[x] All endpoints follow existing codebase patterns (plain Pydantic models, Session(engine), HTTPException for 404s, JSONResponse for 409s)
[x] updated_at explicitly set on PATCH (no DB trigger per task 50 finding)
[x] compile validates against both introspection_registry and non-errored DraftSteps
[x] available-steps merges and deduplicates by step_ref with registered winning
