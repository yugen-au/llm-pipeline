# API Response Time Benchmarking & Query Optimization

Task: master-56 | Phase: research | Step: 3 (backend-architect)

---

## 1. NFR Target Analysis

### NFR-004: <200ms for listing 10k+ pipeline runs (paginated)

**Endpoint:** `GET /api/runs` (`llm_pipeline/ui/routes/runs.py` L108-146)

Query flow:
1. COUNT query: `SELECT count(*) FROM pipeline_runs WHERE <filters>`
2. DATA query: `SELECT * FROM pipeline_runs WHERE <filters> ORDER BY started_at DESC LIMIT :limit OFFSET :offset`

Both queries go through `_apply_filters()` which appends WHERE clauses for pipeline_name, status, started_after, started_before.

**Critical observations:**
- Offset-based pagination is O(offset) in SQLite. At offset=9950 with 10k rows, SQLite must scan and discard 9950 rows before returning the final 50. This is the highest-risk path for NFR-004.
- Default limit=50, max limit=200. Worst case: 200 rows returned per page.
- Two separate queries per request (count + data). Both traverse the same index paths.

### NFR-005: <100ms for step detail retrieval

**Endpoint:** `GET /api/runs/{run_id}/steps/{step_number}` (`llm_pipeline/ui/routes/steps.py` L92-122)

Query flow:
1. `_get_run_or_404()`: `SELECT * FROM pipeline_runs WHERE run_id = :run_id` (unique index lookup)
2. Step fetch: `SELECT * FROM pipeline_step_states WHERE run_id = :run_id AND step_number = :step_number`

**Critical observations:**
- Both queries hit indexed columns. Expected <5ms each on SQLite.
- `_get_run_or_404()` adds a validation query that could be eliminated by JOINing or checking step query results, but overhead is negligible (~2-3ms).
- PipelineStepState has JSON columns (result_data, context_snapshot) that are deserialized for every step detail request. These can be large. This is unavoidable for the detail endpoint but is the main variable affecting response time.

---

## 2. Current Index Coverage

### PipelineRun (`pipeline_runs`)

| Index | Columns | Covers |
|-------|---------|--------|
| ix_pipeline_runs_name_started | (pipeline_name, started_at) | filter by pipeline_name + ORDER BY started_at |
| ix_pipeline_runs_status | (status) | filter by status only |
| unique constraint | (run_id) | get_run, _get_run_or_404 |

**Gaps identified:**

1. **No standalone started_at index.** Unfiltered `list_runs` orders by `started_at DESC`. The composite index (pipeline_name, started_at) cannot be used for ordering when pipeline_name is not in the WHERE clause. SQLite falls back to a full table scan + filesort. At 10k rows this is likely the primary bottleneck for unfiltered listing.

2. **Standalone status index lacks ordering.** Filtering by status alone (`WHERE status = 'completed' ORDER BY started_at DESC`) uses ix_pipeline_runs_status for the WHERE but must filesort for ORDER BY. Replacing with composite (status, started_at) enables indexed ordering.

3. **No covering index for combined pipeline_name + status filter.** `WHERE pipeline_name = ? AND status = ? ORDER BY started_at DESC` uses ix_pipeline_runs_name_started for the first two predicates but status is not in this index.

### PipelineStepState (`pipeline_step_states`)

| Index | Columns | Covers |
|-------|---------|--------|
| ix_pipeline_step_states_run | (run_id, step_number) | get_step, list_steps |
| ix_pipeline_step_states_cache | (pipeline_name, step_name, input_hash) | cache lookups |

**Adequate for NFR-005.** The (run_id, step_number) composite covers exact step lookups and step listing ordered by step_number within a run.

### PipelineEventRecord (`pipeline_events`)

| Index | Columns | Covers |
|-------|---------|--------|
| ix_pipeline_events_run_event | (run_id, event_type) | events by run + type filter |
| ix_pipeline_events_type | (event_type) | global type queries |
| ix_pipeline_events_run_step | (run_id, step_name) | events by run + step filter |

**Gap:** The list_events endpoint orders by `timestamp` within a `run_id` filter. No (run_id, timestamp) index exists. Events per run are typically <100, so in-memory sort is acceptable. Only flag if event volume grows significantly.

---

## 3. Recommended Index Changes

### Priority 1: Standalone started_at index (NFR-004 critical path)

```python
# state.py PipelineRun.__table_args__
Index("ix_pipeline_runs_started", "started_at"),
```

**Why:** Unfiltered `list_runs` is the most common query. Without this index, SQLite does a full table scan at 10k rows. With the index, it can do an index scan in DESC order and stop after LIMIT rows.

### Priority 2: Replace standalone status index with composite

```python
# Replace: Index("ix_pipeline_runs_status", "status")
# With:    Index("ix_pipeline_runs_status_started", "status", "started_at")
```

**Why:** Status-filtered queries also need ORDER BY started_at DESC. The composite index covers both WHERE and ORDER BY, avoiding a filesort. SQLite can walk the index in reverse for DESC ordering.

### Priority 3: Optional covering index for triple filter (defer unless benchmarks fail)

```python
Index("ix_pipeline_runs_name_status_started", "pipeline_name", "status", "started_at")
```

**Why:** Covers `WHERE pipeline_name = ? AND status = ? ORDER BY started_at DESC`. Only needed if combined-filter queries are slow at scale. The existing (pipeline_name, started_at) index already covers the common single-filter case.

### No changes needed for:
- PipelineStepState indexes (adequate for NFR-005)
- PipelineEventRecord indexes (adequate for typical event volumes)
- PipelineRunInstance indexes (not in API hot path)

---

## 4. Query Optimization Patterns

### 4.1 Column Projection for List Endpoints

**Current pattern (runs.py L120):**
```python
data_stmt = select(PipelineRun)  # SELECT * -- loads all columns
```

PipelineRun has no JSON columns, so full-row loading is acceptable. For PipelineStepState list queries (steps.py L71-76), the query loads JSON columns (result_data, context_snapshot) that are NOT used in StepListItem. At small scale this is fine; at scale it wastes deserialization time.

**Potential optimization (only if benchmarks fail):**
```python
# Column projection for step listing
data_stmt = select(
    PipelineStepState.step_name,
    PipelineStepState.step_number,
    PipelineStepState.execution_time_ms,
    PipelineStepState.model,
    PipelineStepState.created_at,
).where(PipelineStepState.run_id == run_id)
```

**Trade-off:** Returns Row tuples instead of model instances. Requires different attribute access pattern. Recommend deferring unless benchmarks show JSON deserialization as a bottleneck.

### 4.2 Eager Loading (selectinload / joinedload)

**Not applicable here.** The current models have no SQLAlchemy relationships defined (no `Relationship()` fields). PipelineRun and PipelineStepState are linked by `run_id` string field, not FK relationships. The get_run endpoint issues two separate queries by design. Adding ORM relationships would be a schema change beyond performance tuning scope.

If relationships were added in the future:
- `selectinload`: Preferred for collections (e.g., loading steps for a run). Issues a second SELECT ... WHERE run_id IN (...) query. Good when parent count is small.
- `joinedload`: Single query with JOIN. Better for single-parent lookups. Use `innerjoin=True` when the relationship is guaranteed to exist.

### 4.3 Offset Pagination Risk

**Current:** `OFFSET :offset LIMIT :limit` (runs.py L126)

At 10k rows with offset=9950, SQLite scans 9950 rows to discard them. For the 200ms target:
- SQLite typically handles 10k-row table scans in 5-20ms on modern hardware
- The real cost is in the Python side: SQLModel object creation + Pydantic serialization for 50 items

**If offset pagination is slow at high offsets, consider keyset pagination:**
```python
# Instead of: .offset(9950).limit(50)
# Use:        .where(PipelineRun.started_at < last_seen_started_at).limit(50)
```

This changes the API contract (offset/limit -> cursor-based). Defer unless benchmarks confirm offset >5000 exceeds 200ms.

### 4.4 COUNT(*) Optimization

`SELECT count(*) FROM pipeline_runs WHERE ...` must count all matching rows. At 10k rows with no filter, this is a full scan. SQLite does not maintain row counts.

**Mitigations:**
- Indexes help filtered counts (SQLite counts index entries)
- Run `ANALYZE` after bulk data changes to update sqlite_stat1 (helps query planner)
- For unfiltered count, the standalone started_at index provides a scannable structure

### 4.5 ANALYZE Command for Query Planner

SQLite's query planner uses statistics from `sqlite_stat1` to choose between indexes. After bulk insert of 10k rows, running ANALYZE ensures optimal index selection.

```python
# In benchmark fixture, after bulk insert:
with engine.connect() as conn:
    conn.execute(text("ANALYZE"))
    conn.commit()
```

---

## 5. Test Fixture Patterns for 10k+ Rows

### 5.1 Bulk Insert Pattern

```python
import uuid
from datetime import datetime, timezone, timedelta
from sqlmodel import Session
from llm_pipeline.state import PipelineRun, PipelineStepState
from sqlalchemy import text

PIPELINE_NAMES = [f"pipeline_{i}" for i in range(10)]
STATUSES = ["running", "completed", "failed"]

def _utc(offset_seconds: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)

def seed_large_db(engine, run_count: int = 10_000, steps_per_run: int = 0):
    """Bulk-insert pipeline runs with optional steps.

    Uses session.add_all() for batched INSERTs.
    Runs ANALYZE after insert for optimal query plans.
    """
    with Session(engine) as session:
        runs = [
            PipelineRun(
                run_id=f"{i:08x}-0000-0000-0000-000000000000",
                pipeline_name=PIPELINE_NAMES[i % 10],
                status=STATUSES[i % 3],
                started_at=_utc(-i * 10),
                completed_at=_utc(-i * 10 + 5) if i % 3 == 1 else None,
                step_count=i % 5 if i % 3 == 1 else None,
                total_time_ms=i * 100 if i % 3 == 1 else None,
            )
            for i in range(run_count)
        ]
        session.add_all(runs)
        session.commit()

        if steps_per_run > 0:
            # Seed steps for first 100 runs only (for step detail benchmarks)
            steps = []
            for i in range(min(100, run_count)):
                run_id = f"{i:08x}-0000-0000-0000-000000000000"
                for s in range(1, steps_per_run + 1):
                    steps.append(PipelineStepState(
                        run_id=run_id,
                        pipeline_name=PIPELINE_NAMES[i % 10],
                        step_name=f"step_{s}",
                        step_number=s,
                        input_hash=f"hash_{i}_{s}",
                        result_data={"value": i * s},
                        context_snapshot={"step": s},
                        execution_time_ms=100 * s,
                        created_at=_utc(-i * 10 + s),
                    ))
            session.add_all(steps)
            session.commit()

    # Update query planner statistics
    with engine.connect() as conn:
        conn.execute(text("ANALYZE"))
        conn.commit()
```

### 5.2 Fixture Scoping

```python
@pytest.fixture(scope="module")
def large_app():
    """Module-scoped fixture: create app + seed 10k runs once per test module."""
    app = _make_app()  # from conftest.py pattern (StaticPool, in-memory)
    seed_large_db(app.state.engine, run_count=10_000, steps_per_run=3)
    return app

@pytest.fixture
def large_client(large_app):
    """Per-test client backed by pre-seeded large DB."""
    with TestClient(large_app) as client:
        yield client
```

**scope="module"** is critical: seeding 10k rows takes ~2-5 seconds. Doing it once per module (not per test) keeps the benchmark suite fast. All tests in the module share the same seeded data.

### 5.3 Run ID Convention for Benchmarks

Use deterministic run_ids (formatted hex) rather than random UUIDs. This allows benchmark tests to reference specific runs by index:

```python
def run_id_for(i: int) -> str:
    return f"{i:08x}-0000-0000-0000-000000000000"

# In test: fetch run at index 5000 (middle of dataset)
resp = client.get(f"/api/runs/{run_id_for(5000)}")
```

---

## 6. Benchmark Test Patterns

### 6.1 Measurement Approach

**Recommendation: `time.perf_counter()` with warmup iterations.**

Rationale:
- No new dependency needed (pytest-benchmark not in dev deps)
- `perf_counter()` is monotonic + high resolution (unlike `time.time()`)
- Simple assertion-based pass/fail aligns with CI integration
- Step-1 research suggests pytest-benchmark; either approach works. If pytest-benchmark is added for step-1/step-2 benchmarks, these tests can adopt it too.

```python
import time

def _measure(fn, warmup=3, iterations=5):
    """Run fn with warmup, return median elapsed time in seconds."""
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        elapsed = time.perf_counter() - start
        times.append(elapsed)
    times.sort()
    return times[len(times) // 2]  # median
```

### 6.2 NFR-004 Benchmark: Run Listing at Scale

```python
class TestRunListPerformance:
    """NFR-004: <200ms for listing 10k+ runs (paginated)."""

    def test_unfiltered_first_page(self, large_client):
        """Most common query: no filters, default pagination."""
        elapsed = _measure(
            lambda: large_client.get("/api/runs?limit=50&offset=0")
        )
        assert elapsed < 0.200, f"Unfiltered first page: {elapsed*1000:.0f}ms > 200ms"

    def test_unfiltered_mid_page(self, large_client):
        """Offset pagination at midpoint (offset=5000)."""
        elapsed = _measure(
            lambda: large_client.get("/api/runs?limit=50&offset=5000")
        )
        assert elapsed < 0.200, f"Unfiltered mid page: {elapsed*1000:.0f}ms > 200ms"

    def test_unfiltered_last_page(self, large_client):
        """Worst case: high offset near end of dataset."""
        elapsed = _measure(
            lambda: large_client.get("/api/runs?limit=50&offset=9950")
        )
        assert elapsed < 0.200, f"Unfiltered last page: {elapsed*1000:.0f}ms > 200ms"

    def test_filtered_by_pipeline_name(self, large_client):
        """Filter by pipeline_name (covers ~1k rows out of 10k)."""
        elapsed = _measure(
            lambda: large_client.get("/api/runs?pipeline_name=pipeline_0&limit=50")
        )
        assert elapsed < 0.200, f"Pipeline filter: {elapsed*1000:.0f}ms > 200ms"

    def test_filtered_by_status(self, large_client):
        """Filter by status (covers ~3.3k rows out of 10k)."""
        elapsed = _measure(
            lambda: large_client.get("/api/runs?status=completed&limit=50")
        )
        assert elapsed < 0.200, f"Status filter: {elapsed*1000:.0f}ms > 200ms"

    def test_combined_filters(self, large_client):
        """Filter by pipeline_name + status (narrow result set)."""
        elapsed = _measure(
            lambda: large_client.get(
                "/api/runs?pipeline_name=pipeline_0&status=completed&limit=50"
            )
        )
        assert elapsed < 0.200, f"Combined filter: {elapsed*1000:.0f}ms > 200ms"
```

### 6.3 NFR-005 Benchmark: Step Detail

```python
class TestStepDetailPerformance:
    """NFR-005: <100ms for step detail retrieval."""

    def test_step_detail_response_time(self, large_client):
        """Single step detail lookup by run_id + step_number."""
        run_id = run_id_for(50)  # run with seeded steps
        elapsed = _measure(
            lambda: large_client.get(f"/api/runs/{run_id}/steps/1")
        )
        assert elapsed < 0.100, f"Step detail: {elapsed*1000:.0f}ms > 100ms"

    def test_step_list_response_time(self, large_client):
        """List all steps for a run (3 steps seeded)."""
        run_id = run_id_for(50)
        elapsed = _measure(
            lambda: large_client.get(f"/api/runs/{run_id}/steps")
        )
        assert elapsed < 0.100, f"Step list: {elapsed*1000:.0f}ms > 100ms"

    def test_run_detail_with_steps(self, large_client):
        """Run detail includes step summaries (2 queries)."""
        run_id = run_id_for(50)
        elapsed = _measure(
            lambda: large_client.get(f"/api/runs/{run_id}")
        )
        assert elapsed < 0.100, f"Run detail: {elapsed*1000:.0f}ms > 100ms"
```

### 6.4 Benchmark File Structure

```
tests/benchmarks/
    __init__.py
    conftest.py        -- large_app, large_client, seed_large_db, _measure, run_id_for
    test_api_response.py  -- NFR-004/005 benchmarks (TestRunListPerformance, TestStepDetailPerformance)
```

Use `conftest.py` for module-scoped fixtures. Benchmarks import `_make_app` from `tests.ui.conftest` to reuse the StaticPool pattern.

---

## 7. Database-Level Optimizations

### 7.1 WAL Mode (already enabled)

`init_pipeline_db()` in `llm_pipeline/db/__init__.py` L61-68 enables WAL mode for SQLite. This allows concurrent readers during writes. No change needed.

### 7.2 Connection Pooling

SQLite does not benefit from traditional connection pooling. Current setup:
- In-memory test DBs: `StaticPool` (single connection shared) -- correct
- File-based production: SQLAlchemy default `QueuePool` -- works but `NullPool` is often recommended for SQLite to avoid connection sharing issues

No changes recommended for benchmarking scope.

### 7.3 Prepared Statements

SQLAlchemy uses parameterized queries by default through the DBAPI layer. SQLite caches prepared statement bytecode per connection. No additional configuration needed.

### 7.4 PRAGMA Optimizations (test-only)

For benchmark fixtures, additional PRAGMAs can reduce overhead:
```python
# In benchmark conftest.py, after engine creation:
@event.listens_for(engine, "connect")
def set_sqlite_pragmas(dbapi_conn, conn_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")   # faster commits (ok for testing)
    cursor.execute("PRAGMA cache_size=-64000")     # 64MB page cache
    cursor.execute("PRAGMA mmap_size=268435456")   # 256MB mmap (reduces I/O)
    cursor.close()
```

These should NOT be set in production code. They reduce durability guarantees in exchange for speed, which is acceptable for benchmarking.

---

## 8. Response Serialization Overhead

API response time includes Pydantic model serialization. For `RunListResponse` with 50 items:
- Each `RunListItem` has 7 fields (strings, datetime, optional int)
- `model_validate()` + JSON serialization is typically <1ms for 50 items
- FastAPI's `response_model=RunListResponse` triggers validation on output

For `StepDetail` with JSON columns:
- `result_data` and `context_snapshot` are arbitrary dicts
- Large payloads (>100KB) may push serialization time above 10ms
- Benchmark fixtures should include realistic JSON sizes (not just `{"value": 1}`)

**Recommendation for fixtures:** Include result_data/context_snapshot of ~1-5KB per step to simulate realistic workloads.

---

## 9. Coordination with Step-1 (perf-patterns)

Step-1 research identifies several optimization candidates that overlap with API benchmarking:

| Step-1 Finding | Impact on Step-3 |
|----------------|------------------|
| N+1 in _reconstruct_extractions_from_cache | Not in API hot path (pipeline execution, not API read) |
| Prompt auto-discovery 4 queries per step | Not in API hot path |
| SQLiteEventHandler session-per-emit | Not in API read path; affects write path during trigger_run |
| Missing composite index for triple filter | Covered in section 3 above |
| Offset pagination risk at high offsets | Covered in section 4.3 above |

Key distinction: Step-1 focuses on pipeline execution hot paths. Step-3 focuses on API read path performance. The only shared concern is index optimization on PipelineRun.

---

## 10. Summary of Recommendations

### Must-do (implement during task 56):

1. Add `Index("ix_pipeline_runs_started", "started_at")` to PipelineRun for unfiltered listing
2. Replace `Index("ix_pipeline_runs_status", "status")` with `Index("ix_pipeline_runs_status_started", "status", "started_at")` for filtered+ordered queries
3. Create `tests/benchmarks/` with conftest.py (seed_large_db, _measure, module-scoped fixtures)
4. Create `tests/benchmarks/test_api_response.py` with NFR-004/005 benchmark tests
5. Run `ANALYZE` after bulk insert in benchmark fixtures

### Do-if-benchmarks-fail:

6. Column projection for step list queries (avoid JSON deserialization)
7. Keyset pagination for high-offset queries
8. Add `Index("ix_pipeline_runs_name_status_started", "pipeline_name", "status", "started_at")` for combined-filter queries
9. Add `Index("ix_pipeline_events_run_ts", "run_id", "timestamp")` for event listing

### Out of scope (handled by other steps/tasks):

- Event emission overhead benchmarks (step-1 / step-2 scope)
- SQLiteEventHandler batching optimization (step-1 recommendation)
- N+1 cache reconstruction fix (pipeline execution, not API read path)
- pytest-benchmark dependency decision (step-2 scope)
