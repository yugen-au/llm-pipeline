# PLANNING

## Summary

Create the `llm_pipeline/ui/` package: app factory (`create_app()`), dependency injection (`deps.py`), import guard, and bare-stub route modules. This is the foundational backend structure that tasks 20-27 build upon. No endpoint logic is implemented here - only router declarations and infrastructure wiring.

## Plugin & Agents

**Plugin:** python-development, backend-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **pyproject.toml update**: Add `ui` optional dependency group with fastapi and uvicorn
2. **Package scaffold**: Create all `ui/` files - import guard, app factory, deps, and route stubs

## Architecture Decisions

### Import Guard Strategy
**Choice:** Module-level try/except in `ui/__init__.py` that raises `ImportError` with helpful message if FastAPI not installed.
**Rationale:** Entire `ui/` package depends on FastAPI; module-level guard is correct for package-wide optional dep (vs gemini's lazy method-level guard which is per-call). Consistent with codebase's helpful error message pattern.
**Alternatives:** Lazy imports in each file (too scattered), no guard (bad UX for missing dep).

### Router Prefix Pattern
**Choice:** Each router defines its own prefix (e.g. `prefix="/runs"`); `app.py` adds `/api` at `include_router()` call. WebSocket router has no prefix and is NOT mounted under `/api`.
**Rationale:** CEO-confirmed. Allows route modules to be self-documenting and independently testable. Per-router prefixes visible at definition site.
**Alternatives:** Centralized prefixes in app.py only (rejected by CEO).

### DB Engine Wiring
**Choice:** `create_app(db_path=None)` creates a SQLAlchemy engine from `db_path` (or uses env var default), calls `init_pipeline_db(engine)`, stores result on `app.state.engine`. `deps.py` reads `request.app.state.engine`.
**Rationale:** Reuses existing `init_pipeline_db()` from `llm_pipeline/db/__init__.py` which already handles engine creation and table creation. Storing on `app.state` is the FastAPI-idiomatic pattern for app-level shared resources. Enables test isolation (each test gets its own app instance with its own engine).
**Alternatives:** Module-level singleton engine in `deps.py` (breaks test isolation), creating engine independently in `ui/` (duplicates db/ logic).

### ReadOnlySession Closing
**Choice:** `get_db()` generator creates `Session(engine)`, wraps in `ReadOnlySession`, yields the wrapper, then closes the underlying `Session` directly in `finally`.
**Rationale:** `ReadOnlySession` has no `close()` method - must close `._session` directly. All route handlers receive `ReadOnlySession` preventing accidental writes via API layer.
**Alternatives:** Using raw Session (allows writes, inconsistent with codebase pattern).

### CORS Configuration
**Choice:** `allow_origins=["*"]`, `allow_credentials=False`, `allow_methods=["*"]`, `allow_headers=["*"]`. `create_app()` accepts `cors_origins` param for future override.
**Rationale:** CEO-confirmed. Dev-friendly defaults. `allow_credentials=False` required by CORS spec when using wildcard origins. No auth needed yet.
**Alternatives:** Restrictive CORS (blocks dev workflow), allow_credentials=True with wildcard (spec violation).

### WebSocket Stub
**Choice:** `router = APIRouter(tags=["websocket"])` only - no prefix, no endpoint, no WebSocket import.
**Rationale:** CEO-confirmed bare minimum. Implementation approach (DB polling vs event bridge) deferred to downstream task. Stub exists only to establish the module and router name.
**Alternatives:** Placeholder endpoint (unnecessary code churn when real impl lands).

## Implementation Steps

### Step 1: Add ui optional dependency to pyproject.toml
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** A

1. In `pyproject.toml` under `[project.optional-dependencies]`, add: `ui = ["fastapi>=0.100", "uvicorn[standard]>=0.20"]`
2. Keep existing `gemini` and `dev` groups unchanged

### Step 2: Create ui package import guard
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** B

1. Create `llm_pipeline/ui/__init__.py` with module-level try/except block
2. Attempt `import fastapi` in try block; on `ImportError`, raise new `ImportError` with message: `"llm_pipeline.ui requires FastAPI. Install with: pip install llm-pipeline[ui]"`
3. Do NOT import any other symbols or define `__all__` at this stage (route modules will add their own exports in downstream tasks)

### Step 3: Create app factory
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** B

1. Create `llm_pipeline/ui/app.py`
2. Import: `FastAPI`, `CORSMiddleware` from `fastapi.middleware.cors`, `Optional` from `typing`, `create_engine` from `sqlalchemy`, `init_pipeline_db` from `llm_pipeline.db`
3. Define `create_app(db_path: Optional[str] = None, cors_origins: Optional[list] = None) -> FastAPI`
4. Inside `create_app()`:
   - Instantiate `app = FastAPI(title="llm-pipeline UI")`
   - Resolve origins: `origins = cors_origins or ["*"]`
   - Add `CORSMiddleware` with `allow_origins=origins`, `allow_credentials=False`, `allow_methods=["*"]`, `allow_headers=["*"]`
   - Create engine: if `db_path` provided, `engine = create_engine(f"sqlite:///{db_path}")`, else call `init_pipeline_db()` to get default engine, then call `init_pipeline_db(engine)` to ensure tables exist; store result on `app.state.engine`
   - Import all 6 routers from `llm_pipeline.ui.routes`
   - Mount runs, steps, events, prompts, pipelines routers with `app.include_router(router, prefix="/api")`
   - Mount websocket router with `app.include_router(router)` (no `/api` prefix)
   - Return `app`

### Step 4: Create dependency injection module
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** B

1. Create `llm_pipeline/ui/deps.py`
2. Imports: `Annotated`, `Generator` from `typing`, `Request` from `fastapi`, `Depends` from `fastapi`, `Session` from `sqlmodel`, `ReadOnlySession` from `llm_pipeline.session.readonly`
3. Define `get_db(request: Request) -> Generator[ReadOnlySession, None, None]`:
   - Get engine from `request.app.state.engine`
   - Create `session = Session(engine)`
   - Wrap: `ro_session = ReadOnlySession(session)`
   - `yield ro_session`
   - In `finally`: call `session.close()` (not `ro_session.close()` - no such method)
4. Define type alias: `DBSession = Annotated[ReadOnlySession, Depends(get_db)]`
5. Export both in `__all__`: `["get_db", "DBSession"]`

### Step 5: Create route stub modules
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** B

1. Create `llm_pipeline/ui/routes/__init__.py` (empty file)
2. Create `llm_pipeline/ui/routes/runs.py`:
   - `from fastapi import APIRouter`
   - `router = APIRouter(prefix="/runs", tags=["runs"])`
3. Create `llm_pipeline/ui/routes/steps.py`:
   - `from fastapi import APIRouter`
   - `router = APIRouter(prefix="/runs/{run_id}/steps", tags=["steps"])`
4. Create `llm_pipeline/ui/routes/events.py`:
   - `from fastapi import APIRouter`
   - `router = APIRouter(prefix="/events", tags=["events"])`
5. Create `llm_pipeline/ui/routes/prompts.py`:
   - `from fastapi import APIRouter`
   - `router = APIRouter(prefix="/prompts", tags=["prompts"])`
6. Create `llm_pipeline/ui/routes/pipelines.py`:
   - `from fastapi import APIRouter`
   - `router = APIRouter(prefix="/pipelines", tags=["pipelines"])`
7. Create `llm_pipeline/ui/routes/websocket.py`:
   - `from fastapi import APIRouter`
   - `router = APIRouter(tags=["websocket"])` (no prefix)

Note: Steps 2-5 are in the same group B but operate on non-overlapping files - they can all be executed by the same agent sequentially in one pass.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `ReadOnlySession` has no `close()` - closing wrong object leaks DB connections | High | `deps.py` explicitly closes `session` (underlying), not `ro_session`. Document in code comment. |
| `init_pipeline_db()` with `db_path` param: double-call risk (create engine then pass to init) | Medium | In `create_app()`: if `db_path` given, `engine = create_engine(url)` then `app.state.engine = init_pipeline_db(engine)`. If not given, `app.state.engine = init_pipeline_db()` (no double-call). |
| WebSocket router mounted without prefix - may collide with future routes | Low | Router has no prefix by design (CEO decision). WS endpoints added in downstream task will define their own paths. |
| FastAPI not in dev deps - tests importing `ui` will fail without it | Medium | Add `fastapi` and `uvicorn[standard]` to `dev` optional-dependencies in pyproject.toml as well, or install `llm-pipeline[ui]` in test environment. The import guard gives a clear error. |
| Route stubs with path params in prefix (e.g. `/runs/{run_id}/steps`) - FastAPI behavior at include_router | Low | Path params in router prefix is valid FastAPI pattern. No endpoints added yet so no ambiguity. |

## Success Criteria

- [ ] `from llm_pipeline.ui import create_app` raises `ImportError` when fastapi not installed, with install hint
- [ ] `from llm_pipeline.ui.app import create_app` returns `FastAPI` instance with CORS middleware attached
- [ ] `app.state.engine` is set after `create_app()` call
- [ ] All 6 route modules importable: `from llm_pipeline.ui.routes.runs import router` etc.
- [ ] `from llm_pipeline.ui.deps import get_db, DBSession` succeeds
- [ ] `create_app()` with explicit `db_path` uses that path (not env var default)
- [ ] `create_app()` without args uses `init_pipeline_db()` default (env var or `.llm_pipeline/pipeline.db`)
- [ ] pyproject.toml has `[project.optional-dependencies] ui = [...]` section

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All files are new (no existing code to break). No logic in route stubs. App factory pattern is well-understood. DB wiring reuses existing tested `init_pipeline_db()`. All architectural decisions pre-validated by CEO.
**Suggested Exclusions:** testing, review
