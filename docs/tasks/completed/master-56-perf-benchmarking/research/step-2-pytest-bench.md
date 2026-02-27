# Step 2: pytest-benchmark Patterns and Python Performance Testing Research

## 1. pytest-benchmark Library

### 1.1 Core Fixture Usage

The `benchmark` fixture is injected by pytest-benchmark. Two primary modes:

**Standard mode** (auto-calibration):
```python
def test_event_emit_no_handler(benchmark):
    pipeline = build_pipeline(event_emitter=None)
    event = PipelineStarted(run_id="test", pipeline_name="bench")

    result = benchmark(pipeline._emit, event)
    # Assertions after benchmark (not timed)
    assert result is None
```

**Pedantic mode** (explicit control, better for sub-ms):
```python
def test_event_emit_overhead_pedantic(benchmark):
    pipeline = build_pipeline(event_emitter=None)
    event = PipelineStarted(run_id="test", pipeline_name="bench")

    benchmark.pedantic(
        pipeline._emit,
        args=(event,),
        iterations=1000,   # calls per round
        rounds=100,         # statistical samples
        warmup_rounds=5,
    )
```

Pedantic bypasses auto-calibration. Critical for sub-ms targets where calibration overhead can dominate.

### 1.2 Parametrization

Combine with `@pytest.mark.parametrize` for multiple scenarios:
```python
@pytest.mark.parametrize("handler_count", [0, 1, 3, 5])
def test_composite_emitter_scaling(benchmark, handler_count):
    handlers = [InMemoryEventHandler() for _ in range(handler_count)]
    emitter = CompositeEmitter(handlers=handlers) if handlers else None
    pipeline = build_pipeline(event_emitter=emitter)
    event = PipelineStarted(run_id="test", pipeline_name="bench")
    benchmark.pedantic(pipeline._emit, args=(event,), iterations=1000, rounds=50)
```

### 1.3 Grouping and Organization

```python
@pytest.mark.benchmark(group="event-emission")
def test_emit_no_handler(benchmark):
    ...

@pytest.mark.benchmark(group="api-response")
def test_run_list_10k(benchmark):
    ...
```

Groups appear in separate tables in output. Useful for separating NFR categories.

### 1.4 Statistical Analysis

pytest-benchmark reports per test: min, max, mean, stddev, median, IQR, outliers, OPS (operations/sec), rounds, iterations.

Key settings for reliable sub-ms stats:
- `min_rounds=50` -- minimum statistical sample
- `min_time=0.1` -- minimum total benchmark time (seconds)
- `warmup=True` -- warm CPU caches
- `disable_gc=True` -- exclude GC jitter (set per-test via mark)

### 1.5 Timer Selection

Default: `time.perf_counter` (float seconds, ~ns resolution on modern OS). Sufficient for all NFR targets. For absolute nanosecond precision: `time.perf_counter_ns` (int nanoseconds, avoids float rounding). Set via:
```python
@pytest.mark.benchmark(timer=time.perf_counter_ns)
```
Or globally: `--benchmark-timer=time.perf_counter_ns`

**Recommendation**: Use default `time.perf_counter` -- sufficient for <1ms targets. perf_counter_ns only needed if measuring <1us operations.

### 1.6 CI Integration

**Saving results**:
```ini
# pyproject.toml
[tool.pytest.ini_options]
addopts_benchmarks = "--benchmark-autosave --benchmark-storage=file://.benchmarks"
```

**Regression detection**:
```bash
# CI command
pytest tests/benchmarks/ --benchmark-compare=0001 --benchmark-compare-fail=mean:10%
```

`--benchmark-compare-fail` accepts:
- Percentage: `mean:10%` (fail if 10% slower than baseline)
- Absolute: `mean:0.001` (fail if 1ms slower)
- Fields: `min`, `max`, `mean`, `median`, `stddev`

**Recommended CI threshold**: `mean:15%` for initial setup, tighten to `mean:10%` once baseline is stable.

**JSON output**: `--benchmark-json=benchmark-results.json` for CI artifact storage.

### 1.7 Skipping Benchmarks in Regular Test Runs

```bash
# Normal test run (skip benchmarks)
pytest --benchmark-skip

# Benchmark-only run
pytest tests/benchmarks/ --benchmark-only

# Full run including benchmarks
pytest tests/benchmarks/ --benchmark-enable
```

Configure in pyproject.toml so `pytest` alone skips benchmarks:
```ini
[tool.pytest.ini_options]
addopts = "--benchmark-skip"
```
Then CI explicitly runs `pytest tests/benchmarks/ --benchmark-only`.

## 2. Python Profiling Integration

### 2.1 cProfile

Not directly integrated with pytest-benchmark. Use separately for hotspot identification:
```python
import cProfile
import pstats

def profile_event_emission():
    profiler = cProfile.Profile()
    profiler.enable()
    # ... run benchmark target ...
    profiler.disable()
    stats = pstats.Stats(profiler).sort_stats('cumulative')
    stats.print_stats(20)
```

**pytest-profiling** plugin: `pip install pytest-profiling`, then `pytest --profile` generates cProfile output per test. Orthogonal to pytest-benchmark (different concerns).

### 2.2 memory_profiler

Useful for ensuring event emission doesn't leak memory in high-volume scenarios:
```python
from memory_profiler import memory_usage

def test_event_memory_stability():
    def emit_10k():
        handler = InMemoryEventHandler()
        emitter = CompositeEmitter(handlers=[handler])
        event = PipelineStarted(run_id="test", pipeline_name="bench")
        for _ in range(10_000):
            emitter.emit(event)
    mem = memory_usage((emit_10k,), interval=0.01, max_iterations=1)
    assert max(mem) - min(mem) < 50  # MB delta
```

**Not recommended for CI benchmark suite** -- adds significant overhead. Use as separate diagnostic tool.

### 2.3 line_profiler

For micro-optimization of hot paths (e.g., `_emit`, `CompositeEmitter.emit`):
```python
from line_profiler import LineProfiler

lp = LineProfiler()
lp.add_function(CompositeEmitter.emit)
lp.enable()
# ... run target ...
lp.disable()
lp.print_stats()
```

Use ad-hoc during optimization, not in CI.

## 3. Benchmark Test Structure for llm-pipeline

### 3.1 Directory Layout

```
tests/
  benchmarks/
    __init__.py
    conftest.py              # shared fixtures: engines, large_db, pipelines
    test_event_overhead.py   # NFR-001: event emission <1ms
    test_api_response.py     # NFR-004/005: API <200ms/100ms
    test_event_construction.py  # event dataclass creation overhead
    pytest.ini               # (optional) benchmark-specific config
```

### 3.2 conftest.py Pattern

```python
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session
from starlette.testclient import TestClient

from llm_pipeline.db import init_pipeline_db
from llm_pipeline.state import PipelineRun, PipelineStepState
from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.events.emitter import CompositeEmitter
from llm_pipeline.events.handlers import InMemoryEventHandler


@pytest.fixture(scope="module")
def bench_engine():
    """Shared in-memory SQLite engine for benchmark module."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_pipeline_db(engine)
    return engine


@pytest.fixture(scope="module")
def large_db(bench_engine):
    """Populate 10k+ runs with steps and events for API benchmarks.

    Module-scoped: created once, reused across all tests in module.
    Uses bulk operations for speed.
    """
    _utc = lambda offset: datetime.now(timezone.utc) + timedelta(seconds=offset)
    with Session(bench_engine) as session:
        # Bulk insert 10,000 runs
        runs = [
            PipelineRun(
                run_id=f"bench-{i:05d}-0000-0000-000000000000",
                pipeline_name=f"pipeline_{i % 5}",
                status=["completed", "failed", "running"][i % 3],
                started_at=_utc(-i * 10),
                completed_at=_utc(-i * 10 + 5) if i % 3 != 2 else None,
                step_count=3 if i % 3 == 0 else 1,
                total_time_ms=5000 + (i % 100) * 10,
            )
            for i in range(10_000)
        ]
        session.add_all(runs)
        session.flush()

        # 2 steps per completed run = ~6,666 step records
        steps = []
        for i in range(10_000):
            if i % 3 == 0:  # completed runs
                for s in range(1, 3):
                    steps.append(PipelineStepState(
                        run_id=f"bench-{i:05d}-0000-0000-000000000000",
                        pipeline_name=f"pipeline_{i % 5}",
                        step_name=f"step_{s}",
                        step_number=s,
                        input_hash=f"hash_{i}_{s}",
                        result_data={"v": i},
                        context_snapshot={"k": "v"},
                        execution_time_ms=1000 + s * 500,
                    ))
        session.add_all(steps)
        session.flush()

        # Events for subset (first 1000 runs)
        events = []
        for i in range(1000):
            events.append(PipelineEventRecord(
                run_id=f"bench-{i:05d}-0000-0000-000000000000",
                event_type="pipeline_started",
                pipeline_name=f"pipeline_{i % 5}",
                timestamp=_utc(-i * 10),
                event_data={"event_type": "pipeline_started"},
            ))
        session.add_all(events)
        session.commit()
    return bench_engine


@pytest.fixture
def large_db_client(large_db):
    """TestClient backed by the large_db engine."""
    from llm_pipeline.ui.app import create_app
    # Reuse existing pattern from tests/ui/conftest.py
    # but inject the pre-populated engine
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from llm_pipeline.ui.routes.runs import router as runs_router
    from llm_pipeline.ui.routes.steps import router as steps_router
    from llm_pipeline.ui.routes.events import router as events_router

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"])
    app.state.engine = large_db
    app.state.pipeline_registry = {}
    app.include_router(runs_router, prefix="/api")
    app.include_router(steps_router, prefix="/api")
    app.include_router(events_router, prefix="/api")
    with TestClient(app) as client:
        yield client
```

Key patterns:
- **`scope="module"`** for large_db: avoids recreating 10k rows per test. Read-only benchmarks can share data.
- **`StaticPool`** for in-memory SQLite thread safety (matches existing test patterns).
- **`session.add_all()` + `flush()`** for bulk insertion instead of individual adds.
- **Realistic data distribution**: varied pipeline_names, statuses, timestamps.

### 3.3 Alternative: `session.execute(insert(...).values([...]))` for Maximum Insert Speed

For 10k+ rows, Core-level bulk insert is 3-5x faster than ORM add_all:
```python
from sqlalchemy import insert
session.execute(
    insert(PipelineRun),
    [{"run_id": f"bench-{i}", "pipeline_name": f"p_{i%5}", ...} for i in range(10_000)]
)
```

Trade-off: loses SQLModel defaults/validators. Acceptable for test fixtures.

## 4. Time Measurement Approaches

### 4.1 Wall Clock vs CPU Time

| Approach | Function | Measures | Use When |
|----------|----------|----------|----------|
| Wall clock | `time.perf_counter` | Elapsed real time | I/O-bound, real-world latency (API response) |
| CPU time | `time.process_time` | CPU cycles only | Pure computation, excluding I/O waits |
| Nanosecond | `time.perf_counter_ns` | Wall clock in ns (int) | Sub-microsecond precision needed |

**For this project**:
- **Event emission** (NFR-001): Use wall clock (`perf_counter`, default). The overhead IS the real time cost.
- **API response** (NFR-004/005): Use wall clock. TestClient measures actual HTTP round-trip through FastAPI stack.
- pytest-benchmark uses `perf_counter` by default -- no change needed.

### 4.2 Sub-millisecond Precision Considerations

At <1ms targets, noise sources matter:
1. **GC pauses**: Use `disable_gc=True` on benchmark mark
2. **OS scheduling**: High iteration count (1000+) averages it out
3. **Python object creation**: Frozen dataclass creation has overhead (~1-5us). Pre-create events outside benchmark loop when testing pure emit path.
4. **datetime.now()**: `utc_now()` in PipelineEvent default field factory adds ~0.5-1us per event creation. If benchmarking emit-only, pre-create events.

### 4.3 Measuring Event Emission Accurately

The `_emit` method in `PipelineConfig`:
```python
def _emit(self, event: "PipelineEvent") -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

For NFR-001 (<1ms when no handler), the benchmark target is literally:
```python
def test_emit_no_handler(benchmark):
    # Pre-create event (exclude construction cost)
    event = PipelineStarted(run_id="r", pipeline_name="p")

    class MinimalPipeline:
        _event_emitter = None
        def _emit(self, event):
            if self._event_emitter is not None:
                self._event_emitter.emit(event)

    pipeline = MinimalPipeline()
    benchmark.pedantic(pipeline._emit, args=(event,), iterations=10000, rounds=100)
```

This measures pure dispatch overhead. Separate tests for:
1. Event construction cost (dataclass creation)
2. Emit with no handler (None check)
3. Emit with 1 handler (InMemoryEventHandler)
4. Emit with N handlers via CompositeEmitter
5. SQLiteEventHandler emit overhead (includes DB write)

## 5. Async vs Sync Benchmarking

### 5.1 Current Architecture

All API endpoints are `def` (sync), not `async def`. FastAPI runs them in threadpool. SQLite operations are inherently sync. The event system is entirely synchronous.

**No async benchmarking needed for current codebase.**

### 5.2 If Async Needed Later

pytest-benchmark does not natively support async (issue #66 open since 2016). Workaround:
```python
import asyncio

def test_async_operation(benchmark):
    loop = asyncio.get_event_loop()

    async def target():
        await some_async_operation()

    benchmark(loop.run_until_complete, target())
```

Or use `pytest-asyncio` with manual timing:
```python
@pytest.mark.asyncio
async def test_async_perf():
    start = time.perf_counter()
    await some_operation()
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1  # 100ms
```

## 6. CI-Friendly Configuration

### 6.1 pyproject.toml Additions

```toml
[project.optional-dependencies]
dev = [
    # ... existing ...
    "pytest-benchmark>=4.0",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
# Skip benchmarks in normal test runs
addopts = "--benchmark-skip"

# Benchmark-specific markers
markers = [
    "benchmark: performance benchmark tests",
]
```

### 6.2 CI Workflow Commands

```bash
# Regular tests (benchmarks skipped due to addopts)
pytest

# Benchmark run with save
pytest tests/benchmarks/ --benchmark-only --benchmark-autosave --benchmark-json=benchmark-results.json

# Benchmark with regression detection (after baseline exists)
pytest tests/benchmarks/ --benchmark-only --benchmark-compare=0001 --benchmark-compare-fail=mean:15%
```

### 6.3 GitHub Actions Example

```yaml
- name: Run benchmarks
  run: |
    pytest tests/benchmarks/ \
      --benchmark-only \
      --benchmark-autosave \
      --benchmark-json=benchmark-results.json \
      --benchmark-columns=min,max,mean,stddev,median,rounds

- name: Upload benchmark results
  uses: actions/upload-artifact@v4
  with:
    name: benchmark-results
    path: |
      benchmark-results.json
      .benchmarks/
```

### 6.4 Regression Detection Strategy

1. **Phase 1** (initial): Run benchmarks, save baseline. No failure thresholds.
2. **Phase 2** (stable): Enable `--benchmark-compare-fail=mean:15%`. Compare against last green baseline.
3. **Phase 3** (strict): Tighten to `mean:10%`. Store baselines in git `.benchmarks/` directory.

Consider absolute thresholds for NFR targets:
```bash
# Fail if event emission mean > 0.001s (1ms)
--benchmark-compare-fail=mean:0.001
```

## 7. NFR-Specific Test Patterns

### 7.1 NFR-001: Event Emission <1ms (No Handler)

```python
@pytest.mark.benchmark(group="event-emission", disable_gc=True, warmup=True)
def test_nfr001_emit_no_handler(benchmark):
    """NFR-001: <1ms per event point when no handler."""
    event = PipelineStarted(run_id="r", pipeline_name="p")
    # Simulate pipeline with no emitter
    emitter = None

    def emit_once():
        if emitter is not None:
            emitter.emit(event)

    result = benchmark.pedantic(emit_once, iterations=10000, rounds=100)
    # Assert via stats
    assert benchmark.stats.stats.mean < 0.001  # <1ms mean
```

### 7.2 NFR-004: Run List <200ms (10k+ Runs)

```python
@pytest.mark.benchmark(group="api-response")
def test_nfr004_run_list_10k(benchmark, large_db_client):
    """NFR-004: <200ms for paginated run list with 10k+ runs."""
    def fetch():
        return large_db_client.get("/api/runs?offset=0&limit=50")

    response = benchmark(fetch)
    assert response.status_code == 200
    assert response.json()["total"] >= 10_000
    assert benchmark.stats.stats.mean < 0.200  # <200ms
```

### 7.3 NFR-005: Step Detail <100ms

```python
@pytest.mark.benchmark(group="api-response")
def test_nfr005_step_detail(benchmark, large_db_client):
    """NFR-005: <100ms for step detail."""
    run_id = "bench-00000-0000-0000-000000000000"

    def fetch():
        return large_db_client.get(f"/api/runs/{run_id}/steps/1")

    response = benchmark(fetch)
    assert response.status_code == 200
    assert benchmark.stats.stats.mean < 0.100  # <100ms
```

## 8. Dependency Addition

Add to `pyproject.toml` `[project.optional-dependencies].dev`:
```
"pytest-benchmark>=4.0",
```

Current version: pytest-benchmark 5.2.3 (Nov 2025). Requires pytest>=3.8.

## 9. Key Recommendations

1. **Use pedantic mode** for sub-ms event emission benchmarks -- auto-calibration introduces noise at this scale.
2. **Module-scoped fixtures** for large_db -- 10k row insert takes ~1-2s, unacceptable per-test.
3. **`--benchmark-skip` in addopts** -- benchmarks should not run in normal `pytest` invocations.
4. **Separate NFR groups** -- event-emission, api-response, event-construction for clear reporting.
5. **Pre-create events** outside benchmark loops when measuring pure emit overhead.
6. **StaticPool + shared-cache** for in-memory SQLite (matches existing test patterns).
7. **Start with `mean:15%` regression threshold**, tighten after baseline stabilizes.
8. **No async benchmarking needed** -- all current code paths are synchronous.
9. **SQLAlchemy Core insert** for maximum fixture population speed at 10k+ scale.
10. **memory_profiler and line_profiler** as diagnostic tools, not in CI benchmark suite.
