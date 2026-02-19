# PLANNING

## Summary

Add a dedicated `PipelineRun` table to `state.py`, instrument `pipeline.py` to write run lifecycle records on every execution, configure SQLite WAL mode in `init_pipeline_db()`, and implement three endpoints in `llm_pipeline/ui/routes/runs.py`: `GET /runs` (paginated, filtered list), `GET /runs/{run_id}` (detail with steps), and `POST /runs` (async trigger with background execution). Update `create_app()` to accept an optional `pipeline_registry` param for POST resolution.

## Plugin & Agents

**Plugin:** backend-development
**Subagents:** backend-architect, performance-engineer, test-automator
**Skills:** none

## Phases

1. **DB Layer** - Add `PipelineRun` SQLModel table, WAL mode, index cleanup, init registration
2. **Pipeline Instrumentation** - Write `PipelineRun` records in `execute()`, add `run_id` injection to `__init__`
3. **API Layer** - Implement all three `/runs` endpoints, update `create_app()` with registry param
4. **Tests** - Endpoint tests, WAL verification, PipelineRun write integration tests

## Architecture Decisions

### PipelineRun as Dedicated Table

**Choice:** New `PipelineRun` SQLModel table (table=True) in `state.py` with columns: `id`, `run_id` (unique), `pipeline_name`, `status`, `started_at`, `completed_at`, `step_count`, `total_time_ms`.
**Rationale:** Direct indexed queries on `PipelineRun` guarantee <200ms for 10k+ runs. Alternative of aggregating `PipelineStepState` rows via GROUP BY was assessed as borderline at 10k+ and requires complex queries. CEO decision confirmed Option C.
**Alternatives:** GROUP BY aggregation on PipelineStepState (rejected: performance borderline at scale), PipelineRunInstance repurposing (rejected: semantics differ, it tracks created DB instances not run lifecycle).

### run_id Injection via Optional Parameter

**Choice:** Add `run_id: Optional[str] = None` to `PipelineConfig.__init__()` with `self.run_id = run_id or str(uuid.uuid4())`.
**Rationale:** POST /runs must pre-generate a `run_id` to return to the client before pipeline completes. Without injection, the pipeline generates its own UUID and the returned run_id is useless for subsequent GET queries. Backward compatible - existing callers unaffected.
**Alternatives:** Post-hoc run_id lookup by pipeline start time (rejected: race condition risk), separate tracking table keyed by request (rejected: unnecessary complexity).

### Pipeline Registry via app.state

**Choice:** `create_app()` accepts optional `pipeline_registry: Optional[dict] = None`; stored on `app.state.pipeline_registry`. POST /runs looks up `pipeline_name` key, calls the factory `lambda run_id, engine: SomePipeline(...)`. If registry is None or name not found, returns 404.
**Rationale:** Consuming applications have their own pipeline subclasses with full dependency graphs (provider, strategies, engine). A simple callable dict on app.state allows framework-agnostic registration without coupling the library to specific pipeline implementations. No global registry exists in the codebase.
**Alternatives:** Global registry singleton (rejected: not thread-safe, hard to test), import-based discovery (rejected: requires framework to know about consuming app classes).

### Sync Endpoint Functions

**Choice:** All three endpoints use `def` (sync), not `async def`.
**Rationale:** SQLite and SQLModel are fully synchronous. Using `async def` with sync DB calls blocks the event loop. FastAPI auto-wraps sync handlers in a thread pool executor. Consistent with `PipelineConfig.execute()` which is sync. VALIDATED_RESEARCH.md Finding 7 confirms step-2 (sync) is correct over step-3 (async).
**Alternatives:** `async def` with `asyncio.to_thread` (rejected: unnecessary overhead, adds complexity, async SQLite not used).

### WAL Mode via SQLAlchemy Event Listener

**Choice:** In `init_pipeline_db()`, attach a `"connect"` event listener that executes `PRAGMA journal_mode=WAL` for SQLite engines.
**Rationale:** WAL mode allows concurrent readers and one writer, preventing GET queries from blocking during background pipeline writes. Both engine creation sites (`db/__init__.py:54` and `ui/app.py:43`) pass through `init_pipeline_db()`, so one listener covers both. Safe for `:memory:` (pragma silently ignored).
**Alternatives:** WAL set at engine creation time (rejected: two call sites, fragile), per-request pragma (rejected: overhead per connection, not idiomatic).

## Implementation Steps

### Step 1: Add PipelineRun Model and WAL Mode to state.py and db/__init__.py
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo, /websites/sqlalchemy_en_21
**Group:** A

1. In `llm_pipeline/state.py`, add `PipelineRun` SQLModel table after `PipelineRunInstance`:
   - Fields: `id` (Optional[int], primary_key), `run_id` (str, max_length=36, unique=True), `pipeline_name` (str, max_length=100), `status` (str, max_length=20, default="running"), `started_at` (datetime, default_factory=utc_now), `completed_at` (Optional[datetime], default=None), `step_count` (Optional[int], default=None), `total_time_ms` (Optional[int], default=None)
   - `__tablename__ = "pipeline_runs"`
   - `__table_args__`: `Index("ix_pipeline_runs_name_started", "pipeline_name", "started_at")`, `Index("ix_pipeline_runs_status", "status")`
   - Import `Index` from sqlalchemy (already imported)
2. Remove redundant `index=True` from `run_id` field on `PipelineStepState` (line 44) - composite index `ix_pipeline_step_states_run` covers it
3. Remove redundant `index=True` from `run_id` field on `PipelineRunInstance` (line 122) - composite index `ix_pipeline_run_instances_run` covers it
4. Add `PipelineRun` to `__all__` in `state.py`
5. In `llm_pipeline/db/__init__.py`:
   - Import `event` from `sqlalchemy`
   - In `init_pipeline_db()`, after setting `_engine = engine`, add SQLite WAL listener: `if engine.url.drivername.startswith("sqlite"): @event.listens_for(engine, "connect") def set_sqlite_wal(dbapi_conn, conn_record): cursor = dbapi_conn.cursor(); cursor.execute("PRAGMA journal_mode=WAL"); cursor.close()`
   - Add `PipelineRun.__table__` to the `tables=[...]` list in `SQLModel.metadata.create_all()`
   - Import `PipelineRun` from `llm_pipeline.state`

### Step 2: Instrument pipeline.py execute() with PipelineRun Writes
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo
**Group:** B

1. In `llm_pipeline/pipeline.py`, add `run_id: Optional[str] = None` parameter to `PipelineConfig.__init__()` after `event_emitter` param (line ~146)
2. Change `self.run_id = str(uuid.uuid4())` (line 200) to `self.run_id = run_id or str(uuid.uuid4())`
3. Import `PipelineRun` from `llm_pipeline.state` at top of `execute()` method (lazy import, consistent with existing pattern of lazy imports inside methods)
4. In `execute()`, after `start_time = datetime.now(timezone.utc)` (line ~463) and before the `if self._event_emitter:` block for PipelineStarted:
   - Create and persist: `pipeline_run = PipelineRun(run_id=self.run_id, pipeline_name=self.pipeline_name, status="running", started_at=start_time)`
   - `self._real_session.add(pipeline_run); self._real_session.flush()`
5. In the success path, after computing `pipeline_execution_time_ms` (line ~764), before/after the PipelineCompleted emit:
   - Update: `pipeline_run.status = "completed"; pipeline_run.completed_at = datetime.now(timezone.utc); pipeline_run.step_count = len(self._executed_steps); pipeline_run.total_time_ms = int(pipeline_execution_time_ms)`
   - `self._real_session.add(pipeline_run); self._real_session.flush()`
6. In the except block (line ~777), before PipelineError emit:
   - Update: `pipeline_run.status = "failed"; pipeline_run.completed_at = datetime.now(timezone.utc)`
   - `self._real_session.add(pipeline_run); self._real_session.flush()`
7. Note: `pipeline_run` variable must be declared before the `try` block (or initialized to None with None-checks in except block) to be accessible in both success and except paths

### Step 3: Implement /runs API Endpoints and Update create_app()
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** /websites/fastapi_tiangolo, /websites/sqlmodel_tiangolo
**Group:** C

1. In `llm_pipeline/ui/app.py`:
   - Add `pipeline_registry: Optional[dict] = None` parameter to `create_app()`
   - After `app.state.engine = ...`, add `app.state.pipeline_registry = pipeline_registry or {}`

2. In `llm_pipeline/ui/routes/runs.py`, implement the following (all `def` sync):

   **Pydantic response models** (define at top of file):
   - `RunListItem`: `run_id: str`, `pipeline_name: str`, `status: str`, `started_at: datetime`, `completed_at: Optional[datetime]`, `step_count: Optional[int]`, `total_time_ms: Optional[int]`
   - `RunListResponse`: `items: List[RunListItem]`, `total: int`, `offset: int`, `limit: int`
   - `StepSummary`: `step_name: str`, `step_number: int`, `execution_time_ms: Optional[int]`, `created_at: datetime`
   - `RunDetail`: all `RunListItem` fields plus `steps: List[StepSummary]`
   - `TriggerRunRequest`: `pipeline_name: str`
   - `TriggerRunResponse`: `run_id: str`, `status: str` (value: "accepted")

   **Query params model**:
   - `RunListParams`: Pydantic `BaseModel` with `pipeline_name: Optional[str] = None`, `status: Optional[str] = None`, `started_after: Optional[datetime] = None`, `started_before: Optional[datetime] = None`, `offset: int = Query(default=0, ge=0)`, `limit: int = Query(default=50, ge=1, le=200)`

   **GET /runs** endpoint:
   - Signature: `def list_runs(params: Annotated[RunListParams, Depends()], db: DBSession, request: Request) -> RunListResponse`
   - Build `select(PipelineRun)` with `.where()` clauses for each non-None param
   - Separate count query: `select(func.count()).select_from(PipelineRun)` with same filters
   - Apply `.offset(params.offset).limit(params.limit)` then `.order_by(PipelineRun.started_at.desc())`
   - Execute both via `db.exec()`, return `RunListResponse`

   **GET /runs/{run_id}** endpoint:
   - Signature: `def get_run(run_id: str, db: DBSession) -> RunDetail`
   - Query `PipelineRun` by `run_id` field (not PK); raise `HTTPException(404)` if not found
   - Query `PipelineStepState` where `run_id == run_id`, order by `step_number`
   - Return `RunDetail` with steps list

   **POST /runs** endpoint:
   - Signature: `def trigger_run(body: TriggerRunRequest, background_tasks: BackgroundTasks, request: Request) -> TriggerRunResponse`
   - Status code 202
   - Check `request.app.state.pipeline_registry.get(body.pipeline_name)` - if not found, raise `HTTPException(404, detail=f"Pipeline '{body.pipeline_name}' not found in registry")`
   - Pre-generate `run_id = str(uuid.uuid4())`
   - `factory = request.app.state.pipeline_registry[body.pipeline_name]`
   - Define inner `def run_pipeline(): pipeline = factory(run_id=run_id, engine=request.app.state.engine); pipeline.execute(...); pipeline.save()` - note: consuming apps define factory signature, so this must be documented
   - `background_tasks.add_task(run_pipeline)`
   - Return `TriggerRunResponse(run_id=run_id, status="accepted")`

   **Imports needed**: `uuid`, `datetime`, `List`, `Optional`, `Annotated`, `func` from sqlalchemy, `select` from sqlmodel, `HTTPException`, `BackgroundTasks`, `Request`, `Query`, `Depends` from fastapi, `PipelineRun`, `PipelineStepState` from llm_pipeline.state, `DBSession` from llm_pipeline.ui.deps

### Step 4: Add httpx dev dependency to pyproject.toml
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `pyproject.toml`, add `httpx>=0.24` to `[project.optional-dependencies].dev` (required by FastAPI `TestClient` for endpoint tests)
2. Verify `httpx` not already present; if already present, skip

### Step 5: Write Endpoint and Integration Tests
**Agent:** backend-development:test-automator
**Skills:** none
**Context7 Docs:** /websites/fastapi_tiangolo
**Group:** D

1. Create `tests/ui/` package with `__init__.py` and `test_runs.py`
2. Shared `conftest.py` in `tests/ui/` with:
   - `app_client` fixture: `create_app(db_path=":memory:")` + `TestClient(app)`
   - `seeded_app_client` fixture: same but inserts 3+ `PipelineRun` rows and matching `PipelineStepState` rows directly via `app.state.engine` session
3. **GET /runs tests** in `TestListRuns` class:
   - Returns 200 with empty `items=[]` when no runs exist
   - Returns all runs when no filters applied
   - `total` count matches actual row count
   - `pipeline_name` filter returns only matching runs
   - `status` filter returns only matching runs
   - `started_after` / `started_before` filters narrow results correctly
   - `offset` and `limit` pagination works (page 2 returns correct slice)
   - `limit` capped at 200 (422 if limit > 200)
   - `offset` must be >= 0 (422 if negative)
   - Results ordered by `started_at` descending
4. **GET /runs/{run_id} tests** in `TestGetRun` class:
   - Returns 200 with run fields and steps list for valid run_id
   - Steps ordered by step_number ascending
   - Returns 404 for unknown run_id
   - `completed_at` and `total_time_ms` are None for status="running"
5. **POST /runs tests** in `TestTriggerRun` class:
   - Returns 202 with `run_id` (UUID format) and `status="accepted"` when pipeline_name in registry
   - Returns 404 when pipeline_name not in registry
   - Returns 404 when registry is empty (no pipeline_registry passed to create_app)
   - Background task is added (verify via mock or check run appears in GET after task completes)
6. **WAL mode test** in `TestWALMode` class:
   - `init_pipeline_db()` sets journal_mode=WAL on file-based SQLite engine
   - `:memory:` engine does not raise (WAL pragma silently ignored)
7. **PipelineRun write integration test** (in `tests/test_pipeline_run_tracking.py`, separate from UI tests):
   - Minimal concrete pipeline subclass using in-memory engine
   - After `execute()`, verify `PipelineRun` row exists with `status="completed"`, `started_at`, `completed_at`, `step_count`, `total_time_ms` all populated
   - After failed `execute()` (mock step to raise), verify `PipelineRun` row has `status="failed"`
   - Verify pre-generated `run_id` is preserved when passed to constructor

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `pipeline_run` variable scope: declared inside try, not accessible in except | High | Declare `pipeline_run = None` before try block; add None-check in except path before updating |
| WAL event listener registered multiple times if `init_pipeline_db()` called repeatedly with same engine | Medium | Listener is idempotent (PRAGMA is safe to re-execute); SQLAlchemy deduplicates identical listeners on same target |
| `step_count` uses `len(self._executed_steps)` which counts unique step classes not total calls | Low | Document behavior in PipelineRun docstring; consistent with PipelineCompleted event field |
| POST /runs factory signature convention: consuming apps must match `(run_id, engine)` kwargs | Medium | Document factory contract in `create_app()` docstring; 404 is returned for unregistered names, preventing silent failures |
| Existing tests may break if `PipelineStepState.run_id` index removal changes query plan | Low | Index removal is backward compatible; composite index covers same lookups; run test suite to verify |
| BackgroundTasks in FastAPI uses thread pool; if pipeline execute() calls `save()` and commits, concurrent GET queries during run may return partial data | Low | WAL mode handles concurrent readers; partial data during run is acceptable (status="running" is visible) |
| `total_time_ms` cast to `int` may lose sub-ms precision | Low | Acceptable for monitoring purposes; `execution_time_ms` in PipelineStepState is already int |

## Success Criteria

- [ ] `PipelineRun` table exists in database after `init_pipeline_db()` with all specified columns and indexes
- [ ] WAL mode is active on SQLite file-based engines after `init_pipeline_db()`
- [ ] Every `PipelineConfig.execute()` call (success or failure) writes a `PipelineRun` row
- [ ] `run_id` passed to `PipelineConfig.__init__()` is preserved in `self.run_id` and in the `PipelineRun` row
- [ ] `GET /api/runs` returns 200 with paginated `RunListResponse` (items, total, offset, limit)
- [ ] `GET /api/runs` filters by `pipeline_name`, `status`, `started_after`, `started_before`
- [ ] `GET /api/runs/{run_id}` returns 200 with `RunDetail` including steps list ordered by `step_number`
- [ ] `GET /api/runs/{run_id}` returns 404 for unknown run_id
- [ ] `POST /api/runs` returns 202 with `run_id` and `status="accepted"` for registered pipeline
- [ ] `POST /api/runs` returns 404 for unregistered pipeline name
- [ ] All existing 484+ pytest tests continue to pass
- [ ] New test suite passes (all GET/POST endpoint tests, WAL test, PipelineRun integration test)
- [ ] `GET /runs` query executes in <200ms against 10k+ row fixture (verifiable via SQLite EXPLAIN QUERY PLAN showing index usage)

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Four files modified (state.py, db/__init__.py, pipeline.py, app.py) plus one new implementation file (runs.py). Core pipeline.py changes are the riskiest - adding writes to execute() could break existing tests if session/flush behavior interacts unexpectedly with existing test fixtures. The run_id injection and variable scope issue require careful placement. Pipeline registry pattern is novel (no prior pattern in codebase). WAL mode is additive and low-risk.
**Suggested Exclusions:** review
