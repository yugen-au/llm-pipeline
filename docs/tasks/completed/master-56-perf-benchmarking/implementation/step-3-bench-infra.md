# IMPLEMENTATION - STEP 3: BENCH-INFRA
**Status:** completed

## Summary
Created benchmark test infrastructure in tests/benchmarks/ with shared fixtures (benchmark_engine, minimal_pipeline) and custom pytest marker (benchmark_group) for NFR categorization.

## Files
**Created:** tests/benchmarks/__init__.py, tests/benchmarks/conftest.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/benchmarks/__init__.py`
Empty package marker for benchmark test directory.

### File: `tests/benchmarks/conftest.py`
Shared benchmark fixtures and configuration:

```
# Key components:

# 1. pytest_configure -- registers benchmark_group marker
# 2. _BenchmarkMockProvider -- minimal LLMProvider (raises NotImplementedError)
# 3. MinimalRegistry / _MinimalStrategy / MinimalStrategies / MinimalPipeline
#    -- concrete PipelineConfig subclass with empty registry/strategies
# 4. benchmark_engine (module-scoped) -- in-memory SQLite + StaticPool + PRAGMAs
# 5. minimal_pipeline (function-scoped) -- MinimalPipeline instance per test
```

## Decisions
### MinimalPipeline naming pattern
**Choice:** Follow existing PipelineConfig naming convention (MinimalPipeline + MinimalRegistry + MinimalStrategies)
**Rationale:** PipelineConfig.__init_subclass__ enforces prefix matching. Used _MinimalStrategy (underscore prefix) to bypass PipelineStrategy naming validation since it's internal.

### Mock provider approach
**Choice:** _BenchmarkMockProvider that raises NotImplementedError vs unittest.mock.MagicMock
**Rationale:** Explicit failure if accidentally called during benchmarks. MagicMock silently succeeds which could mask issues. Matches the explicit-is-better-than-implicit principle.

### Strategy with empty get_steps
**Choice:** _MinimalStrategy returns empty get_steps() list, passed via MinimalStrategies class
**Rationale:** PipelineConfig validates REGISTRY and STRATEGIES are not None. Using a real strategy class with empty steps satisfies both class-level and constructor-level validation without needing to pass strategies=[] to bypass.

### mmap_size PRAGMA on in-memory DB
**Choice:** Keep PRAGMA mmap_size=30000000 in fixture even though it has no effect on :memory:
**Rationale:** Matches PLAN spec exactly. When benchmark_engine is reused for step 5 query benchmarks (if using file-backed SQLite for larger datasets), the PRAGMA would apply. No harm on :memory:.

## Verification
[x] tests/benchmarks/__init__.py created (empty)
[x] tests/benchmarks/conftest.py created with benchmark_engine, minimal_pipeline, benchmark_group marker
[x] benchmark_engine uses StaticPool + in-memory SQLite + PRAGMA optimizations
[x] minimal_pipeline uses MinimalPipeline concrete subclass with mock provider
[x] pytest.mark.benchmark_group marker registered in pytest_configure
[x] pytest --benchmark-only runs benchmarks successfully
[x] pytest (normal) skips benchmarks via --benchmark-skip (3 skipped)
[x] Full test suite passes (803 passed, 1 pre-existing failure in test_ui.py unrelated)
