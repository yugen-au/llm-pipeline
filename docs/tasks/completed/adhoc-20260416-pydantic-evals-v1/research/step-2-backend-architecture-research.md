# Backend Architecture Research: pydantic-evals Integration

## 1. YAML Sync System (llm_pipeline/prompts/yaml_sync.py)

### Current Pattern
- **Discovery**: `discover_yaml_prompts(dir)` globs `*.yaml`, parses each via `parse_prompt_yaml(path)`
- **Startup sync**: `sync_yaml_to_db(engine, prompts_dirs)` -- insert if missing, update if YAML version newer (semver compare), skip if same/older
- **Write-back**: `write_prompt_to_yaml(prompts_dir, key, type, data)` -- called from prompts route on UI save; reads existing YAML, merges section, writes back
- **Version conflict**: `compare_versions(a, b)` -- dot-separated numeric comparison, higher version wins
- **Unique key**: `(prompt_key, prompt_type)` pair in DB; one YAML file per prompt_key with system/user sections
- **App state**: `app.state.prompts_dir` stores the project-level writeback target (default: `llm-pipeline-prompts/`)
- **Route trigger**: PUT `/api/prompts/{key}/{type}` calls `write_prompt_to_yaml()` after DB update

### Eval System Parallel
- **Dir**: `llm-pipeline-evals/` (project-level, env override `LLM_PIPELINE_EVALS_DIR`)
- **Format**: Use pydantic-evals native YAML format (Dataset.to_file/from_file) with wrapper metadata
- **Unique key**: dataset `name` field (one file per dataset, `{name}.yaml`)
- **Startup sync**: `sync_eval_datasets_to_db(engine, evals_dirs)` -- parse YAML, upsert EvaluationDataset + EvaluationCase rows. Version compare same as prompts.
- **Write-back**: `write_dataset_to_yaml(evals_dir, name, data)` -- called from evals route on UI save
- **App state**: `app.state.evals_dir` on FastAPI app

### Key Differences from Prompts
- Prompt YAML has custom schema (prompt_key, system/user sections). Eval YAML uses pydantic-evals native Dataset format (cases, evaluators, report_evaluators).
- Prompt sync is per-variant (system/user). Eval sync is per-dataset (one entity = one file).
- Eval YAML includes typed evaluator references (class names + params), prompts don't.

---

## 2. Step Definition Decorator (llm_pipeline/step.py)

### Current Signature
```python
@step_definition(
    instructions: Type[BaseModel],
    default_system_key=None, default_user_key=None,
    default_extractions=None, default_transformation=None,
    context=None, agent=None, model=None,
    review=None,  # StepReview subclass
)
```

### Where `evaluators=` Goes
Add after `review`:
```python
@step_definition(
    instructions=SentimentInstructions,
    review=SentimentReview,
    evaluators=[EqualsExpected(), FieldMatch()],  # NEW
)
class SentimentStep(LLMStep): ...
```

### Storage in StepDefinition (strategy.py)
`StepDefinition` dataclass gets new field:
```python
@dataclass
class StepDefinition:
    # ... existing fields ...
    review: 'StepReview | None' = None
    evaluators: list[Any] = field(default_factory=list)  # pydantic-evals Evaluator instances
```

### Decorator Behavior
- Store on class: `step_class.EVALUATORS = evaluators or []`
- Pass through in `create_definition()`: `kwargs['evaluators'] = cls.EVALUATORS`
- No naming convention needed (evaluators are pydantic-evals @dataclass, not our classes)
- These are step-default evaluators; datasets can add/override case-level evaluators

---

## 3. Discovery System (llm_pipeline/discovery.py)

### Current _LOAD_ORDER
```python
_LOAD_ORDER = ["enums", "constants", "schemas", "extractions", "tools", "steps", "pipelines"]
```

### Evaluator Discovery
**Not needed as separate subfolder.** Evaluators attach via `@step_definition(evaluators=[...])` -- they're imported as part of `steps/` module loading. Custom evaluator classes can live alongside step files or in a project-level `evaluators.py`.

If custom evaluators need shared imports, they go in `schemas/` (already loaded before `steps/`).

### Dataset Discovery
Datasets are YAML files in `llm-pipeline-evals/`, not Python modules. Discovery uses the YAML sync system (parallel to prompts), not the convention directory system. No change to `_LOAD_ORDER`.

---

## 4. DB Models (paralleling state.py + PipelineReview)

### Pattern Observed
- `SQLModel, table=True` with `__tablename__`
- `Optional[int]` PK with `Field(default=None, primary_key=True)`
- String fields with `max_length`
- JSON columns via `sa_column=Column(JSON)`
- Datetime fields with `default_factory=utc_now`
- `__table_args__` tuple with Index and UniqueConstraint
- No SQLAlchemy relationships (flat, query via FK values)

### New Tables

#### EvaluationDataset
```python
class EvaluationDataset(SQLModel, table=True):
    __tablename__ = "evaluation_datasets"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)  # unique, matches YAML filename
    description: Optional[str] = Field(default=None)
    target_type: str = Field(max_length=20)  # "step" or "pipeline"
    target_name: str = Field(max_length=100)  # step_name or pipeline_name
    version: str = Field(default="1.0", max_length=20)
    evaluators_config: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # serialized dataset-level evaluator refs [{class_name: params}]
    case_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    
    __table_args__ = (
        UniqueConstraint("name", name="uq_evaluation_datasets_name"),
        Index("ix_evaluation_datasets_target", "target_type", "target_name"),
    )
```

#### EvaluationCase
```python
class EvaluationCase(SQLModel, table=True):
    __tablename__ = "evaluation_cases"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    dataset_id: int = Field(foreign_key="evaluation_datasets.id")
    name: Optional[str] = Field(default=None, max_length=200)
    inputs: dict = Field(sa_column=Column(JSON))
    expected_output: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    metadata_: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    evaluators_config: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # case-level evaluator overrides
    created_at: datetime = Field(default_factory=utc_now)
    
    __table_args__ = (
        Index("ix_evaluation_cases_dataset", "dataset_id"),
    )
```

#### EvaluationRun
```python
class EvaluationRun(SQLModel, table=True):
    __tablename__ = "evaluation_runs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(max_length=36, sa_column_kwargs={"unique": True})
    dataset_id: int = Field(foreign_key="evaluation_datasets.id")
    dataset_name: str = Field(max_length=100)  # denormalized for queries
    status: str = Field(default="running", max_length=20)
    # running, completed, failed
    model: Optional[str] = Field(default=None, max_length=100)
    case_count: int = Field(default=0)
    pass_count: int = Field(default=0)
    fail_count: int = Field(default=0)
    error_count: int = Field(default=0)
    total_time_ms: Optional[int] = Field(default=None)
    report_data: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # full EvaluationReport serialized
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    
    __table_args__ = (
        Index("ix_evaluation_runs_dataset", "dataset_id"),
        Index("ix_evaluation_runs_status", "status"),
        Index("ix_evaluation_runs_started", "started_at"),
    )
```

#### EvaluationCaseResult
```python
class EvaluationCaseResult(SQLModel, table=True):
    __tablename__ = "evaluation_case_results"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(max_length=36)  # FK to evaluation_runs.run_id
    case_id: Optional[int] = Field(default=None)  # FK to evaluation_cases.id
    case_name: Optional[str] = Field(default=None, max_length=200)
    inputs: dict = Field(sa_column=Column(JSON))
    expected_output: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    actual_output: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    scores: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    # {evaluator_name: {value, reason?}} from ReportCase.scores
    passed: Optional[bool] = Field(default=None)
    duration_ms: Optional[int] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    
    __table_args__ = (
        Index("ix_evaluation_case_results_run", "run_id"),
        Index("ix_evaluation_case_results_case", "case_id"),
    )
```

---

## 5. Route Architecture

### Pattern from reviews.py / runs.py
- `APIRouter(prefix="/evals", tags=["evals"])`
- Pydantic response models (plain BaseModel, not SQLModel)
- `DBSession` (ReadOnlySession) for list/detail reads
- Direct `Session(engine)` for writes (create, update, delete)
- `BackgroundTasks` for eval run execution
- `request.app.state.engine` for engine access
- List endpoints: filters via Query params, pagination (offset/limit), count query + data query
- Detail endpoints: 404 on missing
- Action endpoints: POST with request body, 202 for async operations

### Proposed Routes

```
# Dataset CRUD
GET    /api/evals/datasets                    -> DatasetListResponse
POST   /api/evals/datasets                    -> DatasetDetailResponse (201)
GET    /api/evals/datasets/{name}             -> DatasetDetailResponse
PUT    /api/evals/datasets/{name}             -> DatasetDetailResponse
DELETE /api/evals/datasets/{name}             -> 204

# Case CRUD (nested under dataset)
GET    /api/evals/datasets/{name}/cases       -> CaseListResponse
POST   /api/evals/datasets/{name}/cases       -> CaseDetailResponse (201)
PUT    /api/evals/datasets/{name}/cases/{id}  -> CaseDetailResponse
DELETE /api/evals/datasets/{name}/cases/{id}  -> 204

# Run operations
POST   /api/evals/runs                        -> TriggerEvalResponse (202)
GET    /api/evals/runs                        -> EvalRunListResponse
GET    /api/evals/runs/{run_id}               -> EvalRunDetailResponse
GET    /api/evals/runs/{run_id}/results       -> EvalCaseResultListResponse

# YAML sync
POST   /api/evals/datasets/{name}/sync-yaml   -> sync DB -> YAML writeback
```

### Router Structure
Single file `llm_pipeline/ui/routes/evals.py` with one `APIRouter(prefix="/evals", tags=["evals"])`. Mounted in app.py as `app.include_router(evals_router, prefix="/api")`.

---

## 6. Pipeline Execution Hook Points

### How Step Output is Captured (pipeline.py L998-1009)
```python
run_result = agent.run_sync(user_prompt, deps=step_deps, model=step_model)
instruction = run_result.output  # <-- THIS is what eval task_fn returns
```

### Key Components for Eval Runner's task_fn
1. **build_step_agent()** (agent_builders.py) -- builds pydantic-ai Agent with output_type=instructions_type
2. **StepDeps** -- session, pipeline_context, prompt_service, etc.
3. **PromptService** -- renders system/user prompts from DB
4. **step.build_user_prompt()** -- renders user prompt with variables

### Live Mode task_fn Design
```python
async def make_step_task_fn(step_def, engine, model):
    """Create a task_fn that executes a single step and returns instructions."""
    async def task_fn(inputs: dict) -> BaseModel:
        # 1. Build agent (same as pipeline.execute L901-908)
        agent = build_step_agent(
            step_name=step_def.step_name,
            output_type=step_def.instructions,
            validators=[],
            tools=get_agent_tools(step_def.agent_name) if step_def.agent_name else [],
            system_instruction_key=step_def.system_instruction_key,
        )
        # 2. Build deps
        with Session(engine) as session:
            prompt_service = PromptService(session)
            step_deps = StepDeps(
                session=ReadOnlySession(session),
                prompt_service=prompt_service,
                pipeline_context={},
                run_id="eval",
                pipeline_name="eval",
                step_name=step_def.step_name,
            )
            # 3. Render user prompt from inputs
            user_prompt = prompt_service.get_user_prompt(
                step_def.user_prompt_key, variables=inputs
            )
            # 4. Run agent
            result = await agent.run(user_prompt, deps=step_deps, model=model)
            return result.output
    return task_fn
```

### Full Pipeline task_fn
For pipeline-level evals, the task_fn instantiates the full pipeline:
```python
async def make_pipeline_task_fn(pipeline_cls, engine, model):
    async def task_fn(inputs: dict) -> dict:
        pipeline = pipeline_cls(model=model, engine=engine)
        pipeline.execute(data=None, input_data=inputs)
        # Return all step instructions as dict
        return dict(pipeline.instructions)
    return task_fn
```

---

## 7. Module Layout

### New Files
```
llm_pipeline/
  evals/
    __init__.py          # exports public API
    yaml_sync.py         # discover_eval_datasets, sync_eval_to_db, write_dataset_to_yaml
    models.py            # EvaluationDataset, EvaluationCase, EvaluationRun, EvaluationCaseResult
    runner.py            # EvalRunner -- wraps pydantic-evals Dataset.evaluate()
    evaluators.py        # FieldMatch, InstructionsFieldMatch (auto-generated from schema)
  ui/
    routes/
      evals.py           # all eval routes
```

### DB Init
Add eval models to `llm_pipeline/db/__init__.py` so `init_pipeline_db()` creates tables.

### App Startup
In `create_app()`:
```python
from llm_pipeline.evals.yaml_sync import sync_eval_to_db
evals_dir = Path(evals_dir or os.environ.get("LLM_PIPELINE_EVALS_DIR", "llm-pipeline-evals"))
if evals_dir.is_dir():
    sync_eval_to_db(app.state.engine, evals_dir)
app.state.evals_dir = evals_dir
```

---

## 8. Auto-Generated FieldMatch Evaluator

### Design
Given a step's Instructions class (Pydantic BaseModel), auto-generate evaluators:
```python
def auto_field_evaluators(instructions_cls: Type[BaseModel]) -> list[Evaluator]:
    """Generate FieldMatch evaluators for all fields on instructions class."""
    return [FieldMatch(field_name=name) for name in instructions_cls.model_fields]
```

This uses the FieldMatch evaluator from step-1 research (returns `{}` for None expected fields, self-skipping).

### When Applied
- If `@step_definition(evaluators=[])` is empty and instructions class exists, auto-generate field evaluators
- If evaluators explicitly provided, use those (no auto-generation)
- Step-1 research confirms: `{}` return from evaluator = skip (field not in expected_output)

---

## 9. Integration Points Summary

| Existing Pattern | Eval Parallel | Key File |
|---|---|---|
| `llm-pipeline-prompts/` | `llm-pipeline-evals/` | evals/yaml_sync.py |
| `sync_yaml_to_db()` | `sync_eval_to_db()` | evals/yaml_sync.py |
| `write_prompt_to_yaml()` | `write_dataset_to_yaml()` | evals/yaml_sync.py |
| `app.state.prompts_dir` | `app.state.evals_dir` | ui/app.py |
| `PipelineReview` (state.py) | `EvaluationDataset/Case/Run/CaseResult` | evals/models.py |
| `reviews.py` routes | `evals.py` routes | ui/routes/evals.py |
| `@step_definition(review=)` | `@step_definition(evaluators=)` | step.py |
| `StepDefinition.review` | `StepDefinition.evaluators` | strategy.py |
| `build_step_agent()` + `agent.run_sync()` | eval task_fn | evals/runner.py |
| `trigger_run()` + BackgroundTasks | `trigger_eval()` + BackgroundTasks | ui/routes/evals.py |
