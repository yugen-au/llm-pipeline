# PLANNING

## Summary
Add pytest-benchmark test suite to measure event emission overhead and database query performance against NFR targets (<1ms event emission, <200ms run listing, <100ms step detail at 10k+ scale). Create tests/benchmarks/ with direct SQLModel query benchmarks (no TestClient). Add missing composite indexes to PipelineRun table (standalone started_at index, composite status+started_at index) using CREATE INDEX IF NOT EXISTS pattern matching SQLiteEventHandler approach.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** python-dev
**Skills:** none

## Phases
1. **Dependencies** - Add pytest-benchmark to pyproject.toml dev dependencies
2. **Indexes** - Add missing database indexes to improve query performance
3. **Benchmark Infrastructure** - Create tests/benchmarks/ with conftest.py for shared fixtures and configuration
4. **Event Benchmarks** - Implement NFR-001 benchmarks for event emission overhead
5. **Query Benchmarks** - Implement NFR-004/005 benchmarks for database query performance

## Architecture Decisions

### Benchmark Tool: pytest-benchmark
**Choice:** Use pytest-benchmark for all performance tests
**Rationale:** Standardized statistical rigor with auto-calibration, warmup rounds, CI regression detection via --benchmark-compare-fail. Resolves contradiction in research between manual perf_counter and pytest-benchmark. CEO decision confirmed.
**Alternatives:** Manual time.perf_counter() (rejected - no statistical analysis, no CI integration)

### Benchmark Target: Direct Library Calls
**Choice:** Benchmark SQLModel queries directly via Session, not through FastAPI TestClient
**Rationale:** CEO decision to isolate pure library/DB performance from web framework overhead. NFR-004/005 measure database query time only, excluding Pydantic serialization and HTTP stack. Simplifies fixtures (no FastAPI app needed).
**Alternatives:** TestClient end-to-end (rejected - includes HTTP + Pydantic overhead not in NFR scope)

### Index Migration: CREATE INDEX IF NOT EXISTS
**Choice:** Add indexes via CREATE INDEX IF NOT EXISTS in db.py helper function called from init_pipeline_db
**Rationale:** Matches existing SQLiteEventHandler pattern (handlers.py L175-188). SQLModel.metadata.create_all skips indexes on existing tables. CEO decision confirmed. No new migration framework.
**Alternatives:** Alembic migrations (rejected - introduces new dependency), declarative __table_args__ only (rejected - doesn't apply to existing DBs)

### Missing Indexes
**Choice:** Add standalone ix_pipeline_runs_started(started_at) and replace ix_pipeline_runs_status with composite ix_pipeline_runs_status_started(status, started_at)
**Rationale:** Research confirmed unfiltered list_runs (runs.py L124) does ORDER BY started_at DESC without suitable index, causing full table scan + filesort at 10k rows. Status-filtered queries also need ordering column for efficient status+time queries. Composite index supports both status filter and ORDER BY started_at in single index.
**Alternatives:** Keyset pagination (defer unless benchmarks fail), covering index with all columns (over-indexing for current query patterns)

### Benchmark Directory Structure
**Choice:** tests/benchmarks/ with test_event_overhead.py (NFR-001) + test_query_response.py (NFR-004/005) + conftest.py (shared fixtures)
**Rationale:** Separates event emission concerns from DB query concerns, allows different fixture setups (event tests need minimal data, query tests need 10k rows), better maintainability. Confirmed by VALIDATED_RESEARCH recommendation 8.
**Alternatives:** Single test_benchmarks.py (rejected - mixes concerns, fixture complexity), per-NFR files (rejected - over-granular for 3 NFRs)

### Event Emission Fixture: MinimalPipeline
**Choice:** Create MinimalPipeline concrete subclass with empty REGISTRY={}, STRATEGIES=[], mock LLMProvider to test actual PipelineConfig._emit()
**Rationale:** Tests real _emit() method execution path (not isolated pattern simulation). Overhead measured (None check + optional event construction) is identical to production. Minimal fixture complexity (no real LLM provider needed).
**Alternatives:** Test isolated if-check pattern (simpler but not real code path), use existing test pipeline (more complex fixture setup)

### Large DB Fixture Strategy
**Choice:** Module-scoped large_db_session seeding 10k PipelineRun + 30k PipelineStepState (3 steps per run avg) using session.add_all(), run ANALYZE after insert
**Rationale:** Module scope shares expensive setup across all query benchmarks. add_all() is bulk insert optimization. ANALYZE updates SQLite statistics for query planner. 10k+ scale per NFR targets. Realistic 3-step-per-run ratio per research estimate (15-30+ events = ~3 steps).
**Alternatives:** Function-scoped (too slow - re-seeds per test), SQLAlchemy Core insert().values() (overkill unless add_all proves slow)

### pytest-benchmark Configuration
**Choice:** addopts = "--benchmark-skip" in pyproject.toml, CI runs pytest --benchmark-only --benchmark-autosave --benchmark-compare-fail=mean:15%
**Rationale:** Normal pytest runs skip benchmarks for fast feedback. CI explicitly runs benchmarks with autosave for regression tracking. 15% threshold for mean allows natural variance, tighten to 10% after baseline stabilizes. VALIDATED_RESEARCH recommendation 9.
**Alternatives:** Always run benchmarks (too slow for dev workflow), manual benchmark invocation (no regression detection)

### Benchmark Modes
**Choice:** Use benchmark.pedantic() for NFR-001 (<1ms target), standard benchmark() for NFR-004/005 (100-200ms targets)
**Rationale:** Pedantic mode provides warmup rounds and fine-grained control for sub-millisecond measurements. Standard mode sufficient for 100ms+ targets. Research Open Item confirmed: disable_gc via CLI flag --benchmark-disable-gc, not mark parameter.
**Alternatives:** Pedantic for all (unnecessary overhead for 100ms tests), standard for all (less accurate for sub-ms)

### SQLite Optimization Scope
**Choice:** Apply PRAGMA optimizations (synchronous=NORMAL, cache_size=10000, mmap_size=30000000) in benchmark conftest.py ONLY, not production code
**Rationale:** Benchmark fixtures need consistent fast performance. Production code should not change PRAGMA settings (user's responsibility). VALIDATED_RESEARCH recommendation 10.
**Alternatives:** Apply globally (rejected - alters production behavior), no optimizations (slower benchmarks, less consistent)

## Implementation Steps

### Step 1: Add pytest-benchmark Dependency
**Agent:** python-development:python-dev
**Skills:** none
**Context7 Docs:** -
**Group:** A
1. Add "pytest-benchmark>=4.0" to [project.optional-dependencies].dev in pyproject.toml
2. Update [tool.pytest.ini_options] with addopts = "--benchmark-skip" to skip benchmarks in normal pytest runs

### Step 2: Add Database Indexes
**Agent:** python-development:python-dev
**Skills:** none
**Context7 Docs:** /sqlmodel/tiangolo, /sqlalchemy/sqlalchemy
**Group:** A
1. Create add_missing_indexes() helper function in llm_pipeline/db.py
2. Add CREATE INDEX IF NOT EXISTS for ix_pipeline_runs_started on started_at column
3. Add CREATE INDEX IF NOT EXISTS for ix_pipeline_runs_status_started on (status, started_at) composite
4. Call add_missing_indexes(engine) from init_pipeline_db() after create_all()
5. Use same pattern as SQLiteEventHandler (handlers.py L175-188): text() + conn.execute() + conn.commit() in try/except OperationalError

### Step 3: Create Benchmark Infrastructure
**Agent:** python-development:python-dev
**Skills:** none
**Context7 Docs:** /pytest-dev/pytest-benchmark
**Group:** B
1. Create tests/benchmarks/ directory
2. Create tests/benchmarks/__init__.py (empty)
3. Create tests/benchmarks/conftest.py with:
   - benchmark_engine fixture: in-memory SQLite with StaticPool, init_pipeline_db, PRAGMA optimizations (synchronous=NORMAL, cache_size=10000, mmap_size=30000000)
   - minimal_pipeline fixture: MinimalPipeline concrete class with REGISTRY={}, STRATEGIES=[], mock LLMProvider, using benchmark_engine
   - Pytest markers: pytest.mark.benchmark_group for NFR categorization

### Step 4: Implement Event Emission Benchmarks
**Agent:** python-development:python-dev
**Skills:** none
**Context7 Docs:** /pytest-dev/pytest-benchmark
**Group:** B
1. Create tests/benchmarks/test_event_overhead.py
2. Implement test_emit_no_handler: benchmark minimal_pipeline._emit() with emitter=None, verify <1ms using benchmark.pedantic(warmup_rounds=10)
3. Implement test_emit_with_logging_handler: benchmark with LoggingEventHandler, measure event construction + to_dict() + logging overhead
4. Implement test_emit_with_inmemory_handler: benchmark with InMemoryEventHandler, measure event construction + to_dict() + list append + Lock overhead
5. Mark all tests with @pytest.mark.benchmark_group("NFR-001")
6. Use PipelineStarted event for consistent benchmark (frozen dataclass with utc_now default_factory)

### Step 5: Implement Query Benchmarks
**Agent:** python-development:python-dev
**Skills:** none
**Context7 Docs:** /pytest-dev/pytest-benchmark, /sqlmodel/tiangolo
**Group:** C
1. Create tests/benchmarks/test_query_response.py
2. Create large_db_session module-scoped fixture:
   - Seed 10,000 PipelineRun rows with varied status (70% completed, 20% failed, 10% running) and started_at spread over 30 days
   - Seed 30,000 PipelineStepState rows (3 steps per run avg) with realistic result_data/context_snapshot (1-5KB JSON per research)
   - Use session.add_all() for bulk insert
   - Run session.execute(text("ANALYZE")) after commit
3. Implement test_list_runs_unfiltered: benchmark select(PipelineRun).order_by(started_at.desc()).offset(0).limit(20) + select(func.count()), verify <200ms
4. Implement test_list_runs_status_filtered: benchmark same query with .where(status="completed"), verify <200ms
5. Implement test_step_detail: benchmark select(PipelineStepState).where(run_id=X, step_number=Y).first(), verify <100ms
6. Mark all tests with @pytest.mark.benchmark_group("NFR-004") or @pytest.mark.benchmark_group("NFR-005") as appropriate
7. Use standard benchmark() (not pedantic) for 100-200ms targets

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| 10k row fixture generation slow, delays benchmark runs | Medium | Use session.add_all() bulk insert, module-scoped fixture shares setup. If still slow, switch to SQLAlchemy Core insert().values() |
| pytest-benchmark API errors from research (disable_gc mark param, stats.stats.mean path) | Low | Follow pytest-benchmark 4.x+ docs during implementation. Use --benchmark-disable-gc CLI flag, verify stats access pattern |
| MinimalPipeline ABC requirements complex, breaks tests | Medium | Implement minimal concrete members only (empty REGISTRY, STRATEGIES, mock provider). If too complex, fall back to isolated pattern test with documentation note |
| Windows timing resolution issues (perf_counter) | Low | pytest-benchmark handles platform differences. Project already on Windows 11 with QueryPerformanceCounter support |
| Benchmarks fail NFR targets with new indexes | High | Indexes designed per query analysis. If failures occur, fallback to keyset pagination, column projection, or covering index per VALIDATED_RESEARCH deferred optimizations |
| CI regression detection too sensitive (15% threshold) | Low | Start at 15%, tighten to 10% after baseline stabilizes. Use --benchmark-compare-fail only in CI, not local dev |

## Success Criteria
- [ ] pytest-benchmark added to dev dependencies
- [ ] ix_pipeline_runs_started index created on started_at column
- [ ] ix_pipeline_runs_status_started composite index created on (status, started_at)
- [ ] add_missing_indexes() applied during init_pipeline_db()
- [ ] tests/benchmarks/conftest.py created with benchmark_engine, minimal_pipeline, markers
- [ ] test_event_overhead.py benchmarks NFR-001 event emission <1ms (no handler case)
- [ ] test_query_response.py benchmarks NFR-004 list_runs <200ms at 10k rows
- [ ] test_query_response.py benchmarks NFR-005 step_detail <100ms
- [ ] pytest --benchmark-only runs successfully with all benchmarks passing
- [ ] pytest (normal) skips benchmarks via --benchmark-skip
- [ ] All benchmarks meet NFR targets at 10k+ scale

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Well-defined scope (3 benchmark files, 2 index additions, 1 config change). CEO decisions resolve all ambiguities. Research validated against codebase. No architectural changes, only additive (new tests + indexes). Existing test patterns provide clear templates (StaticPool + in-memory SQLite from tests/ui/conftest.py). Low risk of breaking changes.
**Suggested Exclusions:** testing, review
