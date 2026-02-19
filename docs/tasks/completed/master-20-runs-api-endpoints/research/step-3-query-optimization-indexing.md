# Step 3: Query Optimization & Indexing Research

## 1. Current Schema Analysis

### 1.1 Tables Involved

**pipeline_step_states** - audit trail of each step execution:
- `id` (PK), `pipeline_name`, `run_id`, `step_name`, `step_number`
- `input_hash`, `result_data` (JSON), `context_snapshot` (JSON)
- `prompt_system_key`, `prompt_user_key`, `prompt_version`, `model`
- `created_at`, `execution_time_ms`

**pipeline_run_instances** - links runs to created DB instances:
- `id` (PK), `run_id`, `model_type`, `model_id`, `created_at`

**pipeline_events** - persisted event records:
- `id` (PK), `run_id`, `event_type`, `pipeline_name`, `timestamp`, `event_data` (JSON)

### 1.2 Existing Indexes

```
pipeline_step_states:
  - run_id (Field index=True)                                    -- standalone
  - ix_pipeline_step_states_run (run_id, step_number)            -- composite
  - ix_pipeline_step_states_cache (pipeline_name, step_name, input_hash) -- cache lookup

pipeline_run_instances:
  - run_id (Field index=True)                                    -- standalone
  - ix_pipeline_run_instances_run (run_id)                       -- DUPLICATE of above
  - ix_pipeline_run_instances_model (model_type, model_id)

pipeline_events:
  - ix_pipeline_events_run_event (run_id, event_type)            -- composite
  - ix_pipeline_events_type (event_type)                         -- standalone
```

### 1.3 Index Issues Found

| Issue | Table | Description | Impact |
|-------|-------|-------------|--------|
| DUPLICATE | pipeline_run_instances | `Field(index=True)` on run_id AND `ix_pipeline_run_instances_run(run_id)` create identical indexes | Wasted write I/O |
| REDUNDANT | pipeline_step_states | `Field(index=True)` on run_id is covered by leftmost prefix of `ix_pipeline_step_states_run(run_id, step_number)` | Wasted write I/O |
| MISSING | pipeline_step_states | No index on `pipeline_name` alone or `(pipeline_name, created_at)` | Filter by pipeline_name requires full scan |
| MISSING | pipeline_step_states | No index on `created_at` | Date range queries require full scan |
| MISSING | pipeline_events | No index on `(pipeline_name, timestamp)` | Filter events by pipeline requires full scan |

### 1.4 Database Engine

- Default: **SQLite** via `create_engine(f"sqlite:///{db_path}")`
- Engine is configurable: `init_pipeline_db(engine)` accepts any SQLAlchemy engine
- All query recommendations below work for both SQLite and PostgreSQL
- SQLite-specific note: no parallel writes, no `FOR UPDATE`, limited window function support in older versions

---

## 2. Core Architecture Problem

**There is no dedicated "runs" table.** A "run" is an implicit entity identified by `run_id` scattered across `pipeline_step_states` and `pipeline_events`. To list runs with aggregates, every query must either:

1. `GROUP BY run_id` on step_states (expensive aggregation)
2. Query `pipeline_events` for `pipeline_started`/`pipeline_completed` events (joins needed)
3. Use a dedicated summary table (denormalization)

### 2.1 Option A: Aggregate from pipeline_step_states (No Schema Change)

**Query pattern:**
```python
from sqlalchemy import select, func
from sqlmodel import Session

# Aggregation query
base = (
    select(
        PipelineStepState.run_id,
        PipelineStepState.pipeline_name,
        func.count(PipelineStepState.id).label("step_count"),
        func.coalesce(func.sum(PipelineStepState.execution_time_ms), 0).label("total_time_ms"),
        func.min(PipelineStepState.created_at).label("started_at"),
        func.max(PipelineStepState.created_at).label("completed_at"),
    )
    .group_by(PipelineStepState.run_id, PipelineStepState.pipeline_name)
)

# Filter by pipeline_name (WHERE, before GROUP BY - index-friendly)
if pipeline_name:
    base = base.where(PipelineStepState.pipeline_name == pipeline_name)

# Date range filter (HAVING on MIN(created_at) - NOT index-friendly)
if date_from:
    base = base.having(func.min(PipelineStepState.created_at) >= date_from)
if date_to:
    base = base.having(func.min(PipelineStepState.created_at) <= date_to)

subq = base.subquery()

# Separate count query (more efficient than window function)
total = session.scalar(select(func.count()).select_from(subq))

# Paginated results
results = session.execute(
    select(subq).order_by(subq.c.started_at.desc()).offset(offset).limit(limit)
).all()
```

**Pros:** No schema change, uses existing data.
**Cons:**
- No run "status" (completed/failed/in-progress) - must derive from events or absence of data
- HAVING clause for date range is not index-optimizable
- 10k runs x 5 steps avg = 50k rows to GROUP - borderline for <200ms on SQLite
- `pipeline_name` is repeated per step row (denormalized already, but not at run level)

**Required indexes:**
```python
Index("ix_pss_pipeline_created", "pipeline_name", "created_at")  # filter + date
```

### 2.2 Option B: Derive from pipeline_events

**Query pattern:**
```python
# "started" events = one per run
started = (
    select(
        PipelineEventRecord.run_id,
        PipelineEventRecord.pipeline_name,
        PipelineEventRecord.timestamp.label("started_at"),
    )
    .where(PipelineEventRecord.event_type == "pipeline_started")
    .subquery()
)

# "completed" events for end time + status derivation
completed = (
    select(
        PipelineEventRecord.run_id,
        PipelineEventRecord.timestamp.label("completed_at"),
    )
    .where(PipelineEventRecord.event_type == "pipeline_completed")
    .subquery()
)

# Step counts from step_states
step_agg = (
    select(
        PipelineStepState.run_id,
        func.count(PipelineStepState.id).label("step_count"),
        func.coalesce(func.sum(PipelineStepState.execution_time_ms), 0).label("total_time_ms"),
    )
    .group_by(PipelineStepState.run_id)
    .subquery()
)

# Combine
runs_query = (
    select(
        started.c.run_id,
        started.c.pipeline_name,
        started.c.started_at,
        completed.c.completed_at,
        step_agg.c.step_count,
        step_agg.c.total_time_ms,
    )
    .outerjoin(completed, started.c.run_id == completed.c.run_id)
    .outerjoin(step_agg, started.c.run_id == step_agg.c.run_id)
)
```

**Pros:** Can derive status (completed event exists = done, error event = failed, neither = in-progress). Date filtering on `started.timestamp` is direct WHERE, not HAVING.
**Cons:** Three subqueries + two outer joins per request. More complex. Events might not always be persisted (depends on handler config).

### 2.3 Option C: Dedicated PipelineRun Table (RECOMMENDED)

**Proposed schema:**
```python
class PipelineRun(SQLModel, table=True):
    __tablename__ = "pipeline_runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(max_length=36, unique=True)
    pipeline_name: str = Field(max_length=100)
    status: str = Field(max_length=20, default="running")  # running, completed, failed
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = Field(default=None)
    step_count: int = Field(default=0)
    total_time_ms: Optional[int] = Field(default=None)

    __table_args__ = (
        Index("ix_pipeline_runs_pipeline_started", "pipeline_name", "started_at"),
        Index("ix_pipeline_runs_status", "status", "started_at"),
        Index("ix_pipeline_runs_started", "started_at"),
    )
```

**Write pattern (2 writes per run):**
1. INSERT on `pipeline.execute()` start
2. UPDATE on completion/failure (set status, completed_at, step_count, total_time_ms)

**Query pattern:**
```python
# GET /runs - direct pagination, no GROUP BY
base = select(PipelineRun)

if pipeline_name:
    base = base.where(PipelineRun.pipeline_name == pipeline_name)
if status:
    base = base.where(PipelineRun.status == status)
if date_from:
    base = base.where(PipelineRun.started_at >= date_from)
if date_to:
    base = base.where(PipelineRun.started_at <= date_to)

# Count (separate query)
total = session.scalar(select(func.count()).select_from(base.subquery()))

# Paginated
runs = session.exec(
    base.order_by(PipelineRun.started_at.desc()).offset(offset).limit(limit)
).all()
```

**Pros:**
- Direct pagination without aggregation - guaranteed <200ms even at 100k+ runs
- Status is a real column (filterable, indexable)
- Date range uses direct WHERE on indexed column
- Simple queries, easy to optimize
- Minimal write overhead (2 writes vs N step writes already happening)

**Cons:**
- Schema change required (new table + migration)
- Pipeline code must insert/update this table
- step_count/total_time_ms are denormalized (could drift if steps are manually deleted)

**Recommendation:** Option C. The performance difference is significant. GROUP BY over 50k+ rows on every API call is wasteful when 2 extra writes per run eliminates it entirely. The denormalization risk is minimal since runs are append-only.

---

## 3. Index Recommendations

### 3.1 Remove Redundant Indexes

```python
# PipelineStepState: remove Field(index=True) on run_id
# Covered by ix_pipeline_step_states_run(run_id, step_number)
run_id: str = Field(max_length=36, description="...")  # remove index=True

# PipelineRunInstance: remove Field(index=True) on run_id
# Duplicated by ix_pipeline_run_instances_run(run_id)
run_id: str = Field(max_length=36, description="...")  # remove index=True
```

### 3.2 Add Missing Indexes

**For pipeline_step_states:**
```python
__table_args__ = (
    Index("ix_pipeline_step_states_run", "run_id", "step_number"),           # existing
    Index("ix_pipeline_step_states_cache", "pipeline_name", "step_name", "input_hash"),  # existing
    # NEW: for listing runs filtered by pipeline + date (Option A only)
    Index("ix_pipeline_step_states_pipeline_created", "pipeline_name", "created_at"),
)
```

**For pipeline_events:**
```python
__table_args__ = (
    Index("ix_pipeline_events_run_event", "run_id", "event_type"),  # existing
    Index("ix_pipeline_events_type", "event_type"),                  # existing
    # NEW: for listing/filtering events by pipeline
    Index("ix_pipeline_events_pipeline_ts", "pipeline_name", "timestamp"),
)
```

**For pipeline_runs (if Option C adopted):**
```python
__table_args__ = (
    Index("ix_pipeline_runs_pipeline_started", "pipeline_name", "started_at"),
    Index("ix_pipeline_runs_status_started", "status", "started_at"),
    Index("ix_pipeline_runs_started", "started_at"),  # default sort
)
```

### 3.3 Index Impact on Writes

| Change | Write Cost | Read Benefit |
|--------|-----------|--------------|
| Remove 2 redundant indexes | -2 index updates per write | None (already covered) |
| Add pipeline_created on step_states | +1 index update per step write | Filter by pipeline + date |
| Add pipeline_ts on events | +1 index update per event write | Filter events by pipeline |
| Add 3 indexes on pipeline_runs | +3 index updates per run (2x per run lifecycle) | All list queries O(log n) |
| **Net** | ~Neutral (removed 2, added ~2-4) | Major read improvement |

---

## 4. Query Patterns for Each Endpoint

### 4.1 GET /runs (Paginated List)

**With Option C (PipelineRun table):**
```python
async def list_runs(
    db: ReadOnlySession,
    pipeline_name: str | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    offset: int = 0,
    limit: int = 50,
):
    base = select(PipelineRun)

    if pipeline_name:
        base = base.where(PipelineRun.pipeline_name == pipeline_name)
    if status:
        base = base.where(PipelineRun.status == status)
    if date_from:
        base = base.where(PipelineRun.started_at >= date_from)
    if date_to:
        base = base.where(PipelineRun.started_at <= date_to)

    # Total count - separate query, no window function overhead
    count_stmt = select(func.count()).select_from(base.subquery())
    total = db.scalar(count_stmt)

    # Paginated results
    list_stmt = base.order_by(PipelineRun.started_at.desc()).offset(offset).limit(limit)
    runs = db.scalars(list_stmt).all()

    return {"total": total, "offset": offset, "limit": limit, "runs": runs}
```

**Without Option C (GROUP BY fallback):**
```python
async def list_runs(db: ReadOnlySession, ...):
    agg = (
        select(
            PipelineStepState.run_id,
            PipelineStepState.pipeline_name,
            func.count(PipelineStepState.id).label("step_count"),
            func.coalesce(func.sum(PipelineStepState.execution_time_ms), 0).label("total_time_ms"),
            func.min(PipelineStepState.created_at).label("started_at"),
            func.max(PipelineStepState.created_at).label("completed_at"),
        )
        .group_by(PipelineStepState.run_id, PipelineStepState.pipeline_name)
    )

    if pipeline_name:
        agg = agg.where(PipelineStepState.pipeline_name == pipeline_name)
    if date_from:
        agg = agg.having(func.min(PipelineStepState.created_at) >= date_from)
    if date_to:
        agg = agg.having(func.min(PipelineStepState.created_at) <= date_to)

    subq = agg.subquery()

    total = db.scalar(select(func.count()).select_from(subq))
    results = db.execute(
        select(subq).order_by(subq.c.started_at.desc()).offset(offset).limit(limit)
    ).all()

    return {"total": total, "offset": offset, "limit": limit, "runs": results}
```

### 4.2 GET /runs/{run_id} (Single Run with Steps)

```python
async def get_run(db: ReadOnlySession, run_id: str):
    # Single query: get all steps for this run, ordered
    steps = db.scalars(
        select(PipelineStepState)
        .where(PipelineStepState.run_id == run_id)
        .order_by(PipelineStepState.step_number)
    ).all()

    if not steps:
        raise HTTPException(404, "Run not found")

    # Derive run-level info from steps (or from PipelineRun if Option C)
    run_summary = {
        "run_id": run_id,
        "pipeline_name": steps[0].pipeline_name,
        "step_count": len(steps),
        "total_time_ms": sum(s.execution_time_ms or 0 for s in steps),
        "started_at": steps[0].created_at,
        "completed_at": steps[-1].created_at,
        "steps": steps,
    }
    return run_summary
```

**Performance:** Uses `ix_pipeline_step_states_run(run_id, step_number)` index. Single index seek + ordered scan. Well under 100ms even with 20+ steps.

### 4.3 Efficient COUNT Pattern

Two approaches for total count alongside paginated results:

**Approach A - Separate count query (RECOMMENDED for SQLite):**
```python
# Two queries: one for count, one for results
total = db.scalar(select(func.count()).select_from(base_query.subquery()))
results = db.execute(base_query.offset(offset).limit(limit)).all()
```

**Approach B - Window function (better for PostgreSQL):**
```python
# Single query with window function
window_query = base_query.add_columns(
    func.count().over().label("total_count")
).offset(offset).limit(limit)
rows = db.execute(window_query).all()
total = rows[0].total_count if rows else 0
```

Recommendation: Use Approach A. It's simpler, works well on SQLite, and the overhead of a second query is negligible compared to the complexity of window functions. For PostgreSQL, Approach B can be used as an optimization.

### 4.4 N+1 Prevention

The main N+1 risk: loading steps for each run in the list endpoint.

**Solution:** Do NOT load steps in the list endpoint. The list returns summary data only (step_count, total_time_ms, status). Steps are loaded only in the detail endpoint (`GET /runs/{run_id}`).

If Option C is adopted, the list endpoint doesn't touch `pipeline_step_states` at all - pure `pipeline_runs` table scan.

---

## 5. Pagination Strategy

### 5.1 OFFSET/LIMIT (Recommended for v1)

- Simple, well-understood, supported by all databases
- Performance degrades at high offsets (OFFSET 10000 still scans 10000 rows)
- Acceptable for 10k runs with typical page sizes (20-50)
- At OFFSET 10000 with LIMIT 50: ~10ms on indexed column in SQLite

### 5.2 Cursor-Based (Future Optimization)

```python
# Instead of offset, use last seen value
if cursor:  # cursor = started_at of last item on previous page
    base = base.where(PipelineRun.started_at < cursor)
base = base.order_by(PipelineRun.started_at.desc()).limit(limit)
```

- Constant performance regardless of page depth
- More complex API contract (cursor instead of page number)
- Consider for v2 if pagination depth becomes an issue

### 5.3 Recommendation

Start with OFFSET/LIMIT. For 10k runs with page size 50 = 200 pages max. Even worst case (last page), OFFSET 9950 on an indexed datetime column is fast. Switch to cursor-based only if users regularly paginate deep or run count exceeds 100k.

---

## 6. Performance Estimates

### With Option C (PipelineRun table):

| Query | Estimated Time (10k runs) | Mechanism |
|-------|--------------------------|-----------|
| List runs (no filter) | 5-15ms | Index scan on started_at, LIMIT 50 |
| List runs (filter pipeline_name) | 3-10ms | Index seek on (pipeline_name, started_at) |
| List runs (date range) | 3-10ms | Index range scan on started_at |
| Count total | 5-20ms | Index-only count |
| Get run detail | 1-5ms | Index seek on run_id + step scan |
| **Total list request** | **15-40ms** | Count + paginated results |

### Without Option C (GROUP BY fallback):

| Query | Estimated Time (10k runs, ~50k steps) | Mechanism |
|-------|---------------------------------------|-----------|
| List runs (no filter) | 80-200ms | Full GROUP BY on 50k rows |
| List runs (filter pipeline_name) | 30-100ms | Filtered GROUP BY |
| Count total | 50-150ms | COUNT over grouped result |
| Get run detail | 1-5ms | Same as above |
| **Total list request** | **130-350ms** | Count + paginated GROUP BY |

The GROUP BY approach may exceed the <200ms target under load. The dedicated table approach provides 5-10x headroom.

---

## 7. Summary of Recommendations

### Critical (Do Now):
1. **Remove redundant indexes** on `run_id` (Field-level) from both `PipelineStepState` and `PipelineRunInstance`
2. **Add `ix_pipeline_events_pipeline_ts`** index on `(pipeline_name, timestamp)` to pipeline_events

### Strongly Recommended (Architecture Decision Required):
3. **Create `PipelineRun` table** - dedicated run-level summary for O(1) list queries instead of O(n) aggregation
4. **Add corresponding indexes** on pipeline_runs as specified in Section 3.2

### If No Schema Change Allowed:
5. **Add `ix_pipeline_step_states_pipeline_created`** on `(pipeline_name, created_at)` for filter+date queries
6. Use the GROUP BY query pattern from Section 4.1 with HAVING for date range
7. Accept that <200ms target may be tight at scale; consider caching list results with short TTL

### Query Patterns:
8. Use **separate count query** (not window function) for pagination total
9. **Never load steps in list endpoint** - summary data only; steps loaded in detail endpoint
10. Start with **OFFSET/LIMIT pagination**; cursor-based is a future optimization
