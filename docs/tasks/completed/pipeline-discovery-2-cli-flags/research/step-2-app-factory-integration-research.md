# Step 2: App Factory Integration Research

## 1. create_app() Current Signature (Post-Task-1)

**File:** `llm_pipeline/ui/app.py`

```python
def create_app(
    db_path: Optional[str] = None,
    database_url: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None,
    auto_discover: bool = True,
    default_model: Optional[str] = None,
) -> FastAPI:
```

### Execution Order (Post-Task-1)
1. Create FastAPI instance (L145)
2. Add CORS middleware (L148-155)
3. Add GZip middleware (L158)
4. Resolve DB engine via `database_url` > `LLM_PIPELINE_DATABASE_URL` env > `db_path` > default (L164-183)
5. Resolve model: `default_model` param > `LLM_PIPELINE_MODEL` env > None; warn if None (L186-192)
6. Store `app.state.default_model = resolved_model` (L192)
7. If `auto_discover`: scan entry points, merge with explicit registries (explicit wins) (L195-209)
8. Import and include route modules (L212-228)
9. Return app

---

## 2. Default Model Flow (Complete Path)

### Resolution Chain
```
default_model param -> os.environ.get("LLM_PIPELINE_MODEL") -> None
```
- Resolved in `create_app()` at L186
- Stored as `app.state.default_model` (L192)
- Passed to `_discover_pipelines(engine, resolved_model)` (L196-197)

### Into Factory Closures
- `_make_pipeline_factory(cls, model)` captures model at discovery time (L24-46)
- Factory closure passes `model=model` to `PipelineConfig.__init__()` (L39-44)
- `PipelineConfig.__init__` declares `model: str` (required, no default) (pipeline.py L211)

### Execution-Time Guard
- `trigger_run()` in `runs.py` reads `app.state.default_model` (L212)
- Returns HTTP 422 if None (L213-217): "No model configured. Set LLM_PIPELINE_MODEL env var or pass --model flag."
- Same guard exists in `creator.py` (L151-155)

### Implication for --model
CLI `--model` value must reach `create_app(default_model=...)`. The factory closures are built at discovery time with whatever model is resolved then. No hot-reload of model after startup.

---

## 3. Pipeline Registration Mechanisms

### A. Entry-Point Auto-Discovery (Task 1)
- `_discover_pipelines(engine, default_model)` scans `llm_pipeline.pipelines` group (L49-102)
- Validates each loaded class is `PipelineConfig` subclass (L67)
- Builds factory closure via `_make_pipeline_factory(cls, default_model)` (L74)
- Registers in both `pipeline_reg[ep.name]` and `introspection_reg[ep.name]` (L74-75)
- Calls `seed_prompts(engine)` if available, in isolated try/except (L85-93)
- Current entry points in `pyproject.toml`:
  ```toml
  [project.entry-points."llm_pipeline.pipelines"]
  text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
  step_creator = "llm_pipeline.creator:StepCreatorPipeline"
  ```

### B. Explicit Registry Parameters
- `pipeline_registry: Optional[dict]` -- factory callables keyed by name
- `introspection_registry: Optional[Dict[str, Type[PipelineConfig]]]` -- class types keyed by name
- Factory callable signature: `(run_id: str, engine: Engine, event_emitter=None, **kwargs) -> PipelineConfig`

### C. Merge Order
```python
app.state.pipeline_registry = {
    **discovered_pipeline,       # auto-discovery first
    **(pipeline_registry or {}), # explicit overrides
}
```
Explicit always wins on key collision.

### Implication for --pipelines
Manual modules should be loaded, PipelineConfig subclasses extracted, factory closures built, then passed as `pipeline_registry`/`introspection_registry` to `create_app()`. They will override any auto-discovered pipelines with the same name.

---

## 4. CLI Current State

**File:** `llm_pipeline/ui/cli.py`

### Argument Parser Structure
```
llm-pipeline
  ui
    --dev     (flag)
    --port    (int, default 8642)
    --db      (str, optional)
```

### Call Sites to create_app()

| Call Site | Location | Current Args |
|-----------|----------|-------------|
| `_run_ui` (prod) | L47-49 | `create_app(db_path=args.db)` |
| `_create_dev_app` (reload factory) | L140-144 | `create_app(db_path=db_path, database_url=database_url)` |

### Dev Mode Pattern
- `_run_dev_mode` sets `os.environ["LLM_PIPELINE_DB"] = args.db` (L83)
- Launches uvicorn with string reference `"llm_pipeline.ui.cli:_create_dev_app"` and `factory=True` (L127-128)
- `_create_dev_app()` reads env vars to reconstruct args (L142-144)
- argparse namespace not available in `_create_dev_app`

---

## 5. Integration Points for --model

### Prod Mode
```python
app = create_app(db_path=args.db, default_model=args.model)
```
Direct passthrough. No complexity.

### Dev Mode
Pattern matches `--db` exactly:
```python
if args.model:
    os.environ["LLM_PIPELINE_MODEL"] = args.model
```
`create_app()` already reads `LLM_PIPELINE_MODEL` as fallback (L186). No changes to `_create_dev_app` needed.

### Confidence: High -- no ambiguity, follows existing pattern.

---

## 6. Integration Points for --pipelines (Manual Module Loading)

### Prod Mode
1. Parse `--pipelines` arg (module path strings)
2. Import each module
3. Scan for PipelineConfig subclasses (or read exported dict)
4. Build factory closures and registry dicts
5. Pass to `create_app(pipeline_registry=..., introspection_registry=...)`

### Dev Mode -- Problem
`_create_dev_app()` cannot import module paths from argparse. Options:

**Option A: Env var passthrough** (consistent with --db pattern)
- Set `os.environ["LLM_PIPELINE_PIPELINES"] = "mod1,mod2"` in `_run_dev_mode`
- Read in `_create_dev_app`, perform module loading there
- Requires new env var name and parsing logic in `_create_dev_app`

**Option B: Refactor _create_dev_app to accept params via module-level state**
- Store in module global, read in `_create_dev_app`
- Won't survive uvicorn reload (module re-imported)

**Option C: Both modes call shared helper**
- Extract module loading into `_load_pipeline_modules(module_paths, model)` helper
- Both prod and dev call it; dev passes module paths via env var
- Helper returns `(pipeline_registry, introspection_registry)` tuple

**Recommendation: Option A/C combined.** Env var for dev mode passthrough + shared helper for DRY module loading. Consistent with existing --db pattern.

---

## 7. Module Loading: Design Options

### Option 1: Scan modules for PipelineConfig subclasses
- Consistent with entry-point auto-discovery pattern
- Import module, inspect members, filter by `issubclass(cls, PipelineConfig)`
- Build factory closures via `_make_pipeline_factory(cls, model)`
- Use `cls.__name__` (snake_cased) as registry key

### Option 2: Expect modules to export PIPELINE_REGISTRY dict
- Upstream task 1 research mentioned "module imports with PIPELINE_REGISTRY dict"
- Less consistent with current entry-point pattern
- More explicit control for module authors
- Registry dict values could be classes (build closures) or factory callables

### Trade-offs
| Aspect | Option 1 (scan) | Option 2 (dict export) |
|--------|-----------------|----------------------|
| Consistency | Matches entry-point pattern | Diverges |
| Module author effort | Zero (just define class) | Must export dict |
| Naming control | Auto-derived from class name | Explicit in dict keys |
| Multiple classes per module | All discovered | Author chooses |
| Error messages | "No PipelineConfig subclasses found in module" | "Module has no PIPELINE_REGISTRY" |

---

## 8. _make_pipeline_factory Reuse

The existing `_make_pipeline_factory(cls, model)` in `app.py` (L24-46) can be reused for manual modules. It returns a factory closure matching the trigger_run expected signature. No need to duplicate.

For manual module loading, the pattern is:
```python
for module_path in module_paths:
    mod = importlib.import_module(module_path)
    for name, obj in inspect.getmembers(mod, inspect.isclass):
        if issubclass(obj, PipelineConfig) and obj is not PipelineConfig:
            key = to_snake_case(name)
            pipeline_reg[key] = _make_pipeline_factory(obj, resolved_model)
            introspection_reg[key] = obj
```

---

## 9. Existing Test Patterns

### CLI Tests (`tests/ui/test_cli.py`)
- Mock `create_app` via `patch("llm_pipeline.ui.app.create_app")`
- Assert called with expected kwargs
- Example: `mock_ca.assert_called_once_with(db_path="/tmp/test.db")`
- Pattern for new flags: mock create_app, assert `default_model=` and `pipeline_registry=` kwargs

### App Factory Tests (`tests/ui/conftest.py`)
- `_make_app()` builds app manually, sets `app.state.default_model = "test-model"`
- Tests in `test_runs.py` directly call `create_app(db_path=":memory:", default_model="test-model")`

### Test Regression Risk
- Adding `--model` and `--pipelines` args to CLI changes `create_app()` call signatures
- Existing CLI tests assert `mock_ca.assert_called_once_with(db_path=None)` -- these will break if we add kwargs to the call
- Fix: update test assertions to match new call signature, or use `assert_called_once()` + inspect specific kwargs

---

## 10. Existing Naming Utilities

`_discover_pipelines` uses `ep.name` as registry key. For manual modules, we need a naming strategy. The codebase has `to_snake_case()` in `llm_pipeline/naming.py` used by `PipelineConfig.pipeline_name`. This could be used to derive registry keys from class names.

---

## 11. Upstream Task 1 Deviations

From task 1 SUMMARY.md:
- Factory closure uses `**kwargs` to absorb `input_data` -- confirmed in current code (L37)
- HTTP 422 (not 400) for missing model -- confirmed (runs.py L215)
- `seed_prompts` failure does not unregister pipeline -- confirmed (separate try/except, L84-93)
- Model resolution: param > env > None -- confirmed (L186)

No deviations affect task 2 integration.

---

## 12. Questions Requiring CEO Input

1. **--pipelines module format**: Should `--pipelines` accept modules that are scanned for PipelineConfig subclasses (consistent with entry-point discovery), or modules that export a `PIPELINE_REGISTRY` dict (as mentioned in upstream research)? Scanning is simpler for module authors; dict export gives explicit naming control.

2. **--pipelines argument syntax**: Should the flag be repeatable (`--pipelines mod1 --pipelines mod2`), use nargs+ (`--pipelines mod1 mod2`), or comma-separated (`--pipelines mod1,mod2`)? Repeatable (append action) is the most standard argparse pattern.
