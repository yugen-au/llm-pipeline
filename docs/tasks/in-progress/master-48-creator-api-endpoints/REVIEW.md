# Architecture Review

## Overall Assessment
**Status:** partial
Implementation follows established codebase patterns well (trigger_run background pattern, Session(engine) for writes, DBSession for reads, sync endpoints). One critical bug in the generate background task will prevent DraftStep.generated_code from being populated. One high-severity issue with missing pipeline.close() before error session. Several medium/low items around session lifecycle and test mock targets.

## Project Guidelines Compliance
**CLAUDE.md:** D:\Documents\claude-projects\llm-pipeline\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| Pipeline + Strategy + Step pattern | pass | StepCreatorPipeline used correctly via lazy import |
| pydantic-ai Agent system | pass | Not directly relevant; pipeline handles internally |
| ReadOnlySession for reads | pass | GET /drafts and GET /drafts/{id} use DBSession (ReadOnlySession) |
| Session(engine) for writes | pass | POST generate, test, accept all use Session(engine) directly |
| Pydantic v2 models | pass | All request/response models are plain BaseModel |
| SQLModel for DB models | pass | DraftStep, PipelineRun from state.py used correctly |
| Tests pass | pass | 18 new tests pass per implementation notes |
| No hardcoded values | pass | Model comes from app.state, target_dir from env var or package location |
| Error handling present | pass | 404, 422, 500 error paths covered with HTTPException |

## Issues Found
### Critical
#### Wrong context key for generated_code in generate background task
**Step:** 1
**Details:** In `run_creator()` (creator.py lines 206-210), the code reads `ctx.get("generated_code", {})` from the pipeline context. However, the `CodeValidationStep.process_instructions()` in `llm_pipeline/creator/steps.py` stores the code dict under the key `all_artifacts`, not `generated_code`. The pipeline context merges step return values via `_context.update(new_context)`, and `CodeValidationContext` has field `all_artifacts: dict[str, str]`. This means `ctx.get("generated_code")` will always return `{}`, and `DraftStep.generated_code` will never be updated from its empty placeholder after generation completes. Fix: change `"generated_code"` to `"all_artifacts"` on line 208.

### High
#### Missing pipeline.close() before error session in generate background task
**Step:** 1
**Details:** The `trigger_run` pattern in runs.py (lines 256-260) explicitly calls `pipeline.close()` before opening the error session to release the internal session lock. Without this, on PostgreSQL, the error session's UPDATE on PipelineRun can deadlock against the pipeline's held transaction. The `run_creator()` closure in creator.py does not call `pipeline.close()` (or any equivalent cleanup) before opening `err_session`. The pipeline variable is also scoped inside the try block, so it may not be accessible in the except block without prior assignment. Fix: declare `pipeline = None` before the try, and add a `pipeline.close()` call in the except block before opening `err_session`, matching the trigger_run pattern.

### Medium
#### Accept endpoint session not using context manager
**Step:** 1
**Details:** The accept endpoint creates `session = Session(engine)` without a `with` block (line 308). While the finally block attempts `session.close()`, the structure is fragile: if the HTTPException for 404 is raised, `session.close()` is called explicitly (line 312), but then the `finally` block calls it again. The StepIntegrator commits on success, but if the integrator raises, the except block catches it and re-raises HTTPException -- the outer `except HTTPException: raise` then propagates, hitting finally which does a second close. This works but is unnecessarily complex. The pattern is correct in that the integrator owns commit, but a `with Session(engine) as session:` block would be cleaner and match the test/generate patterns. Not a bug, but a maintainability concern -- the manual close() paths are error-prone.

#### Error path in generate uses single session for two separate entity updates
**Step:** 1
**Details:** In the error path of `run_creator()` (lines 220-236), a single `err_session` fetches DraftStep, commits, then fetches PipelineRun and commits again. Two commits in one session block is unusual. If the first commit succeeds but the second fails, DraftStep.status="error" is persisted but PipelineRun.status remains "running" -- an inconsistent state. trigger_run uses a single session with a single entity update (PipelineRun only). Consider combining both updates into a single commit, or use separate sessions for isolation.

### Low
#### Test mock targets may be fragile for accept endpoint
**Step:** 3
**Details:** Accept tests patch `llm_pipeline.creator.integrator.StepIntegrator` and `llm_pipeline.creator.models.GeneratedStep.from_draft` at their source modules. This works because the route uses lazy imports. However, if someone refactors the imports to module-level (moving them out of the function body), the mocks would break silently. The tests should document this coupling or use a more robust mock injection pattern. Not a blocker -- current implementation works correctly with the lazy import pattern.

#### DraftItem response model excludes generated_code and test_results
**Step:** 1
**Details:** The `DraftItem` response model and `GET /drafts/{id}` endpoint only expose id, name, description, status, run_id, created_at, updated_at. For a detail endpoint, the frontend (task 49) may need `generated_code` and `test_results` to render the editor and test output. This may be intentional to keep the list response lightweight, but the single-draft detail endpoint could benefit from a richer model (e.g., `DraftDetail` with the extra fields). Not blocking -- can be addressed in task 49 when frontend needs are clearer.

#### _ensure_seeded sets _seed_done=True even on failure
**Step:** 1
**Details:** If `seed_prompts` raises, `_seed_done` is set to True in the except block (line 106) to avoid retrying. The PLAN.md documents this as intentional (don't retry on every request), and it matches app.py's pattern for seed_prompts failures. However, if the failure is transient (e.g., temporary DB issue), seeds will never be attempted again for the process lifetime. Acceptable trade-off for current scale.

## Review Checklist
[x] Architecture patterns followed -- 202+BackgroundTasks for generate, Session(engine) for writes, DBSession for reads, sync endpoints, lazy imports for creator modules
[x] Code quality and maintainability -- clean separation of models, helpers, endpoints; consistent with runs.py patterns
[ ] Error handling present -- missing pipeline.close() in generate error path (HIGH); double-commit in error session (MEDIUM)
[x] No hardcoded values -- model from app.state, target_dir from env var, run_id from uuid4
[x] Project conventions followed -- router prefix/tags, response_model, BaseModel not SQLModel
[x] Security considerations -- no arbitrary paths in request body for target_dir, pipeline_file is relative
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- minimal models, no unnecessary abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/routes/creator.py | fail | Critical: wrong context key; High: missing pipeline.close() |
| llm_pipeline/ui/app.py | pass | Router registration correct, placement after pipelines_router |
| tests/ui/conftest.py | pass | Router added correctly to _make_app() |
| tests/ui/test_creator.py | pass | 18 tests, good coverage, proper mocking strategy |

## New Issues Introduced
- CRITICAL: `ctx.get("generated_code")` should be `ctx.get("all_artifacts")` -- DraftStep.generated_code will never be populated after generation
- HIGH: Missing `pipeline.close()` before error session in generate background task -- potential PostgreSQL deadlock
- MEDIUM: Accept endpoint session lifecycle is fragile (manual close, not context manager)
- MEDIUM: Double commit in generate error path (DraftStep + PipelineRun in same session)

## Recommendation
**Decision:** CONDITIONAL
Two required fixes before merge: (1) Change `"generated_code"` to `"all_artifacts"` in the generate background task's context extraction -- without this, the entire generate workflow produces empty DraftStep records. (2) Add `pipeline.close()` before the error session in generate's except block, matching trigger_run's deadlock prevention pattern. The medium issues are real but not blocking.
