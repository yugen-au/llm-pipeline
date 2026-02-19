# Research: Codebase Structure & FastAPI App Factory Patterns

## 1. Existing Package Structure

```
llm_pipeline/
  __init__.py          # top-level: hybrid export strategy (26 symbols in __all__)
  pipeline.py          # PipelineConfig
  step.py              # LLMStep, LLMResultMixin, step_definition
  strategy.py          # PipelineStrategy, PipelineStrategies, StepDefinition
  context.py           # PipelineContext
  extraction.py        # PipelineExtraction
  transformation.py    # PipelineTransformation
  registry.py          # PipelineDatabaseRegistry
  state.py             # PipelineStepState, PipelineRunInstance
  types.py             # ArrayValidationConfig, ValidationContext
  llm/
    __init__.py        # re-exports LLMProvider, RateLimiter, LLMCallResult, schema utils
    provider.py        # LLMProvider (abstract)
    gemini.py          # GeminiProvider (optional google-generativeai dep)
    result.py          # LLMCallResult
    rate_limiter.py    # RateLimiter
    schema.py          # flatten_schema, format_schema_for_llm
    validation.py      # validate_structured_output, etc.
    executor.py        # LLM execution logic
  db/
    __init__.py        # init_pipeline_db, get_engine, get_session, get_default_db_path, Prompt
    prompt.py          # Prompt model
  session/
    __init__.py        # re-exports ReadOnlySession
    readonly.py        # ReadOnlySession implementation
  prompts/
    __init__.py        # re-exports PromptService, VariableResolver, sync/load helpers
    service.py         # PromptService
    loader.py          # sync_prompts, load_all_prompts, extract_variables_from_content
    variables.py       # VariableResolver
  events/
    __init__.py        # comprehensive re-exports: 51 symbols in __all__
    types.py           # PipelineEvent base + 30 concrete event dataclasses
    emitter.py         # PipelineEventEmitter, CompositeEmitter
    handlers.py        # LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler
    models.py          # PipelineEventRecord (SQLModel)
```

## 2. Import & Export Patterns

### Top-level __init__.py (hybrid strategy)
- Direct imports of all core types (no lazy loading)
- `__all__` with 26 entries organized by category comments
- Infrastructure symbols promoted here; concrete event types stay in `events` submodule
- Docstring documents both import paths: `from llm_pipeline import X` and `from llm_pipeline.events import Y`

### Subpackage __init__.py pattern
- Each subpackage __init__.py does explicit `from .module import Symbol` imports
- Each has an `__all__` list
- Module docstring with usage examples

### Optional dependency pattern (gemini)
- `gemini.py` does **lazy import** inside `_ensure_configured()` method
- ImportError raises helpful message: `"google-generativeai not installed. Install with: pip install llm-pipeline[gemini]"`
- `gemini.py` is NOT imported from `llm/__init__.py` (stays opt-in)
- pyproject.toml has `[project.optional-dependencies] gemini = ["google-generativeai>=0.3.0"]`

## 3. pyproject.toml Configuration

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "llm-pipeline"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.0",
    "sqlmodel>=0.0.14",
    "sqlalchemy>=2.0",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
gemini = ["google-generativeai>=0.3.0"]
dev = ["pytest>=7.0", "pytest-cov>=4.0", "google-generativeai>=0.3.0"]
```

Key observations:
- No FastAPI, uvicorn, or websockets in any dependency group
- Hatchling build system (auto-discovers packages)
- No `[project.scripts]` entry points defined yet

## 4. FastAPI App Factory Pattern

### create_app() function (from Context7 + best practices)
- Function that constructs and returns a `FastAPI` instance
- Allows parameterization (db_path, cors_origins, debug mode, etc.)
- Routers included via `app.include_router(router, prefix=..., tags=...)`
- Middleware added via `app.add_middleware()`
- Supports testing by creating isolated app instances

### APIRouter modular organization
- Each route module creates `router = APIRouter()` at module level
- Router can have prefix, tags, dependencies, responses set at creation or at include time
- `app.include_router(router, prefix="/api")` merges routes into main app
- Negligible performance impact (microsecond startup cost)

### Router best practices
- Set `prefix` and `tags` at router level for self-contained modules
- Or set at `include_router()` call for centralized control
- Task spec uses centralized prefix (`prefix='/api'`) at include time

### CORSMiddleware
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      # dev mode: permissive
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
- For dev: `allow_origins=["*"]` is standard
- Note: `allow_credentials=True` + `allow_origins=["*"]` is technically invalid per CORS spec. For dev mode, either use `allow_credentials=False` with wildcard, or skip credentials. Task spec implies simple wildcard approach.

## 5. Import Guard Strategy for ui/

Task spec prescribes **module-level** guard in `ui/__init__.py`:
```python
try:
    from fastapi import FastAPI
except ImportError:
    raise ImportError(
        'FastAPI not installed. Install with: pip install llm-pipeline[ui]'
    )
```

This differs from gemini's lazy pattern because:
- Gemini: you can import `llm_pipeline.llm` without google-generativeai (just can't use GeminiProvider)
- UI: the entire ui/ package requires FastAPI - no point importing it without FastAPI installed
- Module-level guard is the correct choice here

Critical: `llm_pipeline/__init__.py` must NOT import from `llm_pipeline.ui` to keep FastAPI optional.

## 6. Dependency Requirements for [ui] Extra

```toml
[project.optional-dependencies]
ui = [
    "fastapi>=0.100",
    "uvicorn[standard]>=0.20",
]
```

- `fastapi>=0.100` for Annotated type support and modern features
- `uvicorn[standard]` includes uvloop, httptools, websockets
- websockets support comes via uvicorn[standard]

## 7. Files to Create (Task 19 Scope)

```
llm_pipeline/ui/
  __init__.py           # import guard + package docstring
  app.py                # create_app() factory function
  routes/
    __init__.py         # empty or convenience re-exports
    runs.py             # router = APIRouter(tags=["runs"])
    steps.py            # router = APIRouter(tags=["steps"])
    events.py           # router = APIRouter(tags=["events"])
    prompts.py          # router = APIRouter(tags=["prompts"])
    pipelines.py        # router = APIRouter(tags=["pipelines"])
    websocket.py        # router = APIRouter(tags=["websocket"])
```

Plus modify:
- `pyproject.toml` - add `[project.optional-dependencies] ui = [...]`

## 8. Upstream Task 18 Status

Completed with no deviations. Event system fully exported. Task 19 can import handlers from top-level (`from llm_pipeline import LoggingEventHandler`) and concrete events from submodule (`from llm_pipeline.events import PipelineStarted`).

## 9. Downstream Task Boundaries (OUT OF SCOPE)

| Task | Title | Status | What it adds |
|------|-------|--------|-------------|
| 20 | Runs API Endpoints | pending | Actual GET/POST /runs endpoints in runs.py |
| 22 | Prompts API Endpoint | pending | Actual GET /prompts endpoints in prompts.py |
| 23 | Pipeline Introspection Service | pending | ui/introspection.py with PipelineIntrospector |
| 27 | CLI Entry Point | pending | ui/cli.py with argparse + uvicorn.run |

## 10. Design Decisions (Confirmed)

1. **Import guard**: module-level in `ui/__init__.py` (not lazy) - correct for package-wide dep
2. **CORS**: `allow_origins=["*"]` for dev mode per task spec
3. **Router prefix**: centralized `prefix="/api"` at `include_router()` in app.py
4. **No top-level export**: `llm_pipeline/__init__.py` stays untouched (optional dep pattern)
5. **Route stubs**: each file gets `router = APIRouter(tags=[...])` with no endpoints (downstream)
6. **db_path parameter**: accepted by create_app() but minimal wiring (downstream tasks handle queries)
