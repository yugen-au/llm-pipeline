# Codebase Architecture Research - Task 24

## Package Structure

```
llm_pipeline/
  __init__.py              # Re-exports all public symbols
  pipeline.py              # PipelineConfig (ABC) - orchestrator
  strategy.py              # PipelineStrategy, PipelineStrategies, StepDefinition
  step.py                  # LLMStep, LLMResultMixin, step_definition decorator
  context.py               # PipelineContext (BaseModel)
  extraction.py            # PipelineExtraction (ABC)
  transformation.py        # PipelineTransformation (ABC)
  registry.py              # PipelineDatabaseRegistry (ABC)
  state.py                 # PipelineStepState, PipelineRunInstance, PipelineRun
  introspection.py         # PipelineIntrospector (task 23 output)
  types.py                 # ArrayValidationConfig, ValidationContext, StepCallParams
  llm/
    provider.py            # LLMProvider (ABC)
    gemini.py              # GeminiProvider implementation
    executor.py            # execute_llm_step()
    result.py              # LLMCallResult
    schema.py, validation.py, rate_limiter.py
  prompts/
    service.py, loader.py, variables.py
  db/
    __init__.py            # init_pipeline_db(), get_engine(), get_session()
    prompt.py              # Prompt SQLModel
  events/
    types.py, models.py, emitter.py, handlers.py
  session/
    readonly.py            # ReadOnlySession wrapper
  ui/
    __init__.py            # Exports create_app
    app.py                 # create_app() factory
    deps.py                # DBSession dependency (ReadOnlySession)
    bridge.py              # UIBridge event forwarding
    cli.py                 # CLI entry point
    routes/
      pipelines.py         # EMPTY - router only, no endpoints (target file)
      runs.py              # Full endpoints: list, detail, trigger, context evolution
      prompts.py           # Full endpoints: list, detail
      steps.py             # Step detail endpoint
      events.py            # Events endpoints
      websocket.py         # WebSocket connection manager
```

## Core Class Hierarchy

### PipelineConfig (pipeline.py)
- ABC base class, ~1150 lines
- ClassVars: `REGISTRY: Type[PipelineDatabaseRegistry]`, `STRATEGIES: Type[PipelineStrategies]`
- Set via `__init_subclass__(cls, registry=None, strategies=None)`
- Naming: class must end with `Pipeline` suffix; enforces matching `{Prefix}Registry` and `{Prefix}Strategies` names
- Constructor: `__init__(strategies, session, engine, provider, variable_resolver, event_emitter, run_id)`
- Key method: `execute(data, initial_context, use_cache, consensus_polling)` - runs pipeline
- Owns: `_instructions` (StepKeyDict), `_context` (dict), `data` (StepKeyDict), `extractions` (dict)
- Execution: iterates step positions, selects strategy via `can_handle(context)`, instantiates step via `StepDefinition.create_step(pipeline)`
- `pipeline_name` property: auto-derived snake_case from class name minus "Pipeline"

### PipelineStrategy (strategy.py)
- ABC with `can_handle(context) -> bool` and `get_steps() -> List[StepDefinition]`
- `__init_subclass__` auto-generates `NAME` (snake_case) and `DISPLAY_NAME` (Title Case) from class name
- Naming: must end with `Strategy` suffix
- Properties: `name`, `display_name`

### PipelineStrategies (strategy.py)
- ABC container for strategy class list
- ClassVar: `STRATEGIES: List[Type[PipelineStrategy]]`
- Set via `__init_subclass__(cls, strategies=None)`
- `create_instances()` -> instantiates all strategy classes
- `get_strategy_names()` -> list of strategy names

### StepDefinition (strategy.py)
- Dataclass connecting step class to its config
- Fields: `step_class`, `system_instruction_key`, `user_prompt_key`, `instructions`, `action_after`, `extractions`, `transformation`, `context`
- `create_step(pipeline)` -> configured step instance with prompt auto-discovery

### LLMStep (step.py)
- ABC base for pipeline steps
- Constructor: `__init__(system_instruction_key, user_prompt_key, instructions, pipeline)`
- `step_name` property: auto-derived snake_case from class name minus "Step"
- Abstract: `prepare_calls() -> List[StepCallParams]`
- Optional: `process_instructions()`, `should_skip()`, `log_instructions()`, `extract_data()`
- Naming: must end with `Step` suffix

### step_definition Decorator (step.py)
- Stores config on class: `INSTRUCTIONS`, `DEFAULT_SYSTEM_KEY`, `DEFAULT_USER_KEY`, `DEFAULT_EXTRACTIONS`, `DEFAULT_TRANSFORMATION`, `CONTEXT`
- Adds `create_definition()` classmethod -> StepDefinition factory
- Enforces naming: instruction class = `{StepPrefix}Instructions`, transformation = `{StepPrefix}Transformation`, context = `{StepPrefix}Context`

### LLMResultMixin (step.py)
- BaseModel mixin for LLM result schemas
- Adds: `confidence_score`, `notes` fields
- `get_example()`, `create_failure()` classmethods
- Validates `example` class attribute if present

### PipelineContext (context.py)
- BaseModel base for step context contributions
- Naming: `{StepPrefix}Context`

### PipelineExtraction (extraction.py)
- ABC with ClassVar `MODEL: Type[SQLModel]`
- Set via `__init_subclass__(cls, model=None)`
- Smart method detection: `default()` -> strategy-named method -> single custom method
- Validates instances before returning (NaN, Infinity, NULL checks)
- Naming: must end with `Extraction`

### PipelineTransformation (transformation.py)
- ABC with ClassVars `INPUT_TYPE`, `OUTPUT_TYPE`
- Set via `__init_subclass__(cls, input_type=None, output_type=None)`
- Smart method detection similar to PipelineExtraction
- Type validation on input/output

### PipelineDatabaseRegistry (registry.py)
- ABC with ClassVar `MODELS: List[Type[SQLModel]]`
- Set via `__init_subclass__(cls, models=None)`
- `get_models()` returns ordered model list
- Single source of truth for table creation and FK insertion order

### State Models (state.py)
- `PipelineStepState` (table=True): audit trail per step execution
- `PipelineRunInstance` (table=True): links created instances to runs
- `PipelineRun` (table=True): run lifecycle (start/complete/fail)

### LLMProvider (llm/provider.py)
- ABC with `call_structured()` method
- GeminiProvider implementation in gemini.py

## Introspection Module (Task 23 Output)

### PipelineIntrospector (introspection.py)
- Pure class-level introspection, no DB/FastAPI/LLM deps
- Constructor: `__init__(pipeline_cls: Type[PipelineConfig])`
- `get_metadata() -> Dict[str, Any]` (cached by `id(pipeline_cls)`)
- Returns dict with keys:
  - `pipeline_name`: str (snake_case)
  - `registry_models`: List[str] (model class names)
  - `strategies`: List[Dict] (each with name, display_name, class_name, steps, optional error)
  - `execution_order`: List[str] (deduplicated step names across strategies)
- Each strategy step entry:
  - `step_name`, `class_name`, `system_key`, `user_key`
  - `instructions_class`, `instructions_schema` (JSON Schema dict)
  - `context_class`, `context_schema`
  - `extractions` (list of {class_name, model_class, methods})
  - `transformation` (null or {class_name, input_type, input_schema, output_type, output_schema})
  - `action_after`
- Defensively handles broken strategies (captured in "error" key, no exception)
- Class-level cache: `_cache: ClassVar[Dict[int, Dict]]`

## Pipeline Discovery / Registration

### Two Separate Registries in create_app()

```python
def create_app(
    db_path=None, cors_origins=None,
    pipeline_registry=None,          # Dict[str, factory_callable] for run triggering
    introspection_registry=None,     # Dict[str, Type[PipelineConfig]] for introspection
) -> FastAPI:
```

1. **pipeline_registry** (app.state.pipeline_registry): maps pipeline names to factory callables
   - Signature: `(run_id: str, engine: Engine, event_emitter: PipelineEventEmitter | None) -> pipeline`
   - Used by `POST /api/runs` to trigger pipeline execution
   - Returns instantiated pipeline objects

2. **introspection_registry** (app.state.introspection_registry): maps pipeline names to PipelineConfig subclass types
   - Used for class-level introspection (task 24 endpoints)
   - Passed to PipelineIntrospector(cls).get_metadata()
   - No instantiation needed

Both default to empty dict if not provided.

## Existing Route Patterns (for consistency)

### Response Models
- Plain Pydantic BaseModel (NOT SQLModel)
- Paginated lists: `{items: List[ItemModel], total: int, offset: int, limit: int}`
- Detail responses: domain-specific structure

### Endpoint Conventions
- All sync def (SQLite is sync, FastAPI wraps in threadpool)
- DBSession dependency for DB access (ReadOnlySession wrapper)
- Request dependency for app.state access
- HTTPException(404) for not-found
- Query params via Pydantic model with Depends()

### Current Pipelines Router (EMPTY)
```python
# llm_pipeline/ui/routes/pipelines.py
router = APIRouter(prefix="/pipelines", tags=["pipelines"])
```
Already included in create_app() with prefix="/api" -> final path: `/api/pipelines`

## Key Findings for Implementation

1. **Target file**: `llm_pipeline/ui/routes/pipelines.py` (exists, empty router)
2. **No DB needed**: introspection is pure class-level, access app.state.introspection_registry via Request
3. **PipelineIntrospector already cached**: safe to call get_metadata() per request
4. **Follow existing patterns**: Pydantic response models, sync endpoints, HTTPException for errors
5. **app.py needs NO changes**: router already wired, introspection_registry already stored
6. **conftest.py needs update**: `_make_app()` doesn't set `app.state.introspection_registry` (only sets `pipeline_registry`)

## Upstream Task 23 Deviations (from SUMMARY.md)
- Step entries include extra fields `context_class`, `context_schema`, `action_after` not in original plan. Accepted: task 24 consumes these.
- `_introspect_strategy()` accepts pre-resolved step_defs (from double-instantiation fix). No impact on task 24.
- Pre-existing test failures: `test_events_router_prefix` and `test_file_based_sqlite_sets_wal` - not related to task 24.

## Out of Scope
- Task 40 (pending): Frontend Pipeline Structure View - consumes these endpoints
- Task 52 (pending): Visual Editor compile/validate endpoints
