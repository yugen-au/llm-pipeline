# IMPLEMENTATION - STEP 1: CREATOR ROUTE MODULE
**Status:** completed

## Summary
Created `llm_pipeline/ui/routes/creator.py` with all 5 REST endpoints for the step creator workflow: POST /generate (202 background), POST /test/{draft_id} (sync sandbox), POST /accept/{draft_id} (sync integration), GET /drafts (list), GET /drafts/{draft_id} (detail). Follows trigger_run pattern exactly for background task wiring.

## Files
**Created:** `llm_pipeline/ui/routes/creator.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/creator.py`
New file with:
- APIRouter(prefix="/creator", tags=["creator"])
- 8 Pydantic request/response models (GenerateRequest, GenerateResponse, TestRequest, TestResponse, AcceptRequest, AcceptResponse, DraftItem, DraftListResponse)
- Module-level `_seed_done` flag and `_ensure_seeded(engine)` helper for lazy StepCreatorPipeline prompt seeding
- `_derive_target_dir(step_name)` helper using LLM_PIPELINE_STEPS_DIR env var or llm_pipeline package parent
- POST /generate: 202 + BackgroundTasks, pre-creates PipelineRun + DraftStep with placeholder name, UIBridge + BufferedEventHandler + CompositeEmitter, updates DraftStep name from GenerationRecord after pipeline completes, error path sets status="error"/"failed"
- POST /test/{draft_id}: merges code_overrides into DraftStep.generated_code (persists before sandbox), runs StepSandbox.run(), persists test_results and status
- POST /accept/{draft_id}: Session(engine) directly, GeneratedStep.from_draft(), computed target_dir, StepIntegrator with optional pipeline_file, integrator owns commit
- GET /drafts: ReadOnlySession via DBSession, ordered by created_at desc
- GET /drafts/{draft_id}: ReadOnlySession, 404 if not found

## Decisions
### Sandbox execution outside session
**Choice:** Close the writable session holding code_overrides before running StepSandbox, then reopen for test_results persistence
**Rationale:** StepSandbox.run() may block up to 60s (Docker path). Holding a DB session open during that time risks connection pool exhaustion and SQLite lock contention.

### Error path session separation in generate
**Choice:** Separate Session for DraftStep error update and PipelineRun failure update
**Rationale:** Matches trigger_run pattern. Pipeline may hold internal session locks; opening a new Session for error state avoids deadlock.

### Generated code extraction from pipeline context
**Choice:** Access pipeline._context.get("generated_code") after pipeline.save() to populate DraftStep.generated_code
**Rationale:** GenerationRecord stores step_name_generated and file list but not the actual code dict. Pipeline context carries the generated_code dict populated during execution. Falls through gracefully if context unavailable.

## Verification
[x] Module imports successfully: `from llm_pipeline.ui.routes.creator import router`
[x] All 5 routes registered: /creator/generate, /creator/test/{draft_id}, /creator/accept/{draft_id}, /creator/drafts, /creator/drafts/{draft_id}
[x] All endpoints are sync def (not async def)
[x] Write endpoints use Session(engine) directly (not DBSession)
[x] Read endpoints use DBSession dependency
[x] StepIntegrator called without caller commit in accept endpoint
[x] DraftStep placeholder name on generate, updated from GenerationRecord after pipeline completes
[x] 146 existing UI tests pass (2 pre-existing cli test failures unrelated)
[x] Pydantic models are plain BaseModel, not SQLModel
