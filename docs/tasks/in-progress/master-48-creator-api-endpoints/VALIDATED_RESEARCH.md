# Research Summary

## Executive Summary

Both research files (step-1 API architecture, step-2 creator module analysis) are accurate regarding class interfaces, data models, and codebase conventions. All claims verified against actual source. Key discrepancy: generate endpoint pattern contradicts itself (inline vs 202+background) -- resolved by CEO as 202+background. Nine coverage gaps identified; four blocking architectural questions resolved by CEO (target_dir convention-based, AST splice optional param, generate 202+background, code edits persist on test). Remaining open items are non-blocking implementation details that can be resolved during planning.

## Domain Findings

### Creator Module Interfaces
**Source:** step-2-existing-creator-module-analysis.md

All class signatures verified against actual source:

- `StepCreatorPipeline` (creator/pipeline.py) -- inherits PipelineConfig. Constructor: `(model, strategies?, session?, engine?, variable_resolver?, event_emitter?, run_id?, instrumentation_settings?)`. INPUT_DATA = StepCreatorInputData with fields: description, target_pipeline, include_extraction, include_transformation. SYNC execute().
- `StepSandbox` (creator/sandbox.py) -- `__init__(image, timeout)`, `run(artifacts, sample_data) -> SandboxResult`. Layer 1 AST scan always runs (fast). Layer 2 Docker container up to 60s timeout. Graceful degradation when Docker unavailable.
- `StepIntegrator` (creator/integrator.py) -- `__init__(session: Session, pipeline_file: Path|None)`, `integrate(generated: GeneratedStep, target_dir: Path, draft: DraftStep|None) -> IntegrationResult`. 7 phases, owns commit/rollback. Caller must NOT commit.
- `GeneratedStep` (creator/models.py) -- `from_draft(draft: DraftStep)` classmethod builds typed adapter from DraftStep.generated_code dict. Derives PascalCase class names.
- `DraftStep` (state.py:199-238) -- EXISTS. SQLModel table="draft_steps". Fields match research exactly. UniqueConstraint on name confirmed. Status index confirmed.
- `SandboxResult`, `IntegrationResult`, `GenerationRecord` -- all confirmed in expected locations.

Research step-2 accurately describes include_transformation field on StepCreatorInputData, but research step-1's proposed request model omits it. Minor gap.

### UI Route Architecture
**Source:** step-1-api-architecture-research.md

Conventions verified against llm_pipeline/ui/:

- All HTTP endpoints are sync `def` (not `async def`). Only websocket.py uses async.
- Router pattern: `APIRouter(prefix="/resource", tags=["resource"])`, mounted via `app.include_router(router, prefix="/api")`.
- Response/request models: plain Pydantic BaseModel, NOT SQLModel.
- Read-only: `DBSession` (Annotated[ReadOnlySession, Depends(get_db)]). Writable: `Session(engine)` directly (trigger_run pattern).
- Background tasks: `BackgroundTasks` + 202 status code (trigger_run in runs.py).
- app.state: engine, pipeline_registry, introspection_registry, default_model -- all confirmed.
- No existing creator route file at llm_pipeline/ui/routes/creator.py -- confirmed.

### Background Task Pattern (trigger_run)
**Source:** step-1 + step-2, cross-referenced with llm_pipeline/ui/routes/runs.py

trigger_run (runs.py:186-285) is the canonical pattern for long-running ops:
1. Validate registry + model guard
2. Create run_id, pre-create PipelineRun record (writable Session)
3. Broadcast WS run_created event
4. Background: factory(run_id, engine, event_emitter) -> pipeline.execute() -> pipeline.save()
5. Error path: close pipeline session, update PipelineRun.status="failed"
6. Finally: bridge.complete(), db_buffer.flush()

Research step-2 correctly identifies this pattern for generate but step-1 contradicts with inline asyncio.to_thread approach.

### Test Infrastructure
**Source:** step-1-api-architecture-research.md

Verified tests/ui/conftest.py:
- `_make_app()`: in-memory SQLite + StaticPool, registers all 6 routers, sets app.state.engine/pipeline_registry/default_model.
- Fixtures: `app_client` (empty DB), `seeded_app_client` (pre-populated PipelineRun/StepState/Events).
- Creator tests will need: creator router added to `_make_app()`, DraftStep seed data, possibly mock StepCreatorPipeline.

### Upstream Task 47 Deviations
**Source:** docs/tasks/completed/master-47-auto-integration-gen-steps/SUMMARY.md

Task 47 implemented StepIntegrator exactly as described in research. Key deviations from task 47's plan:
- Re-parse after each AST splice (4 _reparse() calls) -- functionally equivalent, no impact on task 48.
- File+DB non-atomicity limitation documented -- process crash between file writes and commit leaves orphans. DraftStep.status=="draft" is recovery signal.
- Recommendation #1 from task 47: "accept endpoint should create Session, retrieve DraftStep, call integrator.integrate(), return IntegrationResult. Must NOT commit." Directly applicable.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Q1: Where should accepted step files be written (target_dir)? Options: (a) request body param, (b) convention-based `{base}/steps/{step_name}/`, (c) env var only | Convention-based `{configurable_base}/steps/{step_name}/` with env var override for base dir | Accept endpoint derives target_dir from step_name + configurable base. No arbitrary path in request body (security). StepIntegrator receives computed Path. |
| Q2: Should accept endpoint do AST pipeline file modification? Options: (a) always skip, (b) optional pipeline_file param, (c) auto-detect from registry | Optional `pipeline_file` param matching StepIntegrator's existing design; skip if not provided | Accept request model includes optional `pipeline_file: str`. StepIntegrator.__init__ receives Path(pipeline_file) or None. Matches existing integrator design exactly. |
| Q3: Generate endpoint -- inline with asyncio.to_thread or 202+background? Research contradicted itself. | Background 202 -- match existing trigger_run pattern, frontend polls/WS for result | Generate endpoint follows trigger_run pattern: pre-create PipelineRun, BackgroundTasks, UIBridge+CompositeEmitter, 202 response with run_id. Resolves research contradiction in favor of step-2's proposal. |
| Q4: When test endpoint receives code_overrides, should edits persist to DraftStep.generated_code or be transient? | Persist edits -- update DraftStep.generated_code so accept uses the edited version | Test endpoint merges code_overrides into DraftStep.generated_code before running sandbox. Accept always uses latest persisted code. Frontend (task 49) can assume "test and save" semantics. |

## Assumptions Validated
- [x] DraftStep model exists in state.py with correct schema (id, name, description, generated_code, test_results, validation_errors, status, run_id, created_at, updated_at)
- [x] DraftStep has unique constraint on name and status index
- [x] StepIntegrator signature: __init__(session, pipeline_file=None), integrate(generated, target_dir, draft=None) -> IntegrationResult
- [x] StepIntegrator owns commit/rollback -- caller must NOT commit
- [x] GeneratedStep.from_draft(DraftStep) classmethod exists and works
- [x] StepSandbox.run(artifacts, sample_data) -> SandboxResult is sync
- [x] StepCreatorPipeline is sync (execute() blocks for 4 LLM calls)
- [x] All existing HTTP route endpoints are sync def (not async def)
- [x] trigger_run uses BackgroundTasks + 202 pattern for long-running ops
- [x] app.state.default_model available at runtime for model param
- [x] No existing creator route file -- new file needed
- [x] Test conftest _make_app() creates in-memory SQLite with StaticPool
- [x] StepCreatorInputData has include_transformation field (omitted from research step-1 request model)

## Resolved Decisions
- **Q1 (RESOLVED): target_dir for accept endpoint** -- Convention-based `{configurable_base}/steps/{step_name}/` with env var override for base dir. No arbitrary paths in request body.
- **Q2 (RESOLVED): AST pipeline file modification** -- Optional `pipeline_file` param on accept endpoint. When provided, StepIntegrator receives Path; when omitted, AST phase skipped. Matches existing integrator design.
- **Q3 (RESOLVED): Generate endpoint execution pattern** -- 202+background matching trigger_run. Pre-create PipelineRun, BackgroundTasks, UIBridge+CompositeEmitter for WS events. Research step-1's inline proposal rejected.
- **Q4 (RESOLVED): Code overrides persistence** -- Persist to DraftStep.generated_code on test. Accept always uses latest persisted code. "Test and save" semantics.

## Open Items (non-blocking, resolve during planning/implementation)
- **Q5: WebSocket event streaming for generate** -- trigger_run wires UIBridge + CompositeEmitter for real-time WS events. Generate endpoint for StepCreatorPipeline should do the same (4 LLM calls = 4 step_started/step_completed events). Research omits this entirely. Implementation detail -- follow trigger_run pattern.
- **Q6: Error handling for generate failures** -- If StepCreatorPipeline fails mid-execution, DraftStep should be set to status="error" with validation_errors. Follow trigger_run error path pattern.
- **Q7: DraftStep upsert mechanics** -- SQLModel has no built-in upsert. Use query-by-name then update-or-insert pattern for cross-DB compatibility (SQLite + PostgreSQL).
- **Q8: Creator runs visibility in /api/runs** -- StepCreatorPipeline runs create PipelineRun records visible in /api/runs listing. Likely acceptable (frontend can filter by pipeline_name); defer filter decision to task 49.
- **Q9: Seed prompts for StepCreatorPipeline** -- Generate endpoint should call seed_prompts(engine) lazily on first invocation, or register creator pipeline as entry point. Implementation detail.

## Recommendations for Planning
1. All blocking decisions resolved -- ready for planning phase
2. **Generate endpoint**: follow trigger_run pattern exactly -- pre-create PipelineRun + DraftStep, BackgroundTasks, UIBridge+CompositeEmitter for WS, error handling (DraftStep.status="error"), 202 response with run_id + draft name
3. **Accept endpoint**: Session(engine) directly (not dependency injection), compute target_dir from `{configurable_base}/steps/{step_name}/`, optionally receive pipeline_file, pass to StepIntegrator, return IntegrationResult. Integrator owns commit.
4. **Test endpoint**: merge code_overrides into DraftStep.generated_code (persist), then run StepSandbox. Sync 200 for AST-only path, consider timeout for Docker path (~60s).
5. **Writable session pattern**: use direct `Session(engine)` for consistency with trigger_run (not dependency injection)
6. **DraftStep upsert**: query-by-name then update-or-insert (portable across SQLite/PostgreSQL)
7. **Router setup**: `APIRouter(prefix="/creator", tags=["creator"])` at `llm_pipeline/ui/routes/creator.py`, register in create_app() and test conftest _make_app()
8. **Request model**: include `include_transformation` in generate request for completeness
9. **Seed prompts**: lazily call StepCreatorPipeline.seed_prompts(engine) on first generate invocation
10. **5 endpoints**: POST generate, POST test/{draft_id}, POST accept/{draft_id}, GET drafts, GET drafts/{id}
