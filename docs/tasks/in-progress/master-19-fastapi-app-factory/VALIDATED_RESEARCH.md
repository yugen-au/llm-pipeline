# Research Summary

## Executive Summary

Two research agents investigated (1) codebase structure + FastAPI patterns and (2) API architecture + route design for Task 19: FastAPI app factory. All major findings validated against actual codebase. Five architectural ambiguities identified and resolved via CEO Q&A. Research is ready for planning.

## Domain Findings

### Package Structure & Import Patterns
**Source:** step-1-codebase-fastapi-patterns.md

- Validated: 7 subpackages (llm/, db/, session/, prompts/, events/, plus top-level modules)
- Top-level `__init__.py`: 26 symbols in `__all__`, direct imports (no lazy loading)
- Each subpackage has explicit `from .module import Symbol` + `__all__` pattern
- No `ui/` imports in top-level `__init__.py` -- must stay this way (optional dep)
- Optional dep pattern (gemini): lazy import inside methods, not in `__init__.py`, helpful error message

### Database Layer
**Source:** step-1-codebase-fastapi-patterns.md, step-2-api-architecture-routes.md

- `db/__init__.py`: module-level `_engine` singleton, `init_pipeline_db()`, `get_engine()`, `get_session()`
- Default DB path: `LLM_PIPELINE_DB` env var or `.llm_pipeline/pipeline.db`
- 4 tables: `pipeline_step_states`, `pipeline_run_instances`, `pipeline_events`, `prompts`
- No dedicated runs table -- "run" is implicit concept via `run_id` across 3 tables
- `ReadOnlySession`: wraps Session, allows query/exec/get/execute/scalar/scalars, blocks writes
- ReadOnlySession has no `close()` method -- deps.py must close underlying Session directly

### FastAPI App Factory Pattern
**Source:** step-1-codebase-fastapi-patterns.md

- `create_app()` returns configured FastAPI instance
- Parameterizable: db_path, cors_origins, debug mode
- Routers via `app.include_router()`, middleware via `app.add_middleware()`
- Testable: isolated app instances per test

### Route Organization
**Source:** step-2-api-architecture-routes.md

- 6 route modules: runs, steps, events, prompts, pipelines, websocket
- Per-router prefix pattern (CEO confirmed): each router defines own prefix (e.g., `prefix="/runs"`)
- `app.include_router(router, prefix="/api")` adds /api prefix at registration
- WebSocket router excluded from /api prefix (WS at /ws/...)
- Endpoint catalog, response schemas, and pagination patterns documented for downstream tasks

### Import Guard Strategy
**Source:** step-1-codebase-fastapi-patterns.md, step-2-api-architecture-routes.md

- Module-level guard in `ui/__init__.py` (not lazy) -- correct for package-wide dep
- Differs from gemini's lazy pattern: entire ui/ package requires FastAPI
- pyproject.toml addition: `ui = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]`

### Upstream Task 18
**Source:** step-1-codebase-fastapi-patterns.md

- Status: done, no deviations
- Events system fully exported: 51 symbols in events `__all__`
- Import paths confirmed: `from llm_pipeline import LoggingEventHandler`, `from llm_pipeline.events import PipelineStarted`

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Router prefix: centralized at include_router vs per-router? | Per-router (each defines own prefix like `/runs`, app.py adds `/api` at include) | Resolves contradiction between step-1 (centralized) and step-2 (per-router). All route stubs need prefix param. |
| deps.py in Task 19 scope? | Yes, include it. No downstream task mentions it. | Task 19 file list expands: add `deps.py` with `get_db`, `get_engine`, `DBSession` type alias. |
| DB engine: reuse init_pipeline_db() vs create own? | Reuse init_pipeline_db(), store returned engine on app.state. | `create_app()` calls `init_pipeline_db(engine)` (if db_path provided, create engine first) and stores result on `app.state.engine`. Consistent with existing codebase. |
| CORS allow_credentials with wildcard origin? | False. Spec-compliant, no auth needed yet. | `allow_credentials=False` in CORSMiddleware config. |
| WebSocket stub: bare minimum or placeholder endpoint? | Bare minimum -- just `router = APIRouter(tags=["websocket"])`. | websocket.py is simplest stub: no WebSocket import, no endpoint. |

## Assumptions Validated

- [x] Package structure matches research descriptions (all 7 subpackages confirmed)
- [x] Top-level __init__.py has 26+ exports with __all__ list
- [x] pyproject.toml has no FastAPI/uvicorn deps, uses hatchling build
- [x] Optional dep pattern (gemini) uses lazy import inside methods
- [x] db/__init__.py has init_pipeline_db, get_engine, get_session, module-level _engine
- [x] ReadOnlySession exposes query/exec/get/execute/scalar/scalars and blocks writes
- [x] PipelineStepState and PipelineRunInstance models match documented schemas
- [x] PipelineEventRecord exists in events/models.py with documented columns
- [x] Prompt model exists in db/prompt.py with documented columns and constraints
- [x] No dedicated pipeline_runs table -- run is implicit via run_id
- [x] Task 18 (upstream) completed with no deviations
- [x] Downstream tasks (20, 22, 23, 27) all depend on Task 19, boundaries are clean

## Open Items

- WebSocket implementation approach (DB polling vs event bridge) deferred to downstream task. Research documents both options.
- Response schemas (RunSummary, StepDetail, EventResponse, etc.) belong in downstream tasks (20, 22), not Task 19.
- Test file structure (tests/test_ui/ vs tests/test_ui_app.py) to be decided in planning phase.
- Production CORS origins parameterization deferred -- `allow_origins=["*"]` for now with `create_app(cors_origins=None)` parameter for future override.

## Recommendations for Planning

1. **File list for Task 19**: `ui/__init__.py`, `ui/app.py`, `ui/deps.py`, `ui/routes/__init__.py`, `ui/routes/{runs,steps,events,prompts,pipelines,websocket}.py`, plus pyproject.toml edit.
2. **deps.py pattern**: `get_db()` yields `ReadOnlySession(Session(engine))`, closes underlying Session in finally. `DBSession = Annotated[ReadOnlySession, Depends(get_db)]` type alias.
3. **create_app() db wiring**: Accept `db_path` param, create engine if provided, call `init_pipeline_db(engine)`, store result on `app.state.engine`.
4. **Route stubs**: Each file gets `router = APIRouter(prefix="/xxx", tags=["xxx"])` except websocket which gets `router = APIRouter(tags=["websocket"])` only.
5. **Import guard**: Module-level try/except in `ui/__init__.py` checking for FastAPI import.
6. **CORS**: `allow_origins=["*"]`, `allow_credentials=False`, `allow_methods=["*"]`, `allow_headers=["*"]`.
7. **steps.py prefix**: Use `prefix="/runs/{run_id}/steps"` (nested resource pattern from step-2 research).
8. **ReadOnlySession close caveat**: Document in deps.py that `session.close()` closes the underlying Session, not the ReadOnlySession wrapper.
