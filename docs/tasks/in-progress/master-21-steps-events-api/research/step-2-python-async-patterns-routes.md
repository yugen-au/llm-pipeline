# Research: Python Async Patterns & Route Implementation for Steps/Events API

## 1. Sync vs Async Decision

### Established Pattern
runs.py uses **sync `def`** endpoints with a comment: "SQLite is sync, FastAPI wraps in threadpool". This is the correct approach for SQLite backends because:
- SQLite does not support async drivers natively (no `aiosqlite` in this project's deps)
- SQLModel's `Session.exec()` is synchronous
- FastAPI automatically offloads sync `def` endpoints to `anyio` threadpool workers
- No performance penalty: thread context switch is ~0.1ms, well within <100ms target

### Recommendation
**Keep sync `def` for all endpoints.** Do NOT use `async def` -- that would block the event loop on synchronous SQLite calls. FastAPI's auto-threadpool is the correct pattern here.

```python
# CORRECT: sync def, FastAPI wraps in threadpool
@router.get("", response_model=StepListResponse)
def list_steps(run_id: str, db: DBSession) -> StepListResponse:
    ...

# WRONG: async def with sync DB calls blocks event loop
@router.get("", response_model=StepListResponse)
async def list_steps(run_id: str, db: DBSession) -> StepListResponse:
    ...
```

### If Async Were Needed Later
Migration path would be: add `aiosqlite` dep, create `AsyncEngine` via `create_async_engine()`, wrap `AsyncSession` in an async ReadOnlySession, update deps.py `get_db` to `async def`. Not needed for current scope.

## 2. Query Patterns for Step Endpoints

### GET /api/runs/{run_id}/steps (list steps ordered by step_number)

```python
# Validates run exists (404 guard), then fetches steps
stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
run = db.exec(stmt).first()
if run is None:
    raise HTTPException(status_code=404, detail="Run not found")

steps_stmt = (
    select(PipelineStepState)
    .where(PipelineStepState.run_id == run_id)
    .order_by(PipelineStepState.step_number)
)
steps = db.exec(steps_stmt).all()
```

**Index coverage:** `ix_pipeline_step_states_run` on `(run_id, step_number)` -- covers both the filter and order_by. SQLite will do an index scan, no filesort needed.

**Pagination:** Not required. Typical runs have 3-10 steps. Even large pipelines rarely exceed 20 steps. Returning all is fine.

### GET /api/runs/{run_id}/steps/{step_number} (step detail)

```python
# Two-column lookup -- single row
stmt = (
    select(PipelineStepState)
    .where(
        PipelineStepState.run_id == run_id,
        PipelineStepState.step_number == step_number,
    )
)
step = db.exec(stmt).first()
if step is None:
    raise HTTPException(status_code=404, detail="Step not found")
```

**Performance:** Single row lookup on composite index `(run_id, step_number)`. SQLite B-tree seek is O(log n). Even at 100k step rows, lookup is <1ms. Well under <100ms target.

**Alternative pattern with 404 for missing run vs missing step:**
```python
# Option A: Just check step exists (simpler, slightly ambiguous 404)
step = db.exec(stmt).first()
if step is None:
    raise HTTPException(status_code=404, detail="Step not found")

# Option B: Check run first, then step (clearer error messages)
run = db.exec(select(PipelineRun).where(PipelineRun.run_id == run_id)).first()
if run is None:
    raise HTTPException(status_code=404, detail="Run not found")
step = db.exec(step_stmt).first()
if step is None:
    raise HTTPException(status_code=404, detail="Step not found for this run")
```

Recommendation: Option A for step detail (one query instead of two, stays under 100ms). The 404 "Step not found" covers both cases. The step list endpoint already validates run existence separately.

### GET /api/runs/{run_id}/context (context evolution)

```python
# Same query as step list but only select needed columns
# SQLModel doesn't support column-level select easily, so fetch full rows
# and map to response model
steps_stmt = (
    select(PipelineStepState)
    .where(PipelineStepState.run_id == run_id)
    .order_by(PipelineStepState.step_number)
)
steps = db.exec(steps_stmt).all()

# Map to context snapshots
snapshots = [
    ContextSnapshot(
        step_name=s.step_name,
        step_number=s.step_number,
        context_snapshot=s.context_snapshot,
    )
    for s in steps
]
```

**Note on JSON column access:** `context_snapshot` is stored as `Column(JSON)`. SQLModel/SQLAlchemy deserializes it automatically on read. No extra parsing needed.

**Optimization option:** If context_snapshot JSON blobs are large and only a subset of columns is needed, use SQLAlchemy Core select:
```python
from sqlalchemy import select as sa_select
stmt = (
    sa_select(
        PipelineStepState.step_name,
        PipelineStepState.step_number,
        PipelineStepState.context_snapshot,
    )
    .where(PipelineStepState.run_id == run_id)
    .order_by(PipelineStepState.step_number)
)
rows = db.execute(stmt).all()
```
This avoids loading `result_data` JSON column unnecessarily. Useful if result_data is large.

## 3. Events Endpoint Query Patterns

### GET /api/runs/{run_id}/events

Two data sources per task description:
1. **PipelineEventRecord** (pipeline_events table) -- persisted events for completed/failed runs
2. **InMemoryEventHandler** -- volatile in-memory events for active/running runs

### Persisted Events Query (Primary Source)

```python
stmt = (
    select(PipelineEventRecord)
    .where(PipelineEventRecord.run_id == run_id)
    .order_by(PipelineEventRecord.timestamp)
)
if event_type is not None:
    stmt = stmt.where(PipelineEventRecord.event_type == event_type)
events = db.exec(stmt).all()
```

**Index coverage:** `ix_pipeline_events_run_event` on `(run_id, event_type)` covers filtered queries. Unfiltered queries use `run_id` prefix of the index.

### InMemoryEventHandler Access Pattern

The `InMemoryEventHandler` stores events in a thread-safe `list[dict]` and provides:
```python
handler.get_events(run_id="abc-123")  # -> list[dict]
handler.get_events_by_type("pipeline_started", run_id="abc-123")  # -> list[dict]
```

**Current gap:** No app-level reference to InMemoryEventHandler instances. The pipeline's `_event_emitter` is set by consuming code, not by the UI layer.

**Recommended integration pattern:**
```python
# In app.py or deps.py
# app.state.active_event_handlers: Dict[str, InMemoryEventHandler] = {}

# In POST /runs trigger_run (runs.py):
from llm_pipeline.events import InMemoryEventHandler, CompositeEmitter, SQLiteEventHandler

handler = InMemoryEventHandler()
app.state.active_event_handlers[run_id] = handler

# Factory creates pipeline with CompositeEmitter including handler
sqlite_handler = SQLiteEventHandler(engine)
emitter = CompositeEmitter(handlers=[handler, sqlite_handler])
pipeline = factory(run_id=run_id, engine=engine, event_emitter=emitter)

# Cleanup: remove from dict when run completes
del app.state.active_event_handlers[run_id]
```

**Events endpoint dual-source logic:**
```python
def list_events(run_id: str, db: DBSession, request: Request, event_type: str = None):
    active_handlers = getattr(request.app.state, "active_event_handlers", {})
    handler = active_handlers.get(run_id)

    if handler is not None:
        # Active run: serve from InMemoryEventHandler
        if event_type:
            events = handler.get_events_by_type(event_type, run_id=run_id)
        else:
            events = handler.get_events(run_id=run_id)
        return EventListResponse(items=[EventItem(**e) for e in events], source="memory")
    else:
        # Completed/persisted run: query DB
        stmt = select(PipelineEventRecord).where(...)
        ...
        return EventListResponse(items=..., source="database")
```

**Thread safety:** InMemoryEventHandler uses `threading.Lock` internally. Safe to call `get_events()` from FastAPI threadpool workers concurrently with pipeline execution calling `emit()`.

### Pagination for Events

Events per run can be substantial (50-200+ for a multi-step pipeline with LLM calls). Recommend optional pagination:
```python
class EventListParams(BaseModel):
    event_type: Optional[str] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)
```

For InMemoryEventHandler results (list[dict]), apply offset/limit in Python:
```python
events = handler.get_events(run_id=run_id)
total = len(events)
paged = events[offset:offset + limit]
```

## 4. Pydantic v2 Response Models

### Step List Item (summary view)

```python
class StepListItem(BaseModel):
    step_name: str
    step_number: int
    execution_time_ms: Optional[int] = None
    model: Optional[str] = None
    created_at: datetime
```

### Step Detail (full view)

```python
class StepDetail(BaseModel):
    step_name: str
    step_number: int
    pipeline_name: str
    run_id: str
    input_hash: str
    result_data: dict
    context_snapshot: dict
    prompt_system_key: Optional[str] = None
    prompt_user_key: Optional[str] = None
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    execution_time_ms: Optional[int] = None
    created_at: datetime
```

### Context Snapshot (for JSON diff)

```python
class ContextSnapshot(BaseModel):
    step_name: str
    step_number: int
    context_snapshot: dict

class ContextEvolutionResponse(BaseModel):
    run_id: str
    snapshots: list[ContextSnapshot]
```

### Event Item

```python
class EventItem(BaseModel):
    event_type: str
    pipeline_name: str
    run_id: str
    timestamp: datetime
    event_data: dict

class EventListResponse(BaseModel):
    items: list[EventItem]
    total: int
    source: str  # "memory" or "database"
```

**Note on `source` field:** Including `source` helps the UI distinguish between live and persisted data. The UI can show "live" badge for memory-sourced events. This is optional but useful.

### Consistency with runs.py patterns

- All models inherit from `BaseModel` (not `SQLModel`)
- List responses include `total` count
- Optional fields use `Optional[T] = None`
- datetime fields serialize as ISO strings automatically (Pydantic v2 default)
- Use `list[T]` not `List[T]` (Python 3.11+ project)

## 5. Error Handling Patterns

### 404 for Missing Runs

All endpoints under `/runs/{run_id}/...` should validate run existence:
```python
def _get_run_or_404(db: ReadOnlySession, run_id: str) -> PipelineRun:
    """Shared helper: fetch run or raise 404."""
    stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
    run = db.exec(stmt).first()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
```

This can be a module-level helper in steps.py (and imported in events.py if needed) or extracted to a shared `helpers.py`.

### 404 for Missing Steps

```python
# Step detail: single lookup, 404 if not found
if step is None:
    raise HTTPException(status_code=404, detail="Step not found")
```

### Query Parameter Validation

FastAPI + Pydantic v2 handle this automatically:
- `step_number: int` in path -- invalid int returns 422
- `offset: int = Query(default=0, ge=0)` -- negative returns 422
- `limit: int = Query(default=100, ge=1, le=500)` -- out of range returns 422
- `event_type: Optional[str] = None` -- no validation needed (free-form string matches DB column)

### run_id Format

Task 20 recommendations suggest UUID format validation. For consistency, keep the same un-validated string pattern used by runs.py `get_run`. Can be added later as a cross-cutting concern.

## 6. Context Evolution for JSON Diff Display

### UI Intent
The context evolution endpoint returns ordered snapshots so the UI can show JSON diffs between consecutive steps. The UI will diff `snapshots[n].context_snapshot` vs `snapshots[n+1].context_snapshot`.

### Response Shape
```json
{
  "run_id": "abc-123",
  "snapshots": [
    {
      "step_name": "table_type_detection",
      "step_number": 1,
      "context_snapshot": {"table_type": "rate_card", "columns": 5}
    },
    {
      "step_name": "header_extraction",
      "step_number": 2,
      "context_snapshot": {"table_type": "rate_card", "columns": 5, "headers": ["origin", "dest"]}
    }
  ]
}
```

### Placement Decision
`GET /api/runs/{run_id}/context` -- this path is at the run level, not under steps. Two options:

**Option A: Add to runs.py** -- runs router has `prefix="/runs"`, so path `"/{run_id}/context"` gives `/api/runs/{run_id}/context`. Clean fit.

**Option B: Add to steps.py with explicit path** -- steps router has `prefix="/runs/{run_id}/steps"`. Would need a separate router or path hack. Not clean.

**Recommendation:** Option A -- add to runs.py. It's a run-level view of aggregated step data. Logically belongs with run endpoints.

However, if step-1 research (architecture) decides to put it in steps.py, the router prefix would need to change from `/runs/{run_id}/steps` to `/runs/{run_id}` and step endpoints would use path `/steps` and `/steps/{step_number}`. This is also valid but changes the router structure.

## 7. Router Prefix Adjustments

### events.py: Change Required
```python
# Current (wrong for task spec):
router = APIRouter(prefix="/events", tags=["events"])

# Correct:
router = APIRouter(prefix="/runs/{run_id}/events", tags=["events"])
```

All event endpoints then get `run_id: str` as a path parameter automatically.

### steps.py: No Change Needed
```python
router = APIRouter(prefix="/runs/{run_id}/steps", tags=["steps"])
```
Already matches task spec for `/api/runs/{run_id}/steps`.

### Context endpoint
If placed in runs.py (recommended), no prefix changes needed. Path `"/{run_id}/context"` under `prefix="/runs"` gives the correct URL.

## 8. Test Patterns

### Follow test_runs.py Conventions
- Class-based test groups: `TestListSteps`, `TestGetStep`, `TestContextEvolution`, `TestListEvents`
- Use `seeded_app_client` fixture (extend with PipelineEventRecord seed data)
- Assert status codes, response body structure, ordering, 404 handling
- Constants for run IDs at top: `RUN_1 = "aaaaaaaa-0000-0000-0000-000000000001"`

### Seed Data Extensions
conftest.py needs PipelineEventRecord rows for events testing:
```python
from llm_pipeline.events.models import PipelineEventRecord

event1 = PipelineEventRecord(
    run_id=RUN_1,
    event_type="pipeline_started",
    pipeline_name="alpha_pipeline",
    timestamp=_utc(-300),
    event_data={"event_type": "pipeline_started", "run_id": RUN_1, "pipeline_name": "alpha_pipeline"},
)
event2 = PipelineEventRecord(
    run_id=RUN_1,
    event_type="step_started",
    pipeline_name="alpha_pipeline",
    timestamp=_utc(-299),
    event_data={"event_type": "step_started", "run_id": RUN_1, "step_name": "step_a"},
)
```

### Key Test Cases
**Steps list:**
- Returns steps ordered by step_number
- Returns 404 for nonexistent run
- Empty steps list for run with no steps
- Response fields present (step_name, step_number, execution_time_ms, model, created_at)

**Step detail:**
- Returns full detail including result_data, context_snapshot
- Returns 404 for nonexistent step_number
- Returns 404 for nonexistent run_id
- Includes prompt keys and model when present

**Context evolution:**
- Returns ordered snapshots
- Each snapshot has step_name, step_number, context_snapshot
- Empty list for run with no steps

**Events list:**
- Returns events ordered by timestamp
- Filters by event_type query param
- Returns 404 for nonexistent run
- Empty list when no events for run

## 9. Performance Analysis

### Step Detail (<100ms target)
- **Query:** Single row by composite index `(run_id, step_number)` -- B-tree seek O(log n)
- **JSON deserialization:** `result_data` and `context_snapshot` deserialized by SQLAlchemy JSON column type -- sub-millisecond for typical payloads (<100KB)
- **Pydantic serialization:** dict -> BaseModel -> JSON response -- <1ms
- **Network overhead:** local loopback ~0.1ms, production network ~1-10ms
- **Total estimated:** 2-5ms for the full request/response cycle
- **Verdict:** Easily meets <100ms target

### Step List
- **Query:** Index scan on `(run_id, step_number)` returning ~3-10 rows
- **Total estimated:** 3-10ms

### Context Evolution
- **Same query as step list.** No additional overhead. 3-10ms.

### Events List (unpaginated)
- **Query:** Index scan on `run_id` returning ~50-200 rows
- **JSON column `event_data`:** Each row has a JSON blob. With 200 rows of ~1KB each, ~200KB total data transfer.
- **Total estimated:** 10-30ms
- **With pagination (limit=100):** 5-15ms

## 10. Summary of Key Patterns

| Aspect | Pattern | Source |
|--------|---------|--------|
| Endpoint style | `def` (sync), not `async def` | runs.py precedent |
| DB dependency | `db: DBSession` via `Annotated[ReadOnlySession, Depends(get_db)]` | deps.py |
| Response models | plain `BaseModel`, not SQLModel | runs.py precedent |
| 404 handling | `HTTPException(status_code=404, detail="...")` | runs.py |
| Query execution | `db.exec(select(...).where(...)).all()` | runs.py |
| Test client | `TestClient` with `StaticPool` in-memory SQLite | conftest.py |
| Events dual-source | Check `app.state.active_event_handlers` dict, fall back to DB | New pattern |
| Run validation | Helper fn `_get_run_or_404()` for shared 404 guard | New pattern |
| Context endpoint | In runs.py as `GET /{run_id}/context` | Recommended |
