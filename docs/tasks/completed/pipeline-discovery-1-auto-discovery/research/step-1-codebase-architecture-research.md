# Step 1: Codebase Architecture Research -- Pipeline Auto-Discovery

## 1. create_app() (llm_pipeline/ui/app.py)

### Current signature
```python
def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None,
) -> FastAPI:
```

### Behavior
- Creates FastAPI app, adds CORS + GZip middleware
- Initializes DB engine via `init_pipeline_db()` (supports `db_path` or env `LLM_PIPELINE_DB`)
- Stores `engine`, `pipeline_registry`, `introspection_registry` on `app.state`
- Mounts 6 routers: runs, steps, events, prompts, pipelines, websocket
- Both registries default to empty dicts `{}`

### Changes needed (task 1)
- Add `auto_discover: bool = True` param
- Add `default_model: Optional[str] = None` param (task 2 wires from CLI `--model`)
- Discovery logic between engine init and router mounting

---

## 2. Registry patterns

### pipeline_registry (app.state.pipeline_registry)
- Type: `dict[str, Callable]`
- Maps pipeline name -> factory callable
- Factory signature (from trigger_run L223): `factory(run_id=str, engine=Engine, event_emitter=UIBridge, input_data=dict)`
- Consumed by `POST /api/runs` in `trigger_run()` to instantiate + execute pipelines
- The factory must accept `input_data` kwarg even though `PipelineConfig.__init__` does not use it (trigger_run passes it)

### introspection_registry (app.state.introspection_registry)
- Type: `Dict[str, Type[PipelineConfig]]`
- Maps pipeline name -> PipelineConfig subclass type (class, not instance)
- Consumed by `GET /api/pipelines` and `GET /api/pipelines/{name}` via `PipelineIntrospector`
- `PipelineIntrospector(cls).get_metadata()` extracts pipeline_name, registry_models, strategies, execution_order, pipeline_input_schema -- all from class-level attributes, no instantiation needed

---

## 3. PipelineConfig (llm_pipeline/pipeline.py)

### Class-level attributes
```python
REGISTRY: ClassVar[Type[PipelineDatabaseRegistry]]  # required
STRATEGIES: ClassVar[Type[PipelineStrategies]]       # required
AGENT_REGISTRY: ClassVar[Optional[Type[AgentRegistry]]]
INPUT_DATA: ClassVar[Optional[Type[PipelineInputData]]]
```

### __init__ signature
```python
def __init__(
    self,
    model: str,                          # REQUIRED - pydantic-ai model string
    strategies: Optional[List] = None,
    session: Optional[Session] = None,
    engine: Optional[Engine] = None,
    variable_resolver: Optional = None,
    event_emitter: Optional = None,
    run_id: Optional[str] = None,
    instrumentation_settings: Any | None = None,
):
```

### Naming enforcement
- Class must end with "Pipeline" suffix
- Registry must be `{Prefix}Registry`
- Strategies must be `{Prefix}Strategies`
- `pipeline_name` property: strips "Pipeline" suffix, converts CamelCase to snake_case

### issubclass check
- `PipelineConfig` is an ABC -- can use `issubclass(cls, PipelineConfig)` for validation

---

## 4. Factory closure design

Based on trigger_run() call at L223:
```python
pipeline = factory(run_id=run_id, engine=engine, event_emitter=bridge, input_data=body.input_data or {})
pipeline.execute(data=None, input_data=body.input_data)
pipeline.save()
```

Factory closure must:
1. Capture `model` (from `default_model` param or env var) at closure creation time
2. Accept `run_id`, `engine`, `event_emitter`, `input_data` as kwargs (match trigger_run call)
3. Instantiate PipelineConfig subclass with: `cls(model=model, run_id=run_id, engine=engine, event_emitter=event_emitter)`
4. Ignore `input_data` in __init__ (it's passed to execute() separately by trigger_run)
5. Use `**kwargs` for forward-compat

```python
def _make_factory(cls, model):
    def factory(*, run_id, engine, event_emitter=None, **kwargs):
        return cls(model=model, run_id=run_id, engine=engine, event_emitter=event_emitter)
    return factory
```

---

## 5. Entry point discovery

### importlib.metadata usage
```python
from importlib.metadata import entry_points
eps = entry_points(group="llm_pipeline.pipelines")
for ep in eps:
    cls = ep.load()  # loads the class
    # ep.name = entry point name (e.g. "text_analyzer")
```

### Current pyproject.toml entry points
```toml
[project.scripts]
llm-pipeline = "llm_pipeline.ui.cli:main"
```
No `[project.entry-points]` section exists yet. Task 3 adds:
```toml
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
```

---

## 6. seed_prompts pattern

### Does not exist yet
No `seed_prompts` implementation in the codebase. Task 3 (demo pipeline) will create it.

### Expected pattern (from PRD)
- Optional classmethod on PipelineConfig subclasses: `seed_prompts(engine: Engine) -> None`
- Inserts Prompt rows if not present (idempotent via prompt_key+prompt_type unique constraint)
- Called during discovery, after engine is available

### Detection in discovery
```python
if hasattr(cls, 'seed_prompts') and callable(cls.seed_prompts):
    cls.seed_prompts(engine)
```

### Prompt model (llm_pipeline/db/prompt.py)
- `Prompt(SQLModel, table=True)` with `__tablename__ = "prompts"`
- Unique constraint: `(prompt_key, prompt_type)` -- enables idempotent inserts
- Fields: prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables, version

---

## 7. CLI (llm_pipeline/ui/cli.py)

### Current structure
- `main()` -> argparse with `ui` subcommand
- `_run_ui(args)` -> creates app via `create_app(db_path=args.db)`
- Dev mode: `_run_dev_mode` -> Vite + FastAPI or headless reload
- Prod mode: `_run_prod_mode` -> static files + uvicorn
- `_create_dev_app()` factory for uvicorn reload mode

### Changes needed (task 2, OUT OF SCOPE for task 1)
- Add `--pipelines` and `--model` flags
- Pass to create_app()

### Task 1 impact on CLI
- create_app() signature change is backward-compatible (new params have defaults)
- All existing CLI call sites (`create_app(db_path=args.db)`) continue to work
- `_create_dev_app()` also needs updating eventually but that's task 2 scope

---

## 8. Existing tests reference

### tests/ui/conftest.py
- `_make_app()` creates app manually (does not use create_app()) with in-memory SQLite + StaticPool
- Sets `app.state.pipeline_registry = {}` -- no introspection_registry set
- Tests should mock `importlib.metadata.entry_points` for discovery testing

### tests/ui/test_pipelines.py
- Uses `WidgetPipeline` and `ScanPipeline` from `tests/test_introspection.py` as fixtures
- Manually sets `app.state.introspection_registry = {"widget": WidgetPipeline, ...}`
- Pattern: create app, set state, wrap in TestClient

### tests/test_introspection.py
- Defines minimal pipeline classes: WidgetPipeline, ScanPipeline
- Uses llm_pipeline.* imports (PipelineConfig, LLMStep, etc.)
- Good reference for creating mock PipelineConfig subclasses in tests

---

## 9. Discovery implementation plan

### Order of operations in create_app()
1. Create FastAPI app
2. Add middleware
3. Init DB engine
4. **NEW: Run entry point discovery (if auto_discover)**
   a. Resolve default model (param > env var > hardcoded default)
   b. Scan `importlib.metadata.entry_points(group="llm_pipeline.pipelines")`
   c. For each entry point:
      - `ep.load()` wrapped in try/except
      - Validate `issubclass(cls, PipelineConfig)`
      - Register `ep.name -> cls` in introspection_registry
      - Register `ep.name -> factory_closure` in pipeline_registry
      - Call `cls.seed_prompts(engine)` if present
      - Log warning on any error, continue
   d. Merge with any manually provided registries (manual overrides auto)
   e. Log all discovered pipelines
5. Store registries on app.state
6. Mount routers

### Default model resolution
```
default_model param > LLM_PIPELINE_MODEL env var > "google-gla:gemini-2.0-flash-lite"
```

---

## 10. Downstream task boundaries

### Task 2 (CLI flags) -- OUT OF SCOPE
- `--pipelines` flag, `--model` flag
- Module import + PIPELINE_REGISTRY dict lookup
- Wiring CLI args to create_app()

### Task 3 (demo pipeline) -- OUT OF SCOPE
- TextAnalyzerPipeline implementation
- seed_prompts() implementation
- pyproject.toml entry point addition
- llm_pipeline/demo/ directory

---

## 11. Key file paths

| File | Role |
|------|------|
| `llm_pipeline/ui/app.py` | create_app() -- primary modification target |
| `llm_pipeline/ui/cli.py` | CLI entry -- no changes in task 1 |
| `llm_pipeline/pipeline.py` | PipelineConfig base class (L87-277) |
| `llm_pipeline/registry.py` | PipelineDatabaseRegistry (not pipeline_registry dict) |
| `llm_pipeline/introspection.py` | PipelineIntrospector class |
| `llm_pipeline/ui/routes/runs.py` | trigger_run() -- shows factory call signature |
| `llm_pipeline/ui/routes/pipelines.py` | Shows introspection_registry usage |
| `llm_pipeline/db/prompt.py` | Prompt model for seed_prompts |
| `llm_pipeline/__init__.py` | Public API exports |
| `pyproject.toml` | Build config, entry points |
| `tests/ui/conftest.py` | Test app factory pattern |
| `tests/test_introspection.py` | Mock pipeline classes |
