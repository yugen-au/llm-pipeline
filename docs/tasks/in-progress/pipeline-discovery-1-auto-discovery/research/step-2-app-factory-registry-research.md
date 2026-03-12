# Step 2: App Factory & Registry Research

## 1. create_app() Current State

**File:** `llm_pipeline/ui/app.py`

### Signature
```python
def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None,
) -> FastAPI:
```

### Execution Order
1. Create FastAPI instance (line 43)
2. Add CORS middleware (lines 46-53)
3. Add GZip middleware (line 56)
4. Init DB engine via `init_pipeline_db()` -> `app.state.engine` (lines 62-66)
5. Set registries on `app.state` (lines 68-69)
6. Import and include route modules (lines 72-84)
7. Return app

### Registry Assignment
```python
app.state.pipeline_registry = pipeline_registry or {}
app.state.introspection_registry = introspection_registry or {}
```
Both default to empty dict if None. No merging logic exists.

---

## 2. Registry Types & Signatures

### pipeline_registry
- **Type:** `dict` (untyped in signature, documented as `dict[str, Callable]`)
- **Keys:** pipeline name strings
- **Values:** factory callables
- **Factory signature (from runs.py docstring):** `(run_id: str, engine: Engine, event_emitter: PipelineEventEmitter | None = None) -> pipeline`
- **Actual call site (runs.py:223):** `factory(run_id=run_id, engine=engine, event_emitter=bridge, input_data=body.input_data or {})`
- Note: `input_data` is passed as kwarg to factory AND separately to `pipeline.execute(data=None, input_data=body.input_data)` on line 224. Factory closures must accept `input_data` kwarg (or use `**kwargs`).

### introspection_registry
- **Type:** `Dict[str, Type[PipelineConfig]]`
- **Keys:** pipeline name strings
- **Values:** PipelineConfig subclass types (not instances)
- **Consumed by:** `llm_pipeline/ui/routes/pipelines.py` -- wraps each class in `PipelineIntrospector(cls).get_metadata()`

---

## 3. PipelineConfig Constructor

**File:** `llm_pipeline/pipeline.py`, line 161

```python
def __init__(
    self,
    model: str,                    # REQUIRED positional
    strategies=None,
    session=None,
    engine=None,
    variable_resolver=None,
    event_emitter=None,
    run_id=None,
    instrumentation_settings=None,
):
```

Key points:
- `model` is **required** (no default). Factory closure must supply it.
- `engine` and `event_emitter` are optional kwargs.
- `run_id` is optional kwarg.
- No `input_data` parameter -- input_data flows through `execute()`.

### __init_subclass__ Validation
PipelineConfig subclasses must:
- End with `"Pipeline"` suffix (if registry/strategies/agent_registry provided)
- Have matching `*Registry`, `*Strategies`, `*AgentRegistry` class name prefixes
- `INPUT_DATA` ClassVar must be a PipelineInputData subclass if present

---

## 4. CLI Call Sites

**File:** `llm_pipeline/ui/cli.py`

Three places call `create_app()`:

1. **_run_ui (prod mode):** `create_app(db_path=args.db)` -- line 46
2. **_run_dev_mode (vite mode):** `create_app(db_path=args.db)` -- line 82
3. **_create_dev_app (reload factory):** `create_app(db_path=db_path)` -- line 109

None pass `pipeline_registry` or `introspection_registry`. All rely on empty defaults.

### Current CLI args
- `--dev` (flag)
- `--port` (int, default 8642)
- `--db` (str, optional)

---

## 5. importlib.metadata API (Python 3.11+)

### entry_points() with group kwarg
```python
from importlib.metadata import entry_points

eps = entry_points(group="llm_pipeline.pipelines")
# Returns EntryPoints collection (tuple-like)
```

Available since Python 3.9 (group kwarg). Python 3.11+ is our target per pyproject.toml.

### EntryPoint attributes
- `ep.name` -- entry point name (e.g., "text_analyzer")
- `ep.value` -- module:attr string (e.g., "llm_pipeline.demo:TextAnalyzerPipeline")
- `ep.load()` -- imports and returns the referenced object (the class)

### Error handling
- `ep.load()` can raise `ImportError`, `AttributeError`, or any exception during module import.

---

## 6. Error Handling Patterns in Codebase

### Consistent pattern: `logging.getLogger(__name__)`
Every module uses:
```python
import logging
logger = logging.getLogger(__name__)
```

### Warning pattern (pipelines.py:108)
```python
except Exception as exc:
    logger.warning("Failed to introspect pipeline '%s': %s", name, exc)
```

### Loader warning pattern (prompts/loader.py:74)
```python
except Exception as e:
    logger.warning(f"  Warning: Failed to load {yaml_file}: {e}")
```

Both use broad `except Exception` with `logger.warning()`. This aligns with PRD requirement: "Entry point loading errors are logged as warnings, not fatal."

---

## 7. seed_prompts Pattern

### PRD Spec
- Optional classmethod on PipelineConfig subclasses: `seed_prompts(engine)`
- Called during discovery after class loading
- Idempotent (no-op if prompts exist)
- Uses `prompt_key + prompt_type` unique constraint for idempotent insert

### Detection approach
```python
if hasattr(pipeline_cls, 'seed_prompts') and callable(pipeline_cls.seed_prompts):
    pipeline_cls.seed_prompts(engine)
```

Must wrap in try/except with warning log (consistent with entry point error handling).

---

## 8. Discovery Integration Plan

### New create_app() parameter
```python
auto_discover: bool = True
```

### Insertion point
Discovery must happen AFTER engine init (needs engine for seed_prompts) and BEFORE registry assignment to app.state. Between lines 66 and 68 in current code.

### Algorithm
```
1. Initialize discovered = {} and introspected = {}
2. If auto_discover:
   a. eps = entry_points(group="llm_pipeline.pipelines")
   b. For each ep:
      - Try ep.load() -> pipeline_cls
      - Verify issubclass(pipeline_cls, PipelineConfig)
      - Register in introspected[ep.name] = pipeline_cls
      - Create factory closure capturing pipeline_cls and model
      - Register in discovered[ep.name] = factory
      - Call seed_prompts if available
      - Catch Exception, log warning, continue
3. Merge: explicit registries override discovered
   - final_pipeline_registry = {**discovered, **(pipeline_registry or {})}
   - final_introspection_registry = {**introspected, **(introspection_registry or {})}
4. Assign to app.state
```

### Factory Closure Shape
```python
def _make_factory(cls, default_model):
    def factory(*, run_id, engine, event_emitter=None, **kwargs):
        return cls(
            model=default_model,
            run_id=run_id,
            engine=engine,
            event_emitter=event_emitter,
        )
    return factory
```

Uses `**kwargs` to absorb `input_data` and future kwargs from trigger_run.

### Model Value Source
For task 1: add `default_model: str | None = None` param to create_app(). Factory closure uses this value. Falls back to `os.environ.get("LLM_PIPELINE_MODEL")` if None. Task 2 (downstream) wires CLI `--model` flag into this param.

If both are None, the factory will fail at PipelineConfig init time (model is required). This is acceptable -- user must configure a model.

---

## 9. Downstream Task Boundaries (Out of Scope)

### Task 2: CLI Flags
- Adds `--pipelines` flag (module imports with PIPELINE_REGISTRY dict)
- Adds `--model` flag
- Modifies cli.py to pass these to create_app()
- OUT OF SCOPE for task 1

### Task 3: Demo Pipeline
- Creates `llm_pipeline/demo/` package
- Implements TextAnalyzerPipeline with 3 steps
- Adds entry point in pyproject.toml
- Implements seed_prompts() classmethod
- OUT OF SCOPE for task 1

---

## 10. pyproject.toml Current State

No `[project.entry-points]` section exists yet. Task 3 will add:
```toml
[project.entry-points."llm_pipeline.pipelines"]
text_analyzer = "llm_pipeline.demo:TextAnalyzerPipeline"
```

For task 1: no pyproject.toml changes needed. Discovery code handles empty entry point groups gracefully (returns empty collection).

---

## 11. Implementation Notes

### Files to modify (task 1 only)
- `llm_pipeline/ui/app.py` -- add auto_discover param, default_model param, discovery logic, logger

### No new files needed for task 1

### Testing considerations
- Mock `importlib.metadata.entry_points` to simulate discovered/broken entry points
- Verify merge precedence (explicit > discovered)
- Verify seed_prompts called when present
- Verify warning logged on bad entry point
- Verify auto_discover=False skips scanning
