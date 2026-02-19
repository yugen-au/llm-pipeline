# IMPLEMENTATION - STEP 2: UI PACKAGE & APP FACTORY
**Status:** completed

## Summary
Created the entire `llm_pipeline/ui/` package: import guard, app factory with CORS and DB wiring, dependency injection module, and all 6 route stub modules.

## Files
**Created:**
- `llm_pipeline/ui/__init__.py`
- `llm_pipeline/ui/app.py`
- `llm_pipeline/ui/deps.py`
- `llm_pipeline/ui/routes/__init__.py`
- `llm_pipeline/ui/routes/runs.py`
- `llm_pipeline/ui/routes/steps.py`
- `llm_pipeline/ui/routes/events.py`
- `llm_pipeline/ui/routes/prompts.py`
- `llm_pipeline/ui/routes/pipelines.py`
- `llm_pipeline/ui/routes/websocket.py`

**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/__init__.py`
Module-level import guard for FastAPI. Re-exports `create_app` from `app.py`.
```python
try:
    import fastapi
except ImportError:
    raise ImportError("llm_pipeline.ui requires FastAPI. Install with: pip install llm-pipeline[ui]")

from llm_pipeline.ui.app import create_app
```

### File: `llm_pipeline/ui/app.py`
App factory: `create_app(db_path=None, cors_origins=None) -> FastAPI`. Adds CORSMiddleware, wires DB engine via `init_pipeline_db()`, mounts all 6 routers (5 under `/api`, websocket without prefix).

### File: `llm_pipeline/ui/deps.py`
DB session DI: `get_db(request)` yields `ReadOnlySession(Session(engine))`, closes underlying `Session` in finally. Exports `DBSession = Annotated[ReadOnlySession, Depends(get_db)]`.

### File: `llm_pipeline/ui/routes/*.py`
Six stub modules, each declaring `router = APIRouter(...)`:
- `runs.py`: prefix="/runs", tags=["runs"]
- `steps.py`: prefix="/runs/{run_id}/steps", tags=["steps"]
- `events.py`: prefix="/events", tags=["events"]
- `prompts.py`: prefix="/prompts", tags=["prompts"]
- `pipelines.py`: prefix="/pipelines", tags=["pipelines"]
- `websocket.py`: tags=["websocket"] (no prefix)

## Decisions
### Router imports in app.py
**Choice:** Lazy imports inside `create_app()` body rather than module-level
**Rationale:** Avoids circular import risk since route modules may later import from deps.py which references the app. Also matches the pattern where routers should only be resolved at app creation time.

### ReadOnlySession close pattern
**Choice:** Close underlying `session` directly, not the `ReadOnlySession` wrapper
**Rationale:** `ReadOnlySession` has no `close()` method. Documented in deps.py docstring. Consistent with PLAN.md decision.

## Verification
[x] `from llm_pipeline.ui import create_app` works when FastAPI installed
[x] `from llm_pipeline.ui import create_app` raises ImportError with install hint when FastAPI missing
[x] `create_app(db_path=...)` returns FastAPI with engine on app.state
[x] `create_app()` without args uses init_pipeline_db() default
[x] All 6 route modules importable with correct prefixes
[x] `from llm_pipeline.ui.deps import get_db, DBSession` succeeds
[x] CORS middleware attached to app
[x] Custom cors_origins parameter works
[x] Existing test suite: 347 passed, 1 pre-existing failure (unrelated)
