# IMPLEMENTATION
**Status:** completed

## Summary
Created `tests/ui/test_integration.py` with 19 tests across 5 classes covering the 5 genuine integration gaps. All 19 pass in isolation and in the full suite (729 passed, 1 pre-existing failure in test_ui.py::TestRoutersIncluded::test_events_router_prefix -- out of scope).

## Files
**Created:** `tests/ui/test_integration.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/ui/test_integration.py`
New file. 5 test classes:
- `TestE2ETriggerWebSocket` (3 tests) -- GAP 1/4
- `TestTriggerRunErrorHandling` (3 tests) -- GAP 3
- `TestCombinedFilters` (6 tests) -- GAP 6
- `TestCORSHeaders` (4 tests) -- GAP 7
- `TestWebSocketDisconnect` (3 tests) -- GAP 5

Module-level helpers:
- `_clean_manager` autouse fixture (same as test_websocket.py)
- `_wait_for_connection()` helper (same as test_websocket.py)
- `_make_no_op_factory()` -- background task factory that inserts PipelineRun row and blocks on a threading.Event gate
- `_make_emitting_pipeline_factory()` -- kept as documented helper (not used in final tests; emission driven manually via UIBridge)
- `_make_failing_pipeline_factory()` -- execute() raises RuntimeError after inserting row

## Decisions

### GAP 1 race elimination via gate pattern
**Choice:** No-op factory with `threading.Event` gate injected on `app.state.engine._test_gate`. Background task blocks until gate is set. WS connects, `_wait_for_connection` confirms registration, then `UIBridge.emit()` is called directly before gate is released.
**Rationale:** The emitting factory caused a race: background task could emit before the WS thread connected. The gate pattern eliminates the race deterministically without mocking UIBridge or ConnectionManager. UIBridge.emit() -> ConnectionManager.broadcast_to_run() path is still exercised end-to-end.

### No-op vs emitting factory for background task
**Choice:** Use no-op factory (blocks on gate) for E2E tests; UIBridge emission driven manually in test body.
**Rationale:** Decouples run_id acquisition (POST /api/runs) from event emission timing. Manual emission after `_wait_for_connection` guarantees WS is registered before events are enqueued.

### _make_emitting_pipeline_factory retained
**Choice:** Keep helper in module even though not directly used in final E2E tests.
**Rationale:** Documents the intended full-integration pattern. Available for future tests that don't need gate-based timing control.

### TestClient context manager for background task flushing
**Choice:** `with client:` block wraps all test logic. Gate is set before exiting the `with` block so TestClient can flush the background task cleanly.
**Rationale:** TestClient flushes background tasks on `__exit__`. Setting gate before exit avoids deadlock where TestClient waits for background task that is blocked on gate.

## Verification
- [x] `pytest tests/ui/test_integration.py` -- 19 passed
- [x] `pytest --tb=no -q` -- 729 passed, 1 pre-existing failure (test_events_router_prefix, out of scope)
- [x] GAP 1 covered: POST /api/runs -> UIBridge.emit() -> ConnectionManager -> WS receives pipeline_started + pipeline_completed + stream_complete
- [x] GAP 3 covered: failing execute() -> runs.py except block -> DB status=failed + completed_at set
- [x] GAP 5 covered: WS context exit -> WebSocketDisconnect -> manager.disconnect() -> _queues and _connections cleaned
- [x] GAP 6 covered: pipeline_name+status, pipeline_name+started_after, event_type+pagination combos
- [x] GAP 7 covered: access-control-allow-origin on GET response; access-control-allow-origin + access-control-allow-methods on OPTIONS preflight
- [x] No source files under llm_pipeline/ modified
- [x] No new test dependencies added
