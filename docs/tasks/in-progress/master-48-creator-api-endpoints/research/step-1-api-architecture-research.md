# Creator API Endpoints -- Architecture Research

## Existing Route Architecture

### File Structure
```
llm_pipeline/ui/
  __init__.py          # Import guard for fastapi, exports create_app
  app.py               # create_app() factory, middleware, router mounting
  deps.py              # get_db -> ReadOnlySession, DBSession annotated type
  bridge.py            # UIBridge: sync adapter for pipeline->WS events
  routes/
    __init__.py
    runs.py            # GET/POST /runs, GET /runs/{id}, GET /runs/{id}/context
    steps.py           # GET /runs/{id}/steps, GET /runs/{id}/steps/{n}
    events.py          # GET /runs/{id}/events
    prompts.py         # GET /prompts, GET /prompts/{key}
    pipelines.py       # GET /pipelines, GET /pipelines/{name}, GET .../prompts
    websocket.py       # WS /ws/runs, WS /ws/runs/{id}
```

### Conventions

| Convention | Detail |
|---|---|
| Router prefix | `APIRouter(prefix="/creator", tags=["creator"])` |
| Mount point | `app.include_router(creator_router, prefix="/api")` -> `/api/creator/*` |
| Response models | Plain Pydantic `BaseModel`, NOT SQLModel |
| Request models | Plain Pydantic `BaseModel` |
| DB reads | `DBSession` (Annotated[ReadOnlySession, Depends(get_db)]) |
| DB writes | `Session(request.app.state.engine)` directly (e.g. trigger_run) |
| Long ops | `BackgroundTasks` + 202 status (trigger_run pattern) |
| Sync endpoints | All endpoints are `def` (not `async def`). SQLite is sync, FastAPI threadpool wraps. |
| Error codes | 404 HTTPException for not found, 422 for validation |
| No auth | No authentication middleware on any route |
| Pagination | offset/limit params via Pydantic `BaseModel` with `Query()` defaults |

### App Factory Pattern (app.py)
```python
# Routes imported inside create_app() to avoid circular imports
from llm_pipeline.ui.routes.creator import router as creator_router
app.include_router(creator_router, prefix="/api")
```

## Creator Module -- Classes to Expose

### StepCreatorPipeline
- Location: `llm_pipeline/creator/pipeline.py`
- Signature: `StepCreatorPipeline(model=..., run_id=..., engine=..., ...)`
- Execute: `pipeline.execute(data=None, input_data={'description': ..., 'target_pipeline': ...})`
- After execute, `pipeline.context` contains:
  - `step_name`, `step_class_name` (from RequirementsAnalysis)
  - `step_code`, `instructions_code`, `extraction_code` (from CodeGeneration)
  - `system_prompt`, `user_prompt_template`, `prompt_yaml` (from PromptGeneration)
  - `is_valid`, `all_artifacts: dict[str, str]`, `sandbox_valid`, `issues` (from CodeValidation)
- `pipeline.save()` persists GenerationRecord extraction

### StepSandbox
- Location: `llm_pipeline/creator/sandbox.py`
- Signature: `StepSandbox(image='python:3.11-slim', timeout=60)`
- Run: `sandbox.run(artifacts=dict[str, str], sample_data=dict|None)` -> `SandboxResult`
- SandboxResult: `import_ok, security_issues, sandbox_skipped, output, errors, modules_found`
- Fast operation (AST scan + optional Docker). Can be synchronous.

### StepIntegrator
- Location: `llm_pipeline/creator/integrator.py`
- Signature: `StepIntegrator(session=Session, pipeline_file=Path|None)`
- Run: `integrator.integrate(generated=GeneratedStep, target_dir=Path, draft=DraftStep|None)` -> `IntegrationResult`
- IntegrationResult: `files_written, prompts_registered, pipeline_file_updated, target_dir`
- **Owns commit/rollback** -- caller must NOT commit
- Atomic: file writes + prompt DB registration + AST modification + draft status update

### GeneratedStep
- Location: `llm_pipeline/creator/models.py`
- Factory: `GeneratedStep.from_draft(draft: DraftStep)` -> builds from `draft.generated_code` dict
- Fields: `step_name, step_class_name, instructions_class_name, step_code, instructions_code, prompts_code, extraction_code, all_artifacts`

### DraftStep (DB model)
- Location: `llm_pipeline/state.py`
- Table: `draft_steps`
- Fields: `id, name, description, generated_code(JSON), test_results(JSON), validation_errors(JSON), status(draft|tested|accepted|error), run_id, created_at, updated_at`
- Unique constraint on `name`. Re-generation UPDATEs existing row.

## Proposed Endpoint Design

### POST /api/creator/generate
- **Purpose**: Run StepCreatorPipeline to generate step scaffolding
- **Pattern**: `asyncio.to_thread(pipeline.execute, ...)` -- returns result inline (task spec pattern). Long-running (4 LLM calls, 30-60s). Frontend shows loading spinner.
- **Request body**: `{ step_name: str, description: str, target_pipeline?: str, include_extraction?: bool }`
- **Flow**:
  1. Create or update DraftStep (upsert on name, status="draft")
  2. Build StepCreatorPipeline with model from app.state.default_model
  3. Execute via `asyncio.to_thread()` (sync pipeline in thread)
  4. Extract artifacts from `pipeline.context`
  5. Update DraftStep with generated_code, run_id
  6. Return `{ draft_id: int, generated_code: dict, is_valid: bool }`
- **Session handling**: Needs writable Session for DraftStep upsert. Create Session(engine) directly.

### POST /api/creator/test/{draft_id}
- **Purpose**: Test generated code in sandbox
- **Pattern**: Synchronous -- sandbox is fast (AST scan)
- **Request body**: `{ code_overrides?: dict[str, str], sample_data?: dict }`
- **Flow**:
  1. Fetch DraftStep by id (404 if missing)
  2. Merge code_overrides with draft.generated_code
  3. Run StepSandbox.run(artifacts, sample_data)
  4. Update DraftStep with test_results, status="tested" if import_ok
  5. Return SandboxResult fields
- **Session handling**: Writable Session for DraftStep update

### POST /api/creator/accept/{draft_id}
- **Purpose**: Integrate accepted step into pipeline project
- **Pattern**: Synchronous -- file writes + DB operations
- **Request body**: `{ target_dir?: str, pipeline_file?: str }`
- **Flow**:
  1. Fetch DraftStep by id (404 if missing, 409 if already accepted)
  2. Build GeneratedStep.from_draft(draft)
  3. Create StepIntegrator(session=..., pipeline_file=...)
  4. Call integrator.integrate(generated, target_dir, draft=draft)
  5. Return IntegrationResult
- **Session handling**: StepIntegrator owns commit. Pass writable Session.
- **OPEN QUESTION**: target_dir and pipeline_file resolution strategy

### GET /api/creator/drafts
- **Purpose**: List draft steps
- **Pattern**: Read-only, uses DBSession (ReadOnlySession)
- **Query params**: `status?: str, offset: int = 0, limit: int = 50`
- **Returns**: Paginated list of DraftStep summaries

## Test Pattern

### Existing UI test infrastructure
- `tests/ui/conftest.py`: `_make_app()` creates in-memory SQLite + StaticPool + all routers. `app_client` and `seeded_app_client` fixtures.
- Test classes: `TestListRuns`, `TestGetRun`, `TestTriggerRun` etc.
- Uses `starlette.testclient.TestClient`.
- Creator tests should add creator router to `_make_app()` and seed DraftStep rows.

## Upstream Task 47 Deviations

Key deviation from task 47 (StepIntegrator) relevant to task 48:

- **Task 47 recommendation #1**: "The accept endpoint should create a Session, retrieve the DraftStep, call integrator.integrate(generated, target_dir, draft=draft), and return IntegrationResult. It must NOT commit (integrator owns commit)."
- StepIntegrator.integrate() re-parses AST after each splice step (4 calls). Functionally equivalent to plan spec.
- Extra parameter: `pipeline_file: Path | None` controls whether AST modification runs.

## Downstream Task 49 Scope (OUT OF SCOPE)

Task 49: "Create Step Creator Frontend View (Phase 3)" -- React UI with Monaco editor, generate/test/accept button flow. Frontend API hooks. NOT part of this task.

## Open Architectural Questions

**Q1: target_dir for accept endpoint**
StepIntegrator.integrate() requires `target_dir: Path` -- where generated step files are written. Options:
  - (a) Accept as request body parameter (flexible, security risk -- arbitrary filesystem writes)
  - (b) Convention: `{configurable_base}/steps/{step_name}/` -- safe, predictable
  - (c) Env var / app.state config for base directory

**Q2: AST pipeline file modification in accept flow**
StepIntegrator supports `pipeline_file=None` (skip AST) or `pipeline_file=Path` (splice imports + step registration into existing pipeline). Should accept endpoint:
  - (a) Always skip AST modification (simpler, user manually integrates)
  - (b) Accept pipeline_file as optional parameter (flexible)
  - (c) Auto-detect from target_pipeline name via introspection_registry

Both questions affect the accept endpoint request model and the StepIntegrator instantiation. Cannot finalize accept endpoint design without these answers.
