# Performance Patterns Analysis -- llm-pipeline

Task: master-56 | Phase: research | Step: 1

---

## 1. Event Emission System

### Architecture

```
PipelineConfig._emit()
  -> if self._event_emitter is not None:
       -> event_emitter.emit(event)
           -> CompositeEmitter.emit()
               -> for handler in self._handlers:
                   -> handler.emit(event)  # try/except isolated
```

Three handler types:
- **LoggingEventHandler**: category-based log level, calls `event.to_dict()` each time
- **InMemoryEventHandler**: thread-safe list with Lock, calls `event.to_dict()` each time
- **SQLiteEventHandler**: session-per-emit, calls `event.to_dict()` + INSERT + COMMIT

### NFR-001: <1ms per event point with no handler

**Current implementation (pipeline.py L231-238):**
```python
def _emit(self, event: "PipelineEvent") -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

**All emit sites are guarded** by `if self._event_emitter:` checks (pipeline.py L518, L528, L557, L568, L596, L611, etc.). When `event_emitter=None`:
- No event objects constructed
- Single `is not None` attribute check per emission point
- Expected overhead: ~10-50 nanoseconds (well under 1ms)

**Benchmarking needed**: Confirm with pytest-benchmark across 1000 iterations.

### Event Object Creation Cost

Events use `@dataclass(frozen=True, slots=True)`:
- `slots=True`: no `__dict__`, lower memory
- `frozen=True`: `__post_init__` uses `object.__setattr__` for derived `event_type`
- `default_factory=utc_now` calls `datetime.now(timezone.utc)` -- ~1us each

When emitter IS present, event construction + `to_dict()` (via `dataclasses.asdict`) + datetime ISO conversion is the main cost. `asdict()` is known to be slow for nested structures.

### SQLiteEventHandler -- Session-Per-Emit Anti-Pattern

**File**: `llm_pipeline/events/handlers.py` L190-206

```python
def emit(self, event: "PipelineEvent") -> None:
    session = Session(self._engine)  # NEW session every call
    try:
        record = PipelineEventRecord(...)
        session.add(record)
        session.commit()                # COMMIT every call
    finally:
        session.close()                 # CLOSE every call
```

A typical pipeline run emits 15-30+ events. That means 15-30 session open/commit/close cycles. Each SQLite COMMIT triggers an fsync (even in WAL mode). This is the **most expensive handler** and a candidate for batching optimization.

**Recommendation**: Consider batch-flush strategy (accumulate N events, flush periodically or on terminal events).

---

## 2. Pipeline Execution Hot Paths

### Step Loop (pipeline.py L524-809)

For each step iteration:
1. **Strategy selection**: O(n) scan of strategies calling `can_handle(context)` -- n typically 1-5, negligible
2. **StepDefinition.create_step()** (strategy.py L37-135): up to 4 DB queries for prompt auto-discovery
3. **Cache check**: `_hash_step_inputs()` + `_find_cached_state()` -- 2-3 queries
4. **LLM call**: external API latency dominates (seconds)
5. **Extraction + state save**: DB writes, serialization

### Prompt Auto-Discovery Queries (strategy.py L68-113)

`create_step()` issues up to 4 individual SELECT queries:
```
SELECT ... FROM prompt WHERE prompt_key = '{step}.{strategy}' AND prompt_type = 'system' AND is_active = 1
SELECT ... FROM prompt WHERE prompt_key = '{step}.{strategy}' AND prompt_type = 'user' AND is_active = 1
SELECT ... FROM prompt WHERE prompt_key = '{step}' AND prompt_type = 'system' AND is_active = 1
SELECT ... FROM prompt WHERE prompt_key = '{step}' AND prompt_type = 'user' AND is_active = 1
```

These are NOT cached. If a pipeline has 5 steps, that is up to 20 prompt queries per execution. These could be resolved once and cached.

### _hash_step_inputs (pipeline.py L890-896)

Calls `step.prepare_calls()` (user-defined, could be expensive), then `json.dumps(..., sort_keys=True)` + `hashlib.sha256`. Overhead depends on payload size but generally <1ms for typical payloads.

### _find_cached_state (pipeline.py L898-923)

Two queries:
1. `SELECT ... FROM prompt WHERE prompt_key = ?` (for version)
2. `SELECT ... FROM pipeline_step_states WHERE pipeline_name=? AND step_name=? AND input_hash=? [AND prompt_version=?] ORDER BY created_at DESC LIMIT 1`

Covered by `ix_pipeline_step_states_cache` index (pipeline_name, step_name, input_hash). Prompt version is NOT in this index but is a subsequent WHERE filter -- acceptable for SQLite with small result sets.

### N+1 Query in _reconstruct_extractions_from_cache (pipeline.py L937-969)

```python
for extraction_class in extraction_classes:
    run_instances = self.session.exec(
        select(PipelineRunInstance).where(...)
    ).all()
    for run_instance in run_instances:
        instance = self.session.get(model_class, run_instance.model_id)  # 1 query per instance
```

If a step has 50 cached extraction instances, this fires 50 individual `SELECT ... WHERE id = ?` queries. Classic N+1 pattern.

**Fix**: Use `select(model_class).where(model_class.id.in_([...]))` to batch-load all instances.

---

## 3. Database Schema & Indexes

### PipelineRun (state.py L144-178)

| Index | Columns | Used By |
|-------|---------|---------|
| ix_pipeline_runs_name_started | pipeline_name, started_at | list_runs filter+sort |
| ix_pipeline_runs_status | status | list_runs status filter |
| (unique constraint) | run_id | get_run, get_step, get_events lookups |

**Missing for 10k+ scale**:
- Composite index covering `pipeline_name + status + started_at` for filtered+paginated listing
- SQLite unique constraint on run_id creates an implicit index, so run_id lookups are covered

### PipelineStepState (state.py L24-103)

| Index | Columns | Used By |
|-------|---------|---------|
| ix_pipeline_step_states_run | run_id, step_number | get_run steps, list_steps |
| ix_pipeline_step_states_cache | pipeline_name, step_name, input_hash | _find_cached_state |

**Adequate for current queries.** The `run_id` prefix in ix_pipeline_step_states_run covers step listing by run_id.

### PipelineEventRecord (events/models.py L57-61)

| Index | Columns | Used By |
|-------|---------|---------|
| ix_pipeline_events_run_event | run_id, event_type | list_events with type filter |
| ix_pipeline_events_type | event_type | global type queries |
| ix_pipeline_events_run_step | run_id, step_name | list_events with step filter |

**Missing**: The list_events endpoint orders by `timestamp` within a run_id filter. Adding `(run_id, timestamp)` as a covering index would avoid a filesort at scale. However, `ix_pipeline_events_run_event` covers the run_id prefix and SQLite will use it, then sort in-memory -- acceptable for <1000 events per run.

### PipelineRunInstance (state.py L106-141)

| Index | Columns | Used By |
|-------|---------|---------|
| ix_pipeline_run_instances_run | run_id | _reconstruct_extractions_from_cache |
| ix_pipeline_run_instances_model | model_type, model_id | reverse lookups |

**Adequate.** The N+1 issue is in the Python code, not missing indexes.

---

## 4. API Response Time Patterns

### NFR-004: <200ms for run listing with 10k+ runs

**Endpoint**: `GET /api/runs` (runs.py L108-146)

Two queries:
1. `SELECT count(*) FROM pipeline_runs WHERE ...` -- benefits from ix_pipeline_runs_name_started or ix_pipeline_runs_status
2. `SELECT * FROM pipeline_runs WHERE ... ORDER BY started_at DESC LIMIT 50 OFFSET ?` -- pagination

**Concern at 10k+ scale**: `OFFSET` pagination is O(offset) in SQLite. At offset=9950, SQLite must skip 9950 rows. For 200ms target, this may be tight.

**Recommendation**: Benchmark with 10k seeded rows. If OFFSET >5000 is slow, consider keyset pagination (WHERE started_at < last_seen ORDER BY started_at DESC LIMIT 50).

### NFR-005: <100ms for step detail

**Endpoint**: `GET /api/runs/{run_id}/steps/{step_number}` (steps.py L92-122)

Two queries (run validation + step fetch). Both use indexed columns. Expected <10ms for SQLite. The _get_run_or_404 helper adds an unnecessary extra query -- the step query could validate run existence implicitly.

### Session-per-request pattern (deps.py)

Each request creates a new `Session(engine)` wrapped in `ReadOnlySession`. This is correct for FastAPI but note:
- SQLite with WAL mode allows concurrent reads
- Connection pooling is handled by SQLAlchemy's default pool (QueuePool for non-SQLite, StaticPool or NullPool configurable for SQLite)
- No connection pool tuning observed; defaults may be suboptimal for concurrent API access

---

## 5. Profiling Strategy Recommendations

### Benchmark Suite Structure

```
tests/benchmarks/
  conftest.py           -- fixtures for seeded DBs (10k runs), mock events
  test_event_overhead.py -- NFR-001: event emission with no handler
  test_api_response.py   -- NFR-004/005: run listing, step detail at scale
  test_query_patterns.py -- isolated query benchmarks (N+1 detection)
```

### Specific Benchmarks Needed

1. **Event emission no-handler overhead**
   - Create PipelineConfig with `event_emitter=None`
   - Call `_emit(MockEvent())` in tight loop (1000x)
   - Assert mean per-call < 1ms (NFR-001)

2. **Event emission with handlers (characterization)**
   - LoggingEventHandler: measure `to_dict()` + logging overhead
   - InMemoryEventHandler: measure `to_dict()` + list append + lock overhead
   - SQLiteEventHandler: measure session-per-emit cost

3. **Run listing at 10k+ scale**
   - Seed 10k PipelineRun rows with varied pipeline_name, status, dates
   - Benchmark `GET /api/runs?page_size=50` at various offsets
   - Assert <200ms (NFR-004)

4. **Step detail response time**
   - Benchmark `GET /api/runs/{id}/steps/{n}` with realistic data
   - Assert <100ms (NFR-005)

5. **N+1 detection in cache reconstruction**
   - Seed 50 PipelineRunInstance rows
   - Measure `_reconstruct_extractions_from_cache` query count
   - Profile to confirm N+1 pattern

### Optimization Candidates (if benchmarks fail)

| Priority | Area | Action |
|----------|------|--------|
| P0 | Event emission no-handler | Should pass trivially; if not, profile unexpected overhead |
| P1 | SQLiteEventHandler | Batch inserts (accumulate, flush on terminal event) |
| P2 | Run listing at high offset | Keyset pagination or add covering index |
| P3 | N+1 in cache reconstruction | Batch IN() query instead of per-instance GET |
| P4 | Prompt auto-discovery | Cache resolved keys per pipeline execution |
| P5 | _get_run_or_404 duplication | Join or remove redundant validation query |

---

## 6. Dependencies & Tooling

- **pytest-benchmark**: needed for precise microbenchmarks with statistical analysis
- **SQLite in-memory with StaticPool**: test conftest already uses this pattern (tests/ui/conftest.py)
- **TestClient from Starlette**: for API response time benchmarks
- **No external profiling tools needed**: pytest-benchmark captures mean/median/stddev

---

## 7. Key Files Reference

| File | Performance Relevance |
|------|----------------------|
| `llm_pipeline/pipeline.py` L231-238 | `_emit()` hot path |
| `llm_pipeline/pipeline.py` L524-809 | Main execution loop |
| `llm_pipeline/pipeline.py` L937-969 | N+1 cache reconstruction |
| `llm_pipeline/events/emitter.py` | CompositeEmitter dispatch |
| `llm_pipeline/events/handlers.py` L190-206 | SQLiteEventHandler session-per-emit |
| `llm_pipeline/events/types.py` | Event dataclass definitions |
| `llm_pipeline/state.py` | DB models + indexes |
| `llm_pipeline/events/models.py` | PipelineEventRecord + indexes |
| `llm_pipeline/strategy.py` L37-135 | Prompt auto-discovery queries |
| `llm_pipeline/ui/routes/runs.py` | Run listing API |
| `llm_pipeline/ui/routes/steps.py` | Step detail API |
| `llm_pipeline/ui/routes/events.py` | Event listing API |
| `llm_pipeline/ui/deps.py` | Session-per-request pattern |
