# IMPLEMENTATION - STEP 2: WEBSOCKET TESTS
**Status:** completed

## Summary
Created `tests/ui/test_websocket.py` with 6 test cases covering all WebSocket connection lifecycle paths: batch replay for completed/failed runs, not-found handling, live event streaming, multi-client fan-out, and heartbeat.

## Files
**Created:** `tests/ui/test_websocket.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/ui/test_websocket.py`
New test file with 6 tests across 4 classes.

```
# Before
(file did not exist)

# After
- _wait_for_connection() helper: spins on manager._queues until N clients registered (fixes race between TestClient thread and broadcast calls)
- _clean_manager autouse fixture: clears manager._connections/_queues before and after each test
- TestBatchReplay: test_batch_replay_completed_run, test_batch_replay_failed_run_empty
- TestNotFound: test_run_not_found
- TestLiveStream: test_live_stream_events, test_live_stream_multiple_clients
- TestHeartbeat: test_heartbeat (monkeypatches HEARTBEAT_INTERVAL_S to 0.01)
```

## Decisions

### Race condition: broadcast before queue registered
**Choice:** Added `_wait_for_connection(run_id, count)` helper that polls `manager._queues` with 5ms sleep until the ASGI handler thread has called `manager.connect()`.
**Rationale:** TestClient runs the ASGI app in a background thread. `manager.connect()` is called inside the async handler after `await websocket.accept()`. Without synchronization, `broadcast_to_run` was called before the queue existed, resulting in a missed event and the test seeing only a heartbeat (after the 30s timeout).

### Heartbeat test ordering
**Choice:** `receive_json()` is called before `signal_run_complete` - with `HEARTBEAT_INTERVAL_S=0.01` the handler fires a heartbeat ~10ms after connecting, which arrives before the signal.
**Rationale:** The `_wait_for_connection` call after `receive_json()` ensures the queue is present before signalling complete. This ordering is correct: receive heartbeat, confirm connected, then signal done.

### Manager cleanup
**Choice:** `autouse` fixture clears both `_connections` and `_queues` dicts before and after each test.
**Rationale:** `manager` is a module-level singleton shared across all tests in the same process. Without cleanup, state from one test (e.g. stale queues) leaks into subsequent tests. `defaultdict` keys from prior tests can cause `signal_run_complete` to put sentinels into queues that no longer have active consumers.

## Verification
- [x] All 6 tests pass: `pytest tests/ui/test_websocket.py -v` -> 6 passed in 0.36s
- [x] Pre-existing failure (`test_events_router_prefix`) confirmed pre-existing before this step (stash test)
- [x] 627 other tests unaffected
- [x] `_wait_for_connection` resolves broadcast race condition
- [x] `autouse` fixture isolates manager state between tests
