# Research: Existing API & DB Architecture for Steps/Events Endpoints

## 1. Route Patterns (from Task 20 runs.py)

### Router Setup
- `APIRouter(prefix="/runs", tags=["runs"])` -- registered in `app.py` with `prefix="/api"` -> final path `/api/runs`
- Sync `def` endpoints (not `async def`) -- comment: "SQLite is sync, FastAPI wraps in threadpool"
- Response/request models: plain `Pydantic BaseModel`, NOT SQLModel table classes
- DB dependency: `db: DBSession` where `DBSession = Annotated[ReadOnlySession, Depends(get_db)]`

### Endpoint Pattern
```python
@router.get("", response_model=RunListResponse)
def list_runs(
    params: Annotated[RunListParams, Depends()],  # query params via Depends
    db: DBSession,
) -> RunListResponse:
```

### Query Pattern
- Count: `select(func.count()).select_from(Model)` with `.where()` filters
- Data: `select(Model).where(...).order_by(...).offset(...).limit(...)`
- Execute: `db.exec(stmt).all()` or `db.exec(stmt).first()`
- Scalar: `db.scalar(count_stmt)`

### Response Model Pattern
- Separate list response wrapper: `RunListResponse(items=[], total=int, offset=int, limit=int)`
- Manual model-to-response mapping in endpoint (no ORM serialization)
- 404 via `HTTPException(status_code=404, detail="...")`

### Filter Helper Pattern
```python
def _apply_filters(stmt, params):
    if params.field is not None:
        stmt = stmt.where(Model.field == params.field)
    return stmt
```

## 2. Existing Stub Routers

### steps.py (Task 21 target)
```python
router = APIRouter(prefix="/runs/{run_id}/steps", tags=["steps"])
```
- Registered: `app.include_router(steps_router, prefix="/api")` -> `/api/runs/{run_id}/steps`
- Path param `{run_id}` embedded in prefix -- endpoint defs get `run_id` as path param automatically

### events.py (Task 21 target)
```python
router = APIRouter(prefix="/events", tags=["events"])
```
- Registered: `app.include_router(events_router, prefix="/api")` -> `/api/events`
- **NEEDS CHANGE**: Task spec wants `/runs/{run_id}/events`. Prefix should become `/runs/{run_id}/events`

## 3. Database Models

### PipelineStepState (`pipeline_step_states` table)
| Column | Type | Notes |
|--------|------|-------|
| id | int (PK) | auto-increment |
| pipeline_name | str(100) | snake_case |
| run_id | str(36) | UUID |
| step_name | str(100) | e.g. 'table_type_detection' |
| step_number | int | execution order (1, 2, 3...) |
| input_hash | str(64) | cache invalidation |
| result_data | JSON dict | step result (serialized) |
| context_snapshot | JSON dict | context at this point |
| prompt_system_key | str(200) | optional |
| prompt_user_key | str(200) | optional |
| prompt_version | str(20) | optional |
| model | str(50) | LLM model used, optional |
| created_at | datetime | UTC |
| execution_time_ms | int | optional |

**Indexes:**
- `ix_pipeline_step_states_run` on `(run_id, step_number)` -- perfect for step queries by run
- `ix_pipeline_step_states_cache` on `(pipeline_name, step_name, input_hash)` -- cache lookups

### PipelineEventRecord (`pipeline_events` table)
| Column | Type | Notes |
|--------|------|-------|
| id | int (PK) | auto-increment |
| run_id | str(36) | UUID |
| event_type | str(100) | e.g. 'pipeline_started' |
| pipeline_name | str(100) | snake_case |
| timestamp | datetime | UTC |
| event_data | JSON dict | full serialized event payload |

**Indexes:**
- `ix_pipeline_events_run_event` on `(run_id, event_type)` -- run+type filtered queries
- `ix_pipeline_events_type` on `(event_type)` -- type-only queries

### PipelineRun (`pipeline_runs` table)
Used by existing runs.py endpoints. Steps/events endpoints need only verify run existence via this table (404 guard).

## 4. ReadOnlySession

Wraps `sqlmodel.Session`, allows read-only operations:
- `exec()`, `execute()`, `scalar()`, `scalars()`, `query()`, `get()`
- Blocks: `add`, `add_all`, `delete`, `flush`, `commit`, `merge`, `refresh`, `expire`, `expunge`

Created per-request in `deps.py`:
```python
def get_db(request: Request) -> Generator[ReadOnlySession, None, None]:
    engine = request.app.state.engine
    session = Session(engine)
    try:
        yield ReadOnlySession(session)
    finally:
        session.close()
```

## 5. Router Registration (app.py)

```python
app.include_router(runs_router, prefix="/api")
app.include_router(steps_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(prompts_router, prefix="/api")
app.include_router(pipelines_router, prefix="/api")
app.include_router(ws_router)  # no /api prefix for websocket
```

All route modules already imported and registered. No changes needed in app.py.

## 6. Test Infrastructure

### conftest.py (`tests/ui/conftest.py`)
- `_make_app()`: creates FastAPI app with `StaticPool` in-memory SQLite (thread-safe)
- `app_client` fixture: empty DB
- `seeded_app_client` fixture: 3 PipelineRun rows + 3 PipelineStepState rows
- Uses `TestClient` from starlette

### Seeded Data (for reference)
- **RUN_1** (completed, alpha_pipeline): 2 steps (step_a, step_b) with result_data and context_snapshot
- **RUN_2** (failed, beta_pipeline): 1 step (step_a)
- **RUN_3** (running, alpha_pipeline): 0 steps

### Extension Needed
- Add `PipelineEventRecord` rows to seeded fixture for events endpoint testing
- Import `PipelineEventRecord` in conftest.py

## 7. Endpoint Design Mapping

### GET /api/runs/{run_id}/steps (list steps)
- Source: `PipelineStepState WHERE run_id = ? ORDER BY step_number`
- Index hit: `ix_pipeline_step_states_run`
- Response: list of step summaries (step_name, step_number, execution_time_ms, created_at, model)
- 404 if run not found (check PipelineRun first)

### GET /api/runs/{run_id}/steps/{step_number} (step detail)
- Source: `PipelineStepState WHERE run_id = ? AND step_number = ?`
- Index hit: `ix_pipeline_step_states_run` (covers both columns)
- Response: full step detail including result_data, context_snapshot, prompt keys, model
- Target: <100ms (single row index lookup)
- 404 if step not found

### GET /api/runs/{run_id}/context (context evolution)
- Source: `PipelineStepState WHERE run_id = ? ORDER BY step_number`
- Select only: step_name, step_number, context_snapshot
- Response: ordered array of {step_name, step_number, context_snapshot} for JSON diff display

### GET /api/runs/{run_id}/events (list events)
- Source: `PipelineEventRecord WHERE run_id = ?`
- Optional filter: `event_type` query param -> `AND event_type = ?`
- Index hit: `ix_pipeline_events_run_event` (covers run_id + event_type)
- Response: list of event records ordered by timestamp

## 8. Design Decisions

### Events data source: PipelineEventRecord (DB) only
Task mentions "InMemoryEventHandler (active) or pipeline_events (persisted)". For REST GET endpoints, PipelineEventRecord is the correct source -- it's durable and queryable. InMemoryEventHandler is volatile in-process memory, suitable for WebSocket live streaming (task 25, downstream). REST endpoints should use the persisted table.

### Events router prefix change
Current stub: `prefix="/events"`. Change to: `prefix="/runs/{run_id}/events"` to match RESTful nesting and task spec.

### Pagination
- Steps list: no pagination needed (typical run has 3-10 steps)
- Events list: consider optional pagination (a run could have 50-200+ events). Add offset/limit with sensible defaults matching runs.py pattern.
- Context evolution: no pagination (same cardinality as steps)

### Run existence validation
All endpoints under `/runs/{run_id}/...` should validate the run exists first. Use `PipelineRun WHERE run_id = ?` check and return 404 if not found. This matches the get_run pattern in runs.py.

## 9. Files to Create/Modify

### Modify
- `llm_pipeline/ui/routes/steps.py` -- implement 3 endpoints (list steps, step detail, context evolution)
- `llm_pipeline/ui/routes/events.py` -- change prefix, implement list events endpoint
- `tests/ui/conftest.py` -- add PipelineEventRecord seed data

### Create
- `tests/ui/test_steps.py` -- step list, step detail, context evolution tests
- `tests/ui/test_events.py` -- event list, event type filter tests

### No changes needed
- `llm_pipeline/ui/app.py` -- routers already registered
- `llm_pipeline/ui/deps.py` -- DBSession dependency unchanged
- `llm_pipeline/state.py` -- models unchanged
- `llm_pipeline/events/models.py` -- PipelineEventRecord unchanged
