# IMPLEMENTATION - STEP 4: EVENT-BENCHMARKS
**Status:** completed

## Summary
Implemented NFR-001 event emission overhead benchmarks in tests/benchmarks/test_event_overhead.py. Three benchmark scenarios: no handler (primary NFR target), LoggingEventHandler, and InMemoryEventHandler. All use benchmark.pedantic() with warmup_rounds=10, rounds=100, iterations=1000. No-handler case measured at ~167ns mean, far under 1ms NFR-001 target.

## Files
**Created:** tests/benchmarks/test_event_overhead.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/benchmarks/test_event_overhead.py`
New file with three benchmark tests and supporting fixtures.

- `BenchmarkRegistry`, `BenchmarkStrategies`, `BenchmarkPipeline` -- minimal concrete subclasses satisfying PipelineConfig ABC naming conventions
- `benchmark_engine` (module-scoped) -- in-memory SQLite with StaticPool
- `minimal_pipeline` -- BenchmarkPipeline with event_emitter=None
- `pipeline_with_logging` -- BenchmarkPipeline with LoggingEventHandler via CompositeEmitter
- `pipeline_with_inmemory` -- BenchmarkPipeline with InMemoryEventHandler via CompositeEmitter
- `_make_event()` helper -- creates PipelineStarted for consistent benchmark input
- `test_emit_no_handler` -- primary NFR-001 benchmark, asserts mean < 1ms
- `test_emit_with_logging_handler` -- supplementary, tracks regression
- `test_emit_with_inmemory_handler` -- supplementary, tracks regression
- All tests marked with `@pytest.mark.benchmark_group("NFR-001")`

## Decisions
### Self-contained fixtures vs conftest.py dependency
**Choice:** Defined fixtures locally in test file since conftest.py (step 3) not yet available
**Rationale:** Step 3 creates conftest.py concurrently. Local fixtures avoid blocking. When conftest.py lands, these can be refactored to use shared fixtures (benchmark_engine, minimal_pipeline).

### PipelineStarted as benchmark event
**Choice:** Use PipelineStarted for all benchmarks
**Rationale:** Simplest event type (no extra fields beyond base PipelineEvent), consistent measurement across all three scenarios. Per plan specification.

### Assertion on benchmark.stats.stats.mean
**Choice:** Assert mean < 1e-3 in no-handler test only
**Rationale:** NFR-001 target applies to no-handler case. Handler cases are supplementary regression trackers without hard targets.

## Verification
[x] pytest --benchmark-only runs all 3 benchmarks successfully
[x] test_emit_no_handler mean ~167ns, well under 1ms NFR-001 target
[x] pytest (normal) skips all benchmarks via --benchmark-skip
[x] All tests marked with @pytest.mark.benchmark_group("NFR-001")
[x] Uses benchmark.pedantic(warmup_rounds=10, rounds=100, iterations=1000)
