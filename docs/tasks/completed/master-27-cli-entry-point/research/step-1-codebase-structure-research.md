# Step 1: Codebase Structure Research for CLI Entry Point (Task 27)

## 1. Project Structure

### Package Layout
```
llm_pipeline/
  __init__.py          # top-level exports (PipelineConfig, LLMStep, etc.)
  pipeline.py, step.py, strategy.py, context.py, extraction.py, transformation.py
  registry.py, state.py, introspection.py, types.py
  db/
    __init__.py        # init_pipeline_db(), get_engine(), get_default_db_path()
    prompt.py
  events/
    __init__.py, emitter.py, handlers.py, models.py, types.py
  llm/
    __init__.py, provider.py, gemini.py, result.py, executor.py, schema.py, validation.py, rate_limiter.py
  prompts/
    __init__.py, variables.py, service.py, loader.py
  session/
    __init__.py, readonly.py
  ui/                  # <-- target package for cli.py
    __init__.py        # import guard for FastAPI, exports create_app
    app.py             # create_app factory
    deps.py            # DB dependency injection (get_db, DBSession)
    routes/
      __init__.py, runs.py, steps.py, events.py, prompts.py, pipelines.py, websocket.py
```

### Key Observations
- No `cli.py` exists anywhere in the codebase
- No argparse, click, or typer usage anywhere
- No subprocess/Popen usage in the codebase
- No `[project.scripts]` or `[tool.hatch.build]` in pyproject.toml
- No frontend/dist directory exists (no Vite project yet)

## 2. pyproject.toml Current State

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "llm-pipeline"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pydantic>=2.0", "sqlmodel>=0.0.14", "sqlalchemy>=2.0", "pyyaml>=6.0"]

[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
ui = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]
dev = ["pytest>=7.0", "pytest-cov>=4.0", "google-generativeai>=0.3.0", "fastapi>=0.100", "uvicorn[standard]>=0.20", "httpx>=0.24"]
```

**No `[project.scripts]` section.** Task 28 (downstream) handles adding this.

## 3. create_app Factory

**File:** `llm_pipeline/ui/app.py`

```python
def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
    introspection_registry: Optional[Dict[str, Type[PipelineConfig]]] = None,
) -> FastAPI:
```

### Parameters
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `db_path` | `Optional[str]` | `None` | SQLite path. None = `LLM_PIPELINE_DB` env or `.llm_pipeline/pipeline.db` |
| `cors_origins` | `Optional[list]` | `None` | CORS origins. None = `["*"]` |
| `pipeline_registry` | `Optional[dict]` | `None` | Pipeline name -> factory callable mapping |
| `introspection_registry` | `Optional[Dict[str, Type[PipelineConfig]]]` | `None` | Pipeline name -> PipelineConfig type mapping |

### What it does
1. Creates FastAPI app with CORS middleware
2. Initializes DB engine (via `init_pipeline_db()` or custom `db_path`)
3. Stores engine + registries on `app.state`
4. Mounts 6 route modules: runs, steps, events, prompts, pipelines, websocket

### CLI-relevant params
- `db_path` maps directly to `--db` CLI flag
- `cors_origins` defaults to `["*"]` which is fine for both dev and prod
- `pipeline_registry` and `introspection_registry` are not CLI-configurable (programmatic use only)

## 4. UI Package Import Guard

**File:** `llm_pipeline/ui/__init__.py`

```python
try:
    import fastapi
except ImportError:
    raise ImportError(
        "llm_pipeline.ui requires FastAPI. "
        "Install with: pip install llm-pipeline[ui]"
    )
from llm_pipeline.ui.app import create_app
__all__ = ["create_app"]
```

The CLI module should **not** import from `llm_pipeline.ui` at module level -- it should defer imports to after argument parsing so `--help` works even without FastAPI installed.

## 5. Database Initialization

**File:** `llm_pipeline/db/__init__.py`

- `get_default_db_path()` -> `Path`: uses `LLM_PIPELINE_DB` env var or `CWD/.llm_pipeline/pipeline.db`
- `init_pipeline_db(engine=None)` -> `Engine`: creates tables, sets WAL mode for SQLite
- When `db_path` is passed to `create_app`, it creates engine via `create_engine(f"sqlite:///{db_path}")`

## 6. Upstream Task 19 (done) - Deviations from Spec

Task 19 spec called for basic route stubs. Actual implementation went further:
- Full CRUD routes with pagination, filtering, sorting
- WebSocket real-time streaming with ConnectionManager
- Dependency injection module (deps.py)
- ReadOnlySession wrapper for safety

**No deviations that affect CLI implementation.** create_app signature matches what task 27 expects.

## 7. Downstream Task 28 (pending) - Scope Boundary

Task 28 will:
- Update pyproject.toml with `[project.scripts] llm-pipeline = "llm_pipeline.ui.cli:main"`
- Update version pins for ui optional deps
- Add `[tool.hatch.build]` config for frontend dist inclusion

**Task 27 scope: create cli.py only. Do NOT modify pyproject.toml.**

## 8. Implementation Plan for cli.py

### File: `llm_pipeline/ui/cli.py`

```python
# Deferred imports pattern - argparse at top, FastAPI/uvicorn only when needed
import argparse

def main():
    parser = argparse.ArgumentParser(description='llm-pipeline')
    parser.add_argument('command', choices=['ui'])
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--port', type=int, default=8642)
    parser.add_argument('--db', type=str, default=None)
    args = parser.parse_args()

    if args.command == 'ui':
        _run_ui(args)

def _run_ui(args):
    # Import here so --help works without FastAPI
    from llm_pipeline.ui.app import create_app
    import uvicorn

    app = create_app(db_path=args.db)

    if args.dev:
        start_dev_mode(app, args.port)
    else:
        uvicorn.run(app, host='0.0.0.0', port=args.port)

def start_dev_mode(app, port):
    # Vite on port+1, FastAPI on port
    # No frontend exists yet - guard with helpful error
    ...
```

### Design Decisions
1. **Deferred imports**: argparse at top level, FastAPI/uvicorn inside function bodies so `--help` / `--version` works without `pip install llm-pipeline[ui]`
2. **No pyproject.toml changes**: deferred to task 28
3. **start_dev_mode**: implement subprocess logic but guard if no frontend directory found
4. **Prod mode**: run uvicorn directly; static file mounting deferred (no dist/ exists yet)
5. **Default port**: 8642 per task spec
6. **No pipeline_registry/introspection_registry**: CLI creates basic app for inspection-only use
