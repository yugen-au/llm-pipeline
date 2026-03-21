# Step 1: CLI & Module Loading Research

## 1. Current CLI Structure (`llm_pipeline/ui/cli.py`)

### Entry Point
- `pyproject.toml`: `[project.scripts] llm-pipeline = "llm_pipeline.ui.cli:main"`
- `main()` uses `argparse.ArgumentParser(prog="llm-pipeline")` with `add_subparsers(dest="command")`
- Only subcommand: `"ui"` with flags: `--dev`, `--port` (int, default 8642), `--db` (str, default None)

### Dispatch Flow
```
main() -> parser.parse_args() -> _run_ui(args)
  _run_ui:
    if args.dev -> _run_dev_mode(args)
    else        -> create_app(db_path=args.db) -> _run_prod_mode(app, port)
```

### Prod Mode Path
- Imports `create_app` from `llm_pipeline.ui.app`
- Calls `create_app(db_path=args.db)` directly -- args are available in scope
- Passes `app` object to `_run_prod_mode(app, port)` which calls `uvicorn.run(app, ...)`

### Dev Mode Path
- Sets env vars as bridge: `os.environ["LLM_PIPELINE_DB"] = args.db`
- Calls `uvicorn.run("llm_pipeline.ui.cli:_create_dev_app", factory=True, reload=True, ...)`
- `_create_dev_app()` reads env vars and reconstructs create_app kwargs:
  ```python
  db_path = os.environ.get("LLM_PIPELINE_DB")
  database_url = os.environ.get("LLM_PIPELINE_DATABASE_URL")
  return create_app(db_path=db_path, database_url=database_url)
  ```
- Key pattern: **args -> env vars -> factory reads env vars -> create_app()** (because uvicorn reload reimports the factory, args aren't in scope)

### Import Guard
- `_run_ui` wraps everything in `try/except ImportError` for UI deps (`fastapi`, `uvicorn`, `starlette`, `multipart`, `python_multipart`)
- Unknown ImportErrors are re-raised; known ones print install hint and `sys.exit(1)`

## 2. create_app() Signature (Current)

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

Key behaviors:
- `default_model`: param > `LLM_PIPELINE_MODEL` env var > None (logs warning if None)
- `auto_discover=True`: scans `llm_pipeline.pipelines` entry-point group via `importlib.metadata`
- Merge order: `{**discovered, **(explicit or {})}` -- explicit overrides win
- Stores on `app.state`: `pipeline_registry`, `introspection_registry`, `default_model`, `engine`

## 3. --model Flag Design

### Prod Mode
- Add `--model` to `ui_parser`: `ui_parser.add_argument("--model", type=str, default=None, help="...")`
- Pass to create_app: `create_app(db_path=args.db, default_model=args.model)`
- create_app's resolution chain handles the rest: `args.model > LLM_PIPELINE_MODEL env > None`

### Dev Mode
- Set env var: `os.environ["LLM_PIPELINE_MODEL"] = args.model` (only if args.model is not None)
- No change needed to `_create_dev_app()` -- create_app already reads `LLM_PIPELINE_MODEL` as fallback
- Pattern matches existing `--db` -> `LLM_PIPELINE_DB` pattern exactly

### Fallback Chain
1. `--model` CLI flag (explicit)
2. `LLM_PIPELINE_MODEL` env var (dotenv or shell)
3. None (startup warning logged, HTTP 422 on execution attempt)

## 4. --pipelines Flag Design

### Flag Syntax
```bash
# Single module
llm-pipeline ui --pipelines myapp.pipelines

# Multiple modules
llm-pipeline ui --pipelines myapp.pipelines --pipelines otherapp.pipelines
```
- `ui_parser.add_argument("--pipelines", action="append", type=str, default=None, help="...")`
- Results in `args.pipelines: list[str] | None`

### Module Import Pattern
```python
import importlib
module = importlib.import_module("myapp.pipelines")  # dotted path
registry = getattr(module, "PIPELINE_REGISTRY", None)  # dict[str, Type[PipelineConfig]]
```

### PIPELINE_REGISTRY Contract
Per PRD: `PIPELINE_REGISTRY: dict[str, Type[PipelineConfig]]`
- Keys: pipeline names (str)
- Values: PipelineConfig subclass types (not instances)
- Same validation as entry point discovery: `inspect.isclass(cls) and issubclass(cls, PipelineConfig)`

### Helper Function (new)
```python
def _load_pipeline_modules(
    module_paths: list[str], default_model: str | None
) -> tuple[dict[str, Callable], dict[str, Type[PipelineConfig]]]:
```
- Iterates module_paths, imports each, extracts PIPELINE_REGISTRY
- For each class: validates PipelineConfig subclass, builds factory via `_make_pipeline_factory(cls, model)`
- Returns (pipeline_reg, introspection_reg) -- same shape as `_discover_pipelines()`
- Error handling: log warnings for bad imports, missing PIPELINE_REGISTRY, invalid classes -- don't crash

### Prod Mode
- Import modules in CLI, build registries, pass as `pipeline_registry`/`introspection_registry` to create_app
- These become the "explicit overrides" that merge on top of auto-discovered entries
- OR: pass module paths to create_app, let it do the import (cleaner, but needs new param)

**Recommended approach:** Add helper to `app.py` (near `_discover_pipelines`), call from both CLI paths. In prod mode, call helper directly and pass results to create_app's existing `pipeline_registry`/`introspection_registry` params. Keeps create_app's interface stable.

### Dev Mode
- Serialize module paths to env var: `os.environ["LLM_PIPELINE_PIPELINES"] = ",".join(args.pipelines)`
- `_create_dev_app()` reads: `pipelines_str = os.environ.get("LLM_PIPELINE_PIPELINES", "")`
- Splits on comma, calls helper, passes registries to create_app
- Matches established pattern: `--db` -> `LLM_PIPELINE_DB`, `--model` -> `LLM_PIPELINE_MODEL`

### New Env Var: LLM_PIPELINE_PIPELINES
- Comma-separated dotted module paths
- Example: `LLM_PIPELINE_PIPELINES=myapp.pipelines,otherapp.pipelines`
- Only set by CLI's --pipelines flag; not read by create_app directly (processed in _create_dev_app)

## 5. Discovery Order (PRD-specified)

1. Scan entry points (auto-discovery via `importlib.metadata`) -- create_app's `_discover_pipelines()`
2. Apply CLI overrides (manual via `--pipelines` modules) -- merge on top
3. Log discovered pipelines at startup

create_app's existing merge handles this: `{**discovered, **(explicit or {})}`. The --pipelines registries become the "explicit" param.

## 6. _create_dev_app Updates Needed

Current:
```python
def _create_dev_app() -> object:
    db_path = os.environ.get("LLM_PIPELINE_DB")
    database_url = os.environ.get("LLM_PIPELINE_DATABASE_URL")
    return create_app(db_path=db_path, database_url=database_url)
```

After:
```python
def _create_dev_app() -> object:
    db_path = os.environ.get("LLM_PIPELINE_DB")
    database_url = os.environ.get("LLM_PIPELINE_DATABASE_URL")
    # --model is handled by create_app's env var fallback (LLM_PIPELINE_MODEL)
    # --pipelines needs explicit handling:
    pipelines_str = os.environ.get("LLM_PIPELINE_PIPELINES", "")
    module_paths = [p.strip() for p in pipelines_str.split(",") if p.strip()]
    if module_paths:
        pipeline_reg, introspection_reg = _load_pipeline_modules(module_paths, ...)
        return create_app(db_path=..., pipeline_registry=pipeline_reg, introspection_registry=introspection_reg)
    return create_app(db_path=db_path, database_url=database_url)
```

Note: `default_model` for the helper needs the resolved model. Since create_app resolves it internally, the helper should get it from `os.environ.get("LLM_PIPELINE_MODEL")` in dev mode. This is a minor ordering concern -- the helper needs the model before create_app resolves it. In dev mode, if --model was passed, it's already in the env var. If not, the env var may still be set from `.env` (dotenv loaded at main() entry).

## 7. Existing importlib Usage in Codebase

- `llm_pipeline/ui/app.py`: `importlib.metadata.entry_points(group="llm_pipeline.pipelines")` -- for auto-discovery
- `llm_pipeline/ui/routes/creator.py`: `importlib.metadata.entry_points(...)` -- similar pattern
- `llm_pipeline/creator/sandbox.py`: uses importlib
- No existing use of `importlib.import_module()` in the codebase -- this will be new

## 8. Existing Env Var Conventions

| Env Var | Used By | Purpose |
|---------|---------|---------|
| `LLM_PIPELINE_DB` | cli.py, db/__init__.py | SQLite path |
| `LLM_PIPELINE_DATABASE_URL` | cli.py, app.py | Full SQLAlchemy URL |
| `LLM_PIPELINE_MODEL` | app.py, runs.py, creator.py | Default LLM model |
| `LLM_PIPELINE_STEPS_DIR` | creator.py | Steps output directory |

New: `LLM_PIPELINE_PIPELINES` -- comma-separated module paths (dev mode bridge)

## 9. Test Patterns (from test_cli.py)

- Heavy use of `unittest.mock.patch` for deferred imports
- Patch targets documented at file top
- `_path_exists_side_effect` helper for targeted Path.exists mocking
- Test classes per feature area: `TestProdModeNoStaticFiles`, `TestDevModeNoFrontend`, etc.
- `_run_prod()` / `_run_headless_dev()` helper methods within test classes
- Args verified via `mock_ca.assert_called_once_with(db_path=...)` pattern
- Existing tests verify: `--db` passes through, `--port` passes through, env vars set in dev mode

New tests needed:
- `--model` flag passes `default_model` to create_app in prod mode
- `--model` flag sets `LLM_PIPELINE_MODEL` env var in dev mode
- `--pipelines` flag triggers module import and passes registries to create_app
- `--pipelines` flag sets `LLM_PIPELINE_PIPELINES` env var in dev mode
- Bad module path logs warning, doesn't crash
- Missing PIPELINE_REGISTRY in module logs warning
- Invalid class in PIPELINE_REGISTRY logs warning

## 10. Security Considerations

- `importlib.import_module()` executes module-level code -- only import trusted modules
- CLI users control their own module paths -- acceptable trust model
- No user-provided input from HTTP requests reaches importlib -- only CLI args and env vars
- Validate PipelineConfig subclass before registering (prevents arbitrary class injection into pipeline execution)

## 11. Upstream Task 1 Deviations

Task 1 (auto-discovery) completed cleanly. Key outputs relevant to task 2:
- `_make_pipeline_factory(cls, model)` helper exists in app.py -- reusable for --pipelines
- `_discover_pipelines(engine, default_model)` pattern established -- new helper should match shape
- Merge logic: `{**discovered, **(explicit or {})}` -- --pipelines feeds the explicit side
- HTTP 422 guard in trigger_run already references `--model` flag in error message
- Factory closure accepts `**kwargs` (absorbs extra kwargs safely)

No deviations that affect task 2 design.
