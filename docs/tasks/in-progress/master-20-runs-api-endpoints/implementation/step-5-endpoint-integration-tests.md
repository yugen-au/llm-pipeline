# IMPLEMENTATION - STEP 5: ENDPOINT + INTEGRATION TESTS
**Status:** completed

## Summary

Created 5 test files covering all 3 /runs API endpoints, WAL mode verification, and PipelineRun write integration tests. 31 new tests, all passing. Full suite 511 → 542 (+31).

## Files

**Created:**
- `tests/ui/__init__.py`
- `tests/ui/conftest.py`
- `tests/ui/test_runs.py`
- `tests/ui/test_wal.py`
- `tests/test_pipeline_run_tracking.py`

**Modified:** none
**Deleted:** none

## Changes

### File: `tests/ui/__init__.py`
Empty package marker.

### File: `tests/ui/conftest.py`
Two fixtures:
- `app_client`: builds app with StaticPool in-memory engine via `_make_app()`, yields TestClient
- `seeded_app_client`: same, inserts 3 PipelineRun rows + 3 PipelineStepState rows via direct Session

`_make_app()` constructs the app manually (bypassing `create_app(db_path=":memory:")`) using `StaticPool` so all connections (main thread + threadpool workers) share one in-memory SQLite instance. `create_app(db_path=":memory:")` would produce `sqlite:////:memory:` (file named `:memory:`), causing `no such table` errors from threadpool connections.

### File: `tests/ui/test_runs.py`
Three test classes:

**TestListRuns** (12 tests):
- empty 200, all runs, total count, pipeline_name filter, status filter, started_after/started_before filters, pagination (offset+limit), limit>200 → 422, negative offset → 422, desc ordering, response schema fields

**TestGetRun** (6 tests):
- 200 with fields and steps, steps asc by step_number, step fields present, 404 unknown run_id, null completed_at/total_time_ms for running status, empty steps list for run with no steps

**TestTriggerRun** (5 tests):
- 202 + accepted + valid UUID, run_id is valid UUID format, 404 unregistered pipeline, 404 empty registry, background task executes pipeline (verified via TestClient context exit)

### File: `tests/ui/test_wal.py`
**TestWALMode** (4 tests):
- File-based SQLite gets WAL (PRAGMA journal_mode query verified = "wal")
- :memory: engine does not raise
- Both return the engine passed in

### File: `tests/test_pipeline_run_tracking.py`
**TestPipelineRunTracking** (4 tests):
- Successful execute writes completed PipelineRun with all fields populated
- Failed execute (BrokenStep raises RuntimeError) writes failed PipelineRun with completed_at
- Pre-generated run_id passed to constructor is preserved in DB row
- Completed run has correct pipeline_name

## Decisions

### StaticPool for in-memory engine
**Choice:** Use `sqlalchemy.pool.StaticPool` with `sqlite://` (not `create_app(db_path=":memory:")`)
**Rationale:** FastAPI wraps sync handlers in threadpool. Each threadpool thread gets its own connection. Without StaticPool, each connection gets a blank in-memory DB, causing `no such table`. StaticPool forces all connections to reuse one underlying connection, so the seeded tables are visible to all threads.

### BrokenStrategy passed as instance at init
**Choice:** `TrackingPipeline(strategies=[BrokenStrategy()], ...)` rather than a separate `FailingTrackingPipeline` class
**Rationale:** PipelineConfig enforces `{PipelineName}Registry` and `{PipelineName}Strategies` naming conventions at class definition time. A second pipeline class (`FailingTrackingPipeline`) would need `FailingTrackingRegistry` and `FailingTrackingStrategies`. The `strategies=` init param allows overriding the class-level strategies, avoiding redundant class definitions.

### BrokenInstructions separate class
**Choice:** Define `BrokenInstructions(LLMResultMixin)` for `BrokenStep`
**Rationale:** `step_definition` decorator validates that the instructions class name matches the step class name (`BrokenStep` → `BrokenInstructions`). Reusing `GadgetInstructions` raises `ValueError` at collection time.

## Verification

- [x] 31 new tests collected and passing
- [x] Full suite: 542 passed (511 baseline + 31 new), 0 regressions
- [x] TestListRuns: all 12 cases including filter, pagination, validation
- [x] TestGetRun: all 6 cases including 404, null fields for running status
- [x] TestTriggerRun: all 5 cases including background task execution verification
- [x] TestWALMode: WAL verified via PRAGMA query on file-based engine
- [x] TestPipelineRunTracking: completed/failed/run_id preservation/pipeline_name all verified
