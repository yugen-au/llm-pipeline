# Step 2: Existing Creator Module Analysis

## Creator Module Structure

```
llm_pipeline/creator/
  __init__.py          # exports StepCreatorPipeline, StepIntegrator
  pipeline.py          # StepCreatorPipeline + supporting classes
  models.py            # GeneratedStep, IntegrationResult, GenerationRecord, etc.
  schemas.py           # Instructions + Context classes (4 pairs)
  steps.py             # 4 LLMStep subclasses + GenerationRecordExtraction
  integrator.py        # StepIntegrator (file writer + DB + AST modifier)
  sandbox.py           # StepSandbox (Docker) + CodeSecurityValidator + SandboxResult
  ast_modifier.py      # modify_pipeline_file() AST splice
  prompts.py           # ALL_PROMPTS dicts + seed_prompts()
  sample_data.py       # SampleDataGenerator for sandbox test fixtures
  templates/__init__.py # Jinja2 render_template()
```

---

## Class Interfaces

### StepCreatorPipeline (pipeline.py)

Inherits `PipelineConfig`. The fully wired meta-pipeline.

```python
class StepCreatorPipeline(PipelineConfig,
    registry=StepCreatorRegistry,
    strategies=StepCreatorStrategies,
    agent_registry=StepCreatorAgentRegistry):

    INPUT_DATA: ClassVar[type] = StepCreatorInputData

    @classmethod
    def seed_prompts(cls, engine: Engine) -> None: ...
```

**Constructor** (inherited from PipelineConfig):
```python
def __init__(
    self,
    model: str,                                    # pydantic-ai model string
    strategies: Optional[List[PipelineStrategy]] = None,
    session: Optional[Session] = None,
    engine: Optional[Engine] = None,
    variable_resolver: Optional[VariableResolver] = None,
    event_emitter: Optional[PipelineEventEmitter] = None,
    run_id: Optional[str] = None,
    instrumentation_settings: Any | None = None,
): ...
```

**Execute** (inherited from PipelineConfig):
```python
def execute(
    self,
    data: Any = None,
    initial_context: Optional[Dict[str, Any]] = None,
    input_data: Optional[Dict[str, Any]] = None,
    use_cache: bool = False,
) -> PipelineConfig:  # returns self
```

- SYNC method (not async)
- Long-running: 4 sequential LLM calls
- After execute: `pipeline.context` contains flat dict of all step outputs

**InputData**:
```python
class StepCreatorInputData(PipelineInputData):
    description: str
    target_pipeline: str | None = None
    include_extraction: bool = True
    include_transformation: bool = False
```

### StepSandbox (sandbox.py)

```python
class StepSandbox:
    def __init__(self, image: str = "python:3.11-slim", timeout: int = 60): ...

    def run(
        self,
        artifacts: dict[str, str],        # filename -> code content
        sample_data: dict | None = None,
    ) -> SandboxResult: ...

    def validate_code(self, code: str) -> list[str]: ...  # AST-only scan
```

- SYNC method
- Layer 1: AST security denylist scan (always runs, fast)
- Layer 2: Docker container import check (skipped if Docker unavailable)
- Graceful degradation: returns SandboxResult with sandbox_skipped=True when no Docker

### StepIntegrator (integrator.py)

```python
class StepIntegrator:
    def __init__(
        self,
        session: Session,                  # WRITABLE Session, NOT ReadOnlySession
        pipeline_file: Path | None = None, # target pipeline.py for AST mods
    ) -> None: ...

    def integrate(
        self,
        generated: GeneratedStep,
        target_dir: Path,
        draft: DraftStep | None = None,
    ) -> IntegrationResult: ...
```

- SYNC method
- All-or-nothing transaction: owns commit/rollback
- Caller must NOT commit the session
- 7 phases: dir setup, file writes, prompt DB registration, AST modification, DraftStep update, commit, rollback on failure

### CodeSecurityValidator (sandbox.py)

```python
class CodeSecurityValidator:
    def validate(self, code: str) -> list[str]:  # returns security issues, empty=clean
```

---

## Data Models

### Pydantic Models (transient, for API request/response)

```python
class GeneratedStep(BaseModel):
    step_name: str
    step_class_name: str
    instructions_class_name: str
    step_code: str
    instructions_code: str
    prompts_code: str
    extraction_code: str | None = None
    all_artifacts: dict[str, str]

    @classmethod
    def from_draft(cls, draft: DraftStep) -> GeneratedStep: ...

class IntegrationResult(BaseModel):
    files_written: list[str]
    prompts_registered: int
    pipeline_file_updated: bool
    target_dir: str

class SandboxResult(BaseModel):
    import_ok: bool = False
    security_issues: list[str] = []
    sandbox_skipped: bool = True
    output: str = ""
    errors: list[str] = []
    modules_found: list[str] = []
```

### SQLModel Models (persisted)

```python
class DraftStep(SQLModel, table=True):
    __tablename__ = "draft_steps"
    id: Optional[int]           # PK, auto
    name: str                   # unique constraint
    description: Optional[str]
    generated_code: dict        # JSON column, artifact dict
    test_results: Optional[dict]       # JSON column
    validation_errors: Optional[dict]  # JSON column
    status: str                 # "draft" | "tested" | "accepted" | "error"
    run_id: Optional[str]       # traceability to creator_generation_records
    created_at: datetime
    updated_at: datetime

class DraftPipeline(SQLModel, table=True):
    __tablename__ = "draft_pipelines"
    id: Optional[int]
    name: str                   # unique constraint
    structure: dict             # JSON column
    compilation_errors: Optional[dict]
    status: str                 # "draft" | "tested" | "accepted" | "error"
    created_at: datetime
    updated_at: datetime

class GenerationRecord(SQLModel, table=True):
    __tablename__ = "creator_generation_records"
    id: Optional[int]
    run_id: str
    step_name_generated: str
    files_generated: list[str]  # JSON column
    is_valid: bool
    created_at: datetime
```

---

## Pipeline Context After Execute

After `StepCreatorPipeline.execute()`, `pipeline.context` (flat dict) contains fields from all 4 Context classes:

From RequirementsAnalysisContext:
- `step_name: str`
- `step_class_name: str`
- `instruction_fields: list[dict]`
- `context_fields: list[dict]`
- `extraction_targets: list[dict]`
- `input_variables: list[str]`
- `output_context_keys: list[str]`

From CodeGenerationContext:
- `step_code: str`
- `instructions_code: str`
- `extraction_code: str | None`

From PromptGenerationContext:
- `system_prompt: str`
- `user_prompt_template: str`
- `required_variables: list[str]`
- `prompt_yaml: str`

From CodeValidationContext:
- `is_valid: bool`
- `syntax_valid: bool`
- `llm_review_valid: bool`
- `issues: list[str]`
- `all_artifacts: dict[str, str]`  -- filename -> code content
- `sandbox_valid: bool`
- `sandbox_skipped: bool`
- `sandbox_output: str | None`

---

## Database Session Patterns

### Existing UI Pattern (read-only)
```python
# llm_pipeline/ui/deps.py
def get_db(request: Request) -> Generator[ReadOnlySession, None, None]:
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield ReadOnlySession(session)
    finally:
        session.close()

DBSession = Annotated[ReadOnlySession, Depends(get_db)]
```

### Writable Session Pattern (from trigger_run)
```python
# Direct Session creation for writes
with Session(engine) as session:
    session.add(record)
    session.commit()
```

### Creator Endpoint Needs
- **List/Get drafts**: ReadOnlySession via existing get_db() -- fine
- **Generate**: BackgroundTask needs writable Session(engine) for DraftStep upsert after pipeline completes
- **Test**: May need writable Session for DraftStep.test_results update
- **Accept/Integrate**: StepIntegrator requires writable Session, owns commit/rollback

Recommended: Add a `get_writable_db` dependency alongside existing `get_db`:
```python
def get_writable_db(request: Request) -> Generator[Session, None, None]:
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
```

---

## Existing API Conventions

From `llm_pipeline/ui/routes/`:

1. **Router**: `APIRouter(prefix="/...", tags=["..."])`
2. **Response models**: Plain Pydantic BaseModel (NOT SQLModel)
3. **Request models**: Plain Pydantic BaseModel
4. **Sync endpoints**: All `def`, not `async def` (SQLite is sync)
5. **Background tasks**: `BackgroundTasks` for long-running ops, return 202
6. **Error handling**: `HTTPException(status_code=404, detail="...")`
7. **Pagination**: offset/limit pattern with total count
8. **App state**: `request.app.state.engine`, `request.app.state.pipeline_registry`, `request.app.state.default_model`
9. **Registration**: `app.include_router(router, prefix="/api")`

---

## Endpoint-to-Method Mapping

### POST /api/creator/generate -> 202 (background)
1. Validate request body (description, target_pipeline?, include_extraction?)
2. Check app.state.default_model exists (guard, same as trigger_run)
3. Create run_id, create PipelineRun record
4. Background task:
   - `pipeline = StepCreatorPipeline(model=model, run_id=run_id, engine=engine, event_emitter=emitter)`
   - `pipeline.execute(input_data={"description": ..., ...})`
   - Extract from `pipeline.context`: step_name, all_artifacts, is_valid, issues
   - Upsert DraftStep(name=step_name, generated_code=all_artifacts, status="draft", run_id=run_id)
   - `pipeline.save()`

### POST /api/creator/test/{draft_id} -> 202 or 200
1. Load DraftStep by id
2. Build artifacts dict from DraftStep.generated_code
3. `result = StepSandbox().run(artifacts=artifacts)`
4. Update DraftStep.test_results, DraftStep.status = "tested" if result.import_ok
5. Return SandboxResult fields

### POST /api/creator/accept/{draft_id} -> 200
1. Load DraftStep by id, validate status
2. `generated = GeneratedStep.from_draft(draft)`
3. `integrator = StepIntegrator(session=writable_session, pipeline_file=pipeline_file)`
4. `result = integrator.integrate(generated, target_dir, draft=draft)`
5. Return IntegrationResult fields (session committed by integrator)

### GET /api/creator/drafts -> 200
1. Query DraftStep table with optional status filter, pagination
2. Return list of draft summaries

### GET /api/creator/drafts/{id} -> 200
1. Query single DraftStep by id
2. Return full draft detail including generated_code

---

## Key Observations

1. All creator methods are **sync** -- no async adaptation needed
2. StepIntegrator requires **writable Session** and owns commit -- cannot use ReadOnlySession
3. Generate is **long-running** (4 LLM calls) -- must be background task
4. Sandbox test is **potentially slow** (60s Docker timeout) -- consider background task
5. Accept/integrate is **relatively fast** (file I/O + DB) -- can be sync
6. DraftStep.name has **unique constraint** -- upsert logic needed for re-generation
7. GeneratedStep.from_draft() is the bridge between DraftStep (DB) and integrator input
8. Pipeline context is a **flat dict** -- need to extract specific keys after execute()
9. No existing creator routes -- new router file needed at `llm_pipeline/ui/routes/creator.py`
10. Registration in `create_app()` following existing pattern
