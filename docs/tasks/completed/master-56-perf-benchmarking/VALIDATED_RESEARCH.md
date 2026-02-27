# Research Summary

## Executive Summary

Validated 3 research documents (step-1-perf-patterns, step-2-pytest-bench, step-3-api-bench) against actual codebase. All line references, index definitions, and architectural claims confirmed accurate. Found 3 factual errors in code examples, 1 cross-document contradiction (now resolved by CEO decision), and 2 significant gaps requiring planning attention. CEO decisions incorporated: benchmarks target direct SQLModel queries (no TestClient), standardize on pytest-benchmark, use CREATE INDEX IF NOT EXISTS for schema changes.

## Domain Findings

### Event Emission Architecture
**Source:** step-1-perf-patterns.md

- `_emit()` at pipeline.py L231-238 confirmed: single `is not None` guard, no event construction when emitter absent. All 6+ emit sites (L518, L528, L557, L568, L596, L611) verified to guard BEFORE event object creation. NFR-001 (<1ms no-handler) expected to pass trivially (~10-50ns overhead).
- 3 handler types confirmed: LoggingEventHandler (event.to_dict() + log), InMemoryEventHandler (event.to_dict() + list append with Lock), SQLiteEventHandler (session-per-emit with COMMIT per call).
- Event dataclass uses `@dataclass(frozen=True, slots=True)` with `default_factory=utc_now` (~1us per construction). Confirmed at events/types.py.
- 15-30+ events per 3-step pipeline run estimate is reasonable based on emit site count.

### SQLiteEventHandler Session-Per-Emit Anti-Pattern
**Source:** step-1-perf-patterns.md

- handlers.py L190-206 confirmed: `Session(self._engine)` created per emit, `session.commit()` per emit, `session.close()` in finally. Each COMMIT triggers fsync. Research correctly identifies this as the most expensive handler and a batching optimization candidate.
- This is a write-path concern only; not in API read-path benchmarks.

### N+1 Query in Cache Reconstruction
**Source:** step-1-perf-patterns.md

- pipeline.py L937-969 confirmed: `self.session.get(model_class, run_instance.model_id)` called per instance in a loop. Classic N+1. Fix: batch `IN()` query.
- Not in API read path (pipeline execution only). Out of scope for NFR-004/005 but valid optimization candidate.

### Prompt Auto-Discovery (Uncached)
**Source:** step-1-perf-patterns.md

- strategy.py L68-113 confirmed: up to 4 SELECT queries per step (strategy system, strategy user, step system, step user). NOT cached across steps or runs.
- Pipeline execution concern only. Not in API read path.

### Index Coverage Analysis
**Source:** step-1-perf-patterns.md, step-3-api-bench.md

All existing indexes verified against state.py and events/models.py:
- PipelineRun: ix_pipeline_runs_name_started(pipeline_name, started_at), ix_pipeline_runs_status(status), unique(run_id)
- PipelineStepState: ix_pipeline_step_states_run(run_id, step_number), ix_pipeline_step_states_cache(pipeline_name, step_name, input_hash)
- PipelineEventRecord: ix_pipeline_events_run_event(run_id, event_type), ix_pipeline_events_type(event_type), ix_pipeline_events_run_step(run_id, step_name)
- PipelineRunInstance: ix_pipeline_run_instances_run(run_id), ix_pipeline_run_instances_model(model_type, model_id)

**Gap confirmed:** No standalone `started_at` index on PipelineRun. The composite ix_pipeline_runs_name_started cannot be used for `ORDER BY started_at DESC` without a `pipeline_name` WHERE clause. Unfiltered `list_runs` (runs.py L124) does `.order_by(PipelineRun.started_at.desc())` -- confirmed full table scan + filesort at 10k rows.

**Gap confirmed:** Standalone ix_pipeline_runs_status(status) lacks ordering column. Status-filtered queries must filesort for ORDER BY started_at DESC.

### Offset Pagination Risk
**Source:** step-1-perf-patterns.md, step-3-api-bench.md

runs.py L125-126 confirmed: `.offset(params.offset).limit(params.limit)`. OFFSET is O(offset) but research overstates the impact when a suitable index exists (index walk is cheaper than table scan + sort). With proposed started_at index, SQLite can walk the B-tree in reverse and skip to offset position. Still O(offset) but much faster constant factor. Keyset pagination is a valid fallback if benchmarks show high-offset degradation.

### pytest-benchmark Patterns
**Source:** step-2-pytest-bench.md

Core patterns validated: pedantic mode for sub-ms benchmarks, parametrize for scaling tests, group markers for NFR separation, module-scoped fixtures for large_db. CI integration approach (--benchmark-skip in addopts, --benchmark-only for CI runs, --benchmark-compare-fail for regression) is sound.

### Direct Library Benchmarking (CEO Decision)
**Source:** CEO answer to Q1, replacing TestClient approach from step-2/step-3

NFR-004/005 benchmarks must execute the same SQLModel queries that route handlers use, but directly against a Session. This means:
- Benchmark the `select(PipelineRun)...order_by(...).offset(...).limit(...)` + `select(func.count())` pattern from runs.py L114-128
- Benchmark `select(PipelineStepState).where(run_id=..., step_number=...)` pattern from steps.py L97-104
- Use `Session(engine)` or `ReadOnlySession(Session(engine))` directly
- No FastAPI/Pydantic serialization overhead in the measurement
- This isolates pure library/DB performance from web framework overhead

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| NFR-004/005 benchmarks: TestClient (full HTTP) or direct SQLModel queries? | Direct library calls only. Benchmark SQLModel queries directly. No TestClient. | Invalidates all TestClient-based benchmark code in step-2/step-3. Benchmarks must use Session directly. Pydantic serialization overhead excluded from NFR budget. Simplifies fixtures (no FastAPI app needed). |
| Benchmark tool: pytest-benchmark or manual time.perf_counter()? | pytest-benchmark. Standardize for statistical rigor, CI regression detection, auto-calibration, warmup. | Resolves contradiction between step-2 (pytest-benchmark) and step-3 (manual timing). All benchmark code uses pytest-benchmark. Step-3 section 6.1 manual _measure() helper is superseded. |
| Index migration: CREATE INDEX IF NOT EXISTS or Alembic? | CREATE INDEX IF NOT EXISTS. Matches existing SQLiteEventHandler pattern. | No new migration framework. New indexes added via same pattern as handlers.py L175-188. Applied during init_pipeline_db or similar startup path. |

## Assumptions Validated
- [x] _emit() with no handler is a single `is not None` check with no event construction (confirmed pipeline.py L518-617 all guard before creation)
- [x] Event dataclass uses frozen=True, slots=True with utc_now default_factory (confirmed events/types.py)
- [x] SQLiteEventHandler creates session + commit per emit call (confirmed handlers.py L190-206)
- [x] N+1 exists in _reconstruct_extractions_from_cache via session.get per instance (confirmed pipeline.py L937-969)
- [x] Prompt auto-discovery issues up to 4 uncached SELECTs per step (confirmed strategy.py L68-113)
- [x] All index definitions match codebase exactly (confirmed state.py L100-103, L138-141, L175-178; events/models.py L57-61)
- [x] Unfiltered list_runs orders by started_at DESC without a suitable standalone index (confirmed runs.py L124, state.py L175-178)
- [x] PipelineStepState indexes adequate for NFR-005 step detail queries (confirmed ix_pipeline_step_states_run covers run_id + step_number)
- [x] All API endpoints are sync def (confirmed runs.py L108, steps.py L66/L92, events.py L67)
- [x] Existing test patterns use StaticPool + in-memory SQLite (confirmed tests/ui/conftest.py)
- [x] 15-30+ events per 3-step pipeline run (confirmed by counting emit sites in pipeline.py)

## Open Items
- Step-2 code example error: `@pytest.mark.benchmark(disable_gc=True, warmup=True)` -- disable_gc and warmup are NOT valid pytest.mark.benchmark parameters. Valid mark params are: group, min_rounds, min_time, timer. GC disabling is via `--benchmark-disable-gc` CLI flag; warmup is via `benchmark.pedantic(warmup_rounds=N)`. Planning must use correct API.
- Step-2 config error: `addopts_benchmarks` in pyproject.toml is not a valid pytest config key. Should be `addopts`.
- Step-2 stats access: `benchmark.stats.stats.mean` may be incorrect API path. Verify against pytest-benchmark 4.x+ docs during implementation. The `benchmark.stats` is a `BenchmarkStats` object; `.stats` sub-attribute access pattern needs confirmation.
- PipelineConfig ABC requirement for event emission benchmarks: Creating a real PipelineConfig instance requires REGISTRY, STRATEGIES, engine, LLMProvider. Research proposes MinimalPipeline workaround. Planning must decide: test actual PipelineConfig._emit() (requires full fixture setup) or test the isolated if-check pattern (simpler but not the real code path). The overhead difference is negligible but the benchmark should ideally test the actual class.
- Benchmark fixture JSON payload size: step-3 recommends 1-5KB result_data/context_snapshot per step for realistic benchmarks. Current fixture examples use tiny dicts ({"v": i}). Planning should specify realistic payload sizes. (Note: since CEO decided no TestClient, JSON deserialization of these payloads still matters for SQLModel object hydration from the DB.)
- Pydantic v2 model_validate overhead: Research doesn't discuss Pydantic serialization cost. With direct library calls (no response_model), this is less relevant, but if the planning phase includes any response construction benchmarks, Pydantic overhead should be considered.
- Windows timing: Project developed on Windows 11. time.perf_counter uses QueryPerformanceCounter -- high resolution, no issues expected. Worth noting for CI portability if CI runs on Linux.

## Recommendations for Planning
1. Standardize ALL benchmarks on pytest-benchmark with pedantic mode for sub-ms tests (per CEO decision). Remove all manual `_measure()` / `time.perf_counter()` patterns from step-3.
2. NFR-004/005 benchmarks must execute direct SQLModel queries against Session, NOT through TestClient (per CEO decision). Benchmark functions should replicate the query logic from runs.py and steps.py route handlers but use a plain Session/ReadOnlySession.
3. Add standalone `Index("ix_pipeline_runs_started", "started_at")` and replace `Index("ix_pipeline_runs_status", "status")` with `Index("ix_pipeline_runs_status_started", "status", "started_at")` using CREATE INDEX IF NOT EXISTS pattern (per CEO decision).
4. Fix incorrect pytest-benchmark mark params in benchmark code examples: use `--benchmark-disable-gc` CLI flag or `benchmark.pedantic(warmup_rounds=N)` instead of mark parameters.
5. Module-scoped fixtures for 10k-row seeding are correct. Use `session.add_all()` for bulk insert, run `ANALYZE` after insert. Consider SQLAlchemy Core `insert().values()` if ORM add_all is too slow.
6. Event emission benchmarks should test actual `PipelineConfig._emit()` if feasible, with a minimal concrete subclass that satisfies ABC requirements. If too complex, the MinimalPipeline approach is acceptable but must be documented as a simplification.
7. Defer keyset pagination, column projection, and triple-filter covering index unless benchmarks show NFR failures at current scale.
8. Benchmark directory structure: `tests/benchmarks/conftest.py` (shared fixtures), `test_event_overhead.py` (NFR-001), `test_query_response.py` (NFR-004/005 direct queries).
9. CI regression detection: Start with `--benchmark-compare-fail=mean:15%`, tighten to 10% once baseline stabilizes. Use `--benchmark-skip` in default addopts so normal `pytest` runs skip benchmarks.
10. Step-3 section 7.4 PRAGMA optimizations (synchronous=NORMAL, cache_size, mmap_size) are appropriate for benchmark fixtures but NOT production code. Planning should include these in benchmark conftest only.
