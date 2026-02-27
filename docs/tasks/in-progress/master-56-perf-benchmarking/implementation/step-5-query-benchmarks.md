# IMPLEMENTATION - STEP 5: QUERY-BENCHMARKS
**Status:** completed

## Summary
Created NFR-004/005 database query benchmarks in tests/benchmarks/test_query_response.py. Module-scoped large_db_session fixture seeds 10k PipelineRun + ~30k PipelineStepState rows with realistic data. Three benchmark tests verify query performance against NFR targets at scale.

## Files
**Created:** tests/benchmarks/test_query_response.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/benchmarks/test_query_response.py`
New file with:
- `large_db_session` module-scoped fixture: seeds 10k runs (70% completed, 20% failed, 10% running) with started_at spread over 30 days, ~30k step states (1-5 steps per run, avg 3) with 1-5KB JSON blobs for result_data/context_snapshot. Bulk inserts via add_all() in 2000-row batches, ANALYZE after commit.
- `test_list_runs_unfiltered`: benchmarks paginated SELECT + COUNT, asserts mean <200ms (actual: ~704us)
- `test_list_runs_status_filtered`: benchmarks status-filtered paginated SELECT + COUNT using composite index, asserts mean <200ms (actual: ~1.2ms)
- `test_step_detail`: benchmarks single step lookup by run_id + step_number, asserts mean <100ms (actual: ~330us)

## Decisions
### Batch size for bulk insert
**Choice:** 2000 rows per add_all() batch
**Rationale:** Balances memory usage vs insert speed. 10k runs + 30k steps inserted in ~26s total (including benchmark execution).

### Random seed for reproducibility
**Choice:** random.seed(42) in fixture
**Rationale:** Ensures consistent status distribution and data sizes across runs for comparable benchmarks.

### Standard benchmark() mode
**Choice:** Use standard benchmark() not pedantic() for all query tests
**Rationale:** Per plan -- 100-200ms targets don't need sub-ms precision of pedantic mode. Standard mode provides sufficient statistical rigor with auto-calibration.

## Verification
[x] All 3 benchmarks pass with --benchmark-only
[x] All benchmarks skipped during normal pytest (--benchmark-skip in addopts)
[x] NFR-004 unfiltered: mean 704us < 200ms target
[x] NFR-004 filtered: mean 1.2ms < 200ms target
[x] NFR-005 step detail: mean 330us < 100ms target
[x] 10k PipelineRun rows seeded with correct status distribution
[x] ~30k PipelineStepState rows seeded with realistic JSON payloads
