# Research Summary

## Executive Summary

Cross-referenced all 3 research documents against actual codebase (`state.py`, `pipeline.py`, `deps.py`, `app.py`, `events/models.py`, `session/readonly.py`, `db/__init__.py`). Model schemas, indexes, dependency injection patterns, and FastAPI app factory are accurately documented. Initial validation surfaced 5 hidden assumptions, 4 inter-document contradictions, and 3 blocking architectural questions. All 3 questions answered by CEO. All contradictions resolved. No remaining blockers for planning.

Key architectural decisions locked in: dedicated PipelineRun table with core pipeline.py writes, POST /runs stays in scope (requires run_id injection + pipeline registry), SQLite WAL mode for concurrent API safety.

## Domain Findings

### Finding 1: run_id Ownership Conflict (POST /runs)
**Source:** step-2, verified against `llm_pipeline/pipeline.py` line 200

Step 2's POST skeleton generates `run_id = str(uuid.uuid4())` in the endpoint and returns it immediately. But `PipelineConfig.__init__()` also generates `self.run_id = str(uuid.uuid4())`. These produce two different UUIDs. The client gets one run_id, the pipeline uses another. All step states, events, and run instances are recorded under the pipeline's internal run_id, making the returned run_id useless for subsequent GET queries.

**Resolution (no CEO input needed):** Add optional `run_id` parameter to `PipelineConfig.__init__()` with fallback to uuid4(). Backward compatible -- existing callers unaffected.

```python
def __init__(self, ..., run_id: Optional[str] = None):
    ...
    self.run_id = run_id or str(uuid.uuid4())
```

### Finding 2: PipelineRun Table Write Integration
**Source:** step-3 (Option C recommendation), verified against `llm_pipeline/pipeline.py`

**CEO Decision:** Core pipeline.py writes PipelineRun on every execution (all runs tracked, not just API-triggered).

Write integration points in `execute()`:
- INSERT at start (near PipelineStarted emission, ~line 467): status="running"
- UPDATE on success (near PipelineCompleted emission, ~line 767): status="completed", set completed_at/step_count/total_time_ms
- UPDATE on failure (in except block, ~line 777): status="failed", set completed_at

Transaction detail: uses `self._real_session.add()` + `self._real_session.flush()` consistent with existing `_save_step_state` pattern (line 946-947). The PipelineRun record becomes visible to other sessions only after `save()` calls `commit()`. For API-triggered runs, the background function should call `self._real_session.commit()` after the PipelineRun UPDATE to make it visible to GET queries without requiring `save()`.

New table must be added to `init_pipeline_db()` create_all() tables list (line 60-68).

### Finding 3: Pipeline Resolution Complexity for POST /runs
**Source:** step-2 section 8, verified against `llm_pipeline/pipeline.py` lines 85-213

**CEO Decision:** POST /runs stays in task 20 scope.

Constructing a PipelineConfig subclass requires registry, strategies, provider, engine, and optionally event_emitter. No global registry exists.

**Resolution:** App-level pipeline registry pattern. The consuming application registers pipeline factories with the FastAPI app:

```python
# Consuming app populates:
app.state.pipeline_registry = {
    "rate_card_parser": lambda run_id, engine: RateCardParserPipeline(
        provider=gemini_provider, engine=engine, run_id=run_id,
    ),
}
```

POST endpoint looks up `pipeline_name` in `app.state.pipeline_registry`. If not found, 404. The endpoint itself needs no writable DB session -- pipeline handles all writes internally via `self._real_session`.

`create_app()` should accept optional `pipeline_registry` parameter. If None, POST /runs returns 501 (not implemented) or the registry defaults to empty dict (POST returns 404 for any pipeline_name).

### Finding 4: SQLite Concurrent Access
**Source:** step-3 section 1.4, verified against `llm_pipeline/db/__init__.py`

**CEO Decision:** YES, configure WAL mode.

Two `create_engine` call sites exist:
- `db/__init__.py:54` -- `create_engine(db_url, echo=False)` (auto-SQLite path)
- `ui/app.py:43` -- `create_engine(f"sqlite:///{db_path}")` (app factory path)

Both pass through `init_pipeline_db()`. WAL mode should be configured there via SQLAlchemy event listener:

```python
from sqlalchemy import event

def init_pipeline_db(engine=None):
    ...
    if engine.url.drivername.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_wal(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()
    ...
```

This is safe for both file-based SQLite and in-memory (`:memory:` ignores WAL pragma silently). Note: app.py:43 creates engine without `echo=False` -- minor inconsistency, not a bug.

### Finding 5: Event Persistence is Optional
**Source:** step-1, step-3 (Option B), verified against `llm_pipeline/pipeline.py` line 157

`event_emitter` is optional in PipelineConfig constructor. Pipelines without emitter produce zero event records. Only `PipelineStepState` records are guaranteed. With CEO decision to create PipelineRun table with core writes, this finding is **mitigated** -- PipelineRun writes are unconditional (not gated on event_emitter), providing a reliable runs index regardless of event configuration.

### Finding 6: Pre-existing Bug in clear_cache()
**Source:** verified in `llm_pipeline/pipeline.py` lines 791-805

`clear_cache()` calls `self.session.delete()` and `self.session.commit()`, but `self.session` is a `ReadOnlySession` which raises `RuntimeError` on both operations. Out of scope for task 20, tracked as separate item.

### Finding 7: Inter-Document Contradictions (All Resolved)
**Source:** cross-referencing step-1, step-2, step-3

| Contradiction | Step 2 Says | Step 3 Says | Resolution |
|---|---|---|---|
| Endpoint style | `def` (sync) | `async def` | Step 2 correct. Codebase entirely sync. `async def` with sync DB calls blocks event loop. |
| `completed_at` type | `datetime` (required) | `Optional[datetime]` | Step 3 correct. Running pipelines have no completed_at. |
| `total_time_ms` type | `int` (required) | `Optional[int]` | Step 3 correct. Steps may have None execution_time_ms. |
| `status` filter | Included in RunListParams | Only works with Option C | Resolved by CEO: PipelineRun table adopted, status filter valid. |

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should we create a dedicated PipelineRun table (Step 3 Option C)? If yes, should pipeline.py core write to it or only API-triggered runs? | YES. Core pipeline.py writes on every execution (all runs tracked). | Eliminates GROUP BY aggregation queries. All runs (API + direct Python) tracked. Guarantees <200ms for 10k+ runs. Adds 2 writes per run lifecycle to execute(). |
| Should POST /runs be deferred to a separate task? | NO. Keep in task 20. Task definition explicitly includes POST /runs, and task 21 depends on task 20 completing all endpoints. | Must solve run_id injection (add param to PipelineConfig.__init__), pipeline registry (app.state pattern), and background execution (BackgroundTasks). |
| Should we configure SQLite WAL mode in init_pipeline_db()? | YES. Configure for concurrent read/write safety. | Prevents GET queries from blocking during background pipeline writes. Applied via SQLAlchemy event listener in init_pipeline_db(). |

## Assumptions Validated
- [x] PipelineStepState schema matches research (all columns, types, indexes verified)
- [x] PipelineRunInstance schema matches research (columns, indexes, purpose verified)
- [x] PipelineEventRecord schema matches research (columns, indexes verified)
- [x] ReadOnlySession blocks all write operations listed in research
- [x] ReadOnlySession allows exec, execute, scalar, scalars, get, query (verified)
- [x] deps.py yields ReadOnlySession, closes underlying Session in finally block
- [x] create_app() mounts routers with prefix="/api", lazy imports inside function body
- [x] runs.py route stub exists with `prefix="/runs"` and empty router
- [x] PipelineConfig.execute() emits PipelineStarted and PipelineCompleted events
- [x] PipelineConfig.execute() is sync (not async)
- [x] Step states are saved via flush() (not commit) during execution
- [x] pipeline.save() is the only place commit() is called on the real session
- [x] run_id is generated in PipelineConfig.__init__() with no external override option
- [x] No pipeline registry or factory pattern exists in the codebase
- [x] init_pipeline_db() returns the engine (used by app.state.engine)
- [x] get_session() returns a writable Session (not ReadOnlySession)
- [x] PipelineRun table (Option C) provides guaranteed <200ms at 10k+ runs (vs borderline GROUP BY)
- [x] BackgroundTasks runs sync callables via run_in_executor (no need for asyncio.to_thread wrapper)
- [x] POST /runs endpoint itself needs no writable DB session (pipeline handles writes internally)

## Assumptions Invalidated
- [x] POST /runs can pre-generate run_id and pass to pipeline -- INVALID: PipelineConfig generates its own run_id with no injection point. Fix: add optional run_id param.
- [x] Pipeline resolution is a simple name-to-class mapping -- INVALID: requires full dependency graph (registry, strategies, provider, engine, emitter). Fix: app.state.pipeline_registry with factory callables.
- [x] Status can be derived from existing data reliably -- RESOLVED: PipelineRun table provides explicit status column.
- [x] Step 2's RunListItem fields are all non-optional -- INVALID: completed_at and total_time_ms must be Optional for running/incomplete pipelines.

## Open Items
- clear_cache() bug: uses ReadOnlySession for write ops. Out of scope, track separately.
- Redundant index cleanup (Step 3 section 3.1): remove Field(index=True) on run_id from PipelineStepState and PipelineRunInstance. Low risk, can proceed during implementation.
- httpx dev dependency for TestClient (noted in Step 1). Minor, add during implementation.
- app.py:43 creates engine without echo=False (inconsistent with db/__init__.py:54). Cosmetic, not a bug.

## Recommendations for Planning
1. **Implement PipelineRun model in state.py** -- SQLModel table=True, columns: id, run_id (unique), pipeline_name, status, started_at, completed_at, step_count, total_time_ms. Add indexes per Step 3 section 3.2.
2. **Modify pipeline.py execute()** -- INSERT PipelineRun at start, UPDATE on success/failure. Use self._real_session.add() + flush() consistent with _save_step_state pattern.
3. **Add run_id parameter to PipelineConfig.__init__()** -- `run_id: Optional[str] = None` with `self.run_id = run_id or str(uuid.uuid4())`. Backward compatible.
4. **Configure WAL mode in init_pipeline_db()** -- SQLAlchemy event listener for PRAGMA journal_mode=WAL on SQLite engines.
5. **Add PipelineRun to init_pipeline_db() create_all()** -- include PipelineRun.__table__ in tables list.
6. **Implement GET /runs** -- use `def` (sync), PipelineRun table direct query, offset/limit pagination, RunListParams Pydantic model with status/pipeline_name/date filters. Separate count query (not window function).
7. **Implement GET /runs/{run_id}** -- use `def` (sync), query PipelineRun + PipelineStepState for step summaries. 404 if not found.
8. **Implement POST /runs** -- use `def` (sync), validate pipeline_name against app.state.pipeline_registry, pre-generate run_id, create pipeline with run_id, schedule BackgroundTasks. Return 202 with run_id.
9. **Add pipeline_registry param to create_app()** -- optional dict, stored on app.state. POST /runs returns 404 if registry empty or pipeline not found.
10. **Fix response model optionality** -- completed_at: Optional[datetime], total_time_ms: Optional[int] in both RunListItem and RunDetail.
11. **Remove redundant indexes** -- Field(index=True) on run_id in PipelineStepState and PipelineRunInstance.
12. **Use def (sync) for ALL endpoints** -- FastAPI auto-threadpools sync endpoints; avoids event loop blocking with sync DB calls.
