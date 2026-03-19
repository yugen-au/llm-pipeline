# PLANNING

## Summary

Implement REST API endpoints for the step creator workflow: generate (202 background), test (sync sandbox), accept (sync integration), and list drafts. New file `llm_pipeline/ui/routes/creator.py` follows trigger_run and existing route conventions exactly. Router registered in `create_app()` and test conftest `_make_app()`.

## Plugin & Agents

**Plugin:** backend-development
**Subagents:** backend-architect
**Skills:** none

## Phases

1. **Route implementation**: Create `creator.py` route file with all 5 endpoints and Pydantic request/response models
2. **App wiring**: Register creator router in `create_app()` and test conftest `_make_app()`
3. **Tests**: New `tests/ui/test_creator.py` covering all endpoints with seeded DraftStep fixtures

## Architecture Decisions

### Background pattern for generate
**Choice:** 202 + BackgroundTasks matching trigger_run in runs.py exactly
**Rationale:** StepCreatorPipeline.execute() blocks for 4 LLM calls (~30-60s). CEO resolved: match trigger_run. Pre-create PipelineRun + DraftStep before background task so frontend can poll immediately. UIBridge + CompositeEmitter for WS events. Error path sets DraftStep.status="error" and PipelineRun.status="failed".
**Alternatives:** asyncio.to_thread inline (rejected -- inconsistent with codebase, blocking threadpool)

### Writable session access pattern
**Choice:** `Session(engine)` directly (from `request.app.state.engine`) for write endpoints
**Rationale:** trigger_run uses this pattern. Dependency injection (`DBSession`) is read-only `ReadOnlySession`. Write endpoints need commit control. StepIntegrator owns commit/rollback -- caller must not commit.
**Alternatives:** Dependency injection with writable session (rejected -- not established pattern, breaks integrator contract)

### target_dir derivation for accept
**Choice:** `{LLM_PIPELINE_STEPS_DIR or default_base}/steps/{step_name}/` computed server-side
**Rationale:** CEO decision: convention-based with env var override. No arbitrary path in request body (security). Default base = project root derived from `llm_pipeline` package location. Env var: `LLM_PIPELINE_STEPS_DIR`.
**Alternatives:** Request body path param (rejected by CEO -- security risk)

### Code edit persistence on test
**Choice:** Merge `code_overrides` into `DraftStep.generated_code` before sandbox run, persist with commit
**Rationale:** CEO decision Q4: "test and save" semantics. Accept endpoint always uses latest persisted code. Frontend (task 49) does not need separate save step.
**Alternatives:** Transient (no persist on test) -- rejected by CEO

### DraftStep upsert for generate
**Choice:** Query by name then insert-or-update (no SQLModel built-in upsert)
**Rationale:** UniqueConstraint on name means re-generation updates existing record. Query-by-name then update/add pattern portable across SQLite and PostgreSQL.
**Alternatives:** ON CONFLICT (SQLite-specific, not portable)

### Seed prompts for StepCreatorPipeline
**Choice:** Lazy call `StepCreatorPipeline.seed_prompts(engine)` on first generate invocation, cached via module-level flag
**Rationale:** app.py already calls seed_prompts for entry-point discovered pipelines. StepCreatorPipeline may not be auto-discovered (depends on entry-point registration). Lazy seed on first call ensures prompts exist without requiring entry-point setup.
**Alternatives:** Always seed at app startup (requires wiring in create_app, couples creator to core app)

### 5 endpoints (not 4)
**Choice:** Implement 5 endpoints: POST /generate, POST /test/{draft_id}, POST /accept/{draft_id}, GET /drafts, GET /drafts/{id}
**Rationale:** VALIDATED_RESEARCH.md recommendation #10 adds GET /drafts/{id} for single draft detail. Task 49 (frontend) needs single-draft fetch. Keeps REST conventions consistent with /runs and /runs/{run_id}.
**Alternatives:** 4 endpoints omitting GET /drafts/{id} (defer to task 49 needs -- low risk since simple read endpoint)

## Implementation Steps

### Step 1: Create creator route module
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** A

1. Create `llm_pipeline/ui/routes/creator.py`
2. Add `APIRouter(prefix="/creator", tags=["creator"])`
3. Define Pydantic request/response models (plain BaseModel, NOT SQLModel):
   - `GenerateRequest`: `description: str`, `target_pipeline: str | None`, `include_extraction: bool = True`, `include_transformation: bool = False`
   - `GenerateResponse`: `run_id: str`, `draft_name: str`, `status: str`
   - `TestRequest`: `code_overrides: dict[str, str] | None = None`, `sample_data: dict | None = None`
   - `TestResponse`: `import_ok: bool`, `security_issues: list[str]`, `sandbox_skipped: bool`, `output: str`, `errors: list[str]`, `modules_found: list[str]`, `draft_status: str`
   - `AcceptRequest`: `pipeline_file: str | None = None`
   - `AcceptResponse`: `files_written: list[str]`, `prompts_registered: int`, `pipeline_file_updated: bool`, `target_dir: str`
   - `DraftItem`: `id: int`, `name: str`, `description: str | None`, `status: str`, `run_id: str | None`, `created_at: datetime`, `updated_at: datetime`
   - `DraftListResponse`: `items: list[DraftItem]`, `total: int`
4. Implement module-level `_seed_done: bool = False` and `_ensure_seeded(engine)` helper that calls `StepCreatorPipeline.seed_prompts(engine)` once
5. Implement `_derive_target_dir(step_name: str) -> Path` helper: reads `LLM_PIPELINE_STEPS_DIR` env var or derives from `llm_pipeline` package parent, appends `steps/{step_name}/`
6. Implement `POST /generate` (sync def, BackgroundTasks, Request, status_code=202):
   - Guard: default_model must be set on app.state (HTTP 422 if None)
   - Call `_ensure_seeded(request.app.state.engine)`
   - Derive `step_name` from `body.description` slug or accept explicit `step_name` field -- NOTE: `StepCreatorInputData` has no `step_name` field; step_name must be derived from the pipeline output. Pre-create DraftStep with `name=run_id[:8]` as placeholder, update in background task when pipeline completes with actual generated name from `GenerationRecord.step_name_generated`
   - Create `run_id = str(uuid.uuid4())`
   - Pre-create `PipelineRun(run_id=run_id, pipeline_name="step_creator", status="running")` in writable Session
   - Pre-create `DraftStep(name=f"draft_{run_id[:8]}", description=body.description, generated_code={}, status="draft", run_id=run_id)` in same writable Session
   - Broadcast WS `run_created` event via `ws_manager.broadcast_global(...)`
   - Define `run_creator()` closure matching trigger_run pattern: UIBridge + BufferedEventHandler + CompositeEmitter, `StepCreatorPipeline(model=default_model, run_id=run_id, engine=engine, event_emitter=emitter)`, `pipeline.execute(data=None, input_data=body.model_dump())`, `pipeline.save()`. On success: query `GenerationRecord` by run_id, update DraftStep name+generated_code+status="draft" in new Session. Error path: `DraftStep.status="error"`, `PipelineRun.status="failed"`. Finally: `bridge.complete()`, `db_buffer.flush()`
   - `background_tasks.add_task(run_creator)`
   - Return `GenerateResponse(run_id=run_id, draft_name=f"draft_{run_id[:8]}", status="accepted")` with HTTP 202
7. Implement `POST /test/{draft_id}` (sync def, Request):
   - Fetch `DraftStep` by id from writable Session; 404 if not found
   - If `body.code_overrides`: merge dict into `draft.generated_code` (shallow merge), set `draft.updated_at = utc_now()`, commit
   - Build `artifacts = dict(draft.generated_code)`
   - Call `StepSandbox().run(artifacts=artifacts, sample_data=body.sample_data)` (sync, may block up to 60s)
   - Persist `draft.test_results = sandbox_result.model_dump()`, `draft.status = "tested" if sandbox_result.import_ok else "error"`, `draft.updated_at = utc_now()`, commit
   - Return `TestResponse(**sandbox_result.model_dump(), draft_status=draft.status)`
8. Implement `POST /accept/{draft_id}` (sync def, Request):
   - Open `Session(engine)` (writable)
   - Fetch `DraftStep` by id; 404 if not found
   - `generated = GeneratedStep.from_draft(draft)` -- may raise KeyError if generated_code malformed; catch and return HTTP 422
   - Compute `target_dir = _derive_target_dir(draft.name)`
   - Instantiate `StepIntegrator(session=session, pipeline_file=Path(body.pipeline_file) if body.pipeline_file else None)`
   - Call `result = integrator.integrate(generated=generated, target_dir=target_dir, draft=draft)` -- integrator commits; caller must NOT commit. Catch Exception, return HTTP 500 with detail
   - Return `AcceptResponse(**result.model_dump())`
9. Implement `GET /drafts` (sync def, DBSession):
   - `select(DraftStep).order_by(DraftStep.created_at.desc())`
   - Return `DraftListResponse(items=[DraftItem(...)], total=count)`
10. Implement `GET /drafts/{draft_id}` (sync def, DBSession):
    - Fetch by id; 404 if not found
    - Return `DraftItem(...)`

### Step 2: Register creator router in app.py and conftest
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** B

1. In `llm_pipeline/ui/app.py`, add import `from llm_pipeline.ui.routes.creator import router as creator_router` in the Route modules section
2. Add `app.include_router(creator_router, prefix="/api")` after the pipelines_router include
3. In `tests/ui/conftest.py`, add `from llm_pipeline.ui.routes.creator import router as creator_router` import in `_make_app()`
4. Add `app.include_router(creator_router, prefix="/api")` to `_make_app()` after pipelines_router

### Step 3: Implement creator endpoint tests
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** C

1. Create `tests/ui/test_creator.py`
2. Add `_make_seeded_creator_app()` helper (or extend conftest with `seeded_creator_client` fixture): in-memory SQLite, insert 2 DraftStep rows (one status="draft" with valid generated_code dict, one status="tested")
3. `TestGenerateEndpoint`:
   - `test_generate_returns_202_accepted`: POST /api/creator/generate with valid description; mock `StepCreatorPipeline` to avoid real LLM calls; assert 202 + run_id in body; assert PipelineRun row created
   - `test_generate_missing_model_returns_422`: set `app.state.default_model = None`; assert 422
4. `TestTestEndpoint`:
   - `test_test_no_overrides_runs_sandbox`: POST /api/creator/test/{id}; mock `StepSandbox.run` returning `SandboxResult(import_ok=True, sandbox_skipped=True, ...)`; assert 200 + import_ok=True
   - `test_test_with_code_overrides_persists`: provide `code_overrides`; assert DraftStep.generated_code updated in DB
   - `test_test_404_for_missing_draft`: POST /api/creator/test/9999; assert 404
5. `TestAcceptEndpoint`:
   - `test_accept_calls_integrator_and_returns_result`: mock `StepIntegrator.integrate` to return `IntegrationResult(...)`; assert 200 + files_written in body
   - `test_accept_404_for_missing_draft`: assert 404
   - `test_accept_with_pipeline_file`: pass `pipeline_file` param; assert `StepIntegrator.__init__` called with `Path(pipeline_file)`
6. `TestDraftsEndpoint`:
   - `test_list_drafts_returns_all`: GET /api/creator/drafts; assert 200 + total=2
   - `test_get_draft_by_id`: GET /api/creator/drafts/{id}; assert 200 + correct name
   - `test_get_draft_404`: GET /api/creator/drafts/9999; assert 404

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| step_name not known before pipeline execution | Medium | Pre-create DraftStep with `draft_{run_id[:8]}` placeholder name; update name from GenerationRecord after pipeline completes. GenerationRecord.step_name_generated is populated by StepCreatorPipeline.save(). |
| StepSandbox.run() blocks threadpool worker for up to 60s | Medium | Test endpoint is sync def so FastAPI wraps in threadpool. Acceptable for current scale; document timeout behavior in docstring. Future: add timeout wrapper. |
| File+DB non-atomicity in StepIntegrator | Medium | Task 47 documented this limitation. DraftStep.status="draft" is recovery signal. No change needed for task 48. |
| Session lifecycle in accept endpoint | High | Must open Session(engine) in endpoint, pass to StepIntegrator, NOT commit from endpoint side. Integrator owns commit. Confirm with integration test that status="accepted" persists. |
| GenerationRecord not written if pipeline fails mid-execution | Low | Error path sets DraftStep.status="error". Frontend polls run status. No recovery needed for task 48. |
| Seed prompts failure on first generate | Low | Wrap `_ensure_seeded` in try/except with warning log (matches app.py pattern for seed_prompts failures). Pipeline still proceeds. |

## Success Criteria

- [ ] POST /api/creator/generate returns 202 with run_id; PipelineRun row pre-created; background task wired with UIBridge+CompositeEmitter
- [ ] POST /api/creator/test/{draft_id} merges code_overrides into DraftStep.generated_code and persists before running sandbox
- [ ] POST /api/creator/accept/{draft_id} calls StepIntegrator with computed target_dir; DraftStep.status="accepted" after success
- [ ] GET /api/creator/drafts returns paginated list ordered by created_at desc
- [ ] GET /api/creator/drafts/{id} returns single draft or 404
- [ ] Creator router registered in create_app() and test conftest _make_app()
- [ ] All endpoints are sync def (not async def)
- [ ] Write endpoints use Session(engine) directly (not DBSession dependency)
- [ ] All tests in tests/ui/test_creator.py pass with mocked creator module calls
- [ ] pytest passes with no new failures

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** All blocking decisions resolved. session lifecycle and step_name placeholder pattern add moderate complexity. Background task pattern is well-established (trigger_run reference). Mocking StepCreatorPipeline in tests avoids LLM calls.
**Suggested Exclusions:** review
