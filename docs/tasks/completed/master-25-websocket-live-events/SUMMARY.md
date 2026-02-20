# Task Summary

## Work Completed

Implemented WebSocket live event streaming for the llm-pipeline UI layer. The 4-line stub `llm_pipeline/ui/routes/websocket.py` was fully rewritten with a `ConnectionManager` class, per-client `asyncio.Queue` fan-out, JSON heartbeat, batch replay for completed/failed runs, and live streaming for running runs. Six tests were created in `tests/ui/test_websocket.py` covering all connection lifecycle paths. No new runtime dependencies were required; no other files outside websocket.py and the new test file were changed.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `tests/ui/test_websocket.py` | 6 tests across 4 classes: batch replay (completed + failed), not-found, live stream single/multi-client, heartbeat |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/ui/routes/websocket.py` | Complete rewrite from 4-line stub to full implementation: `ConnectionManager` class, `manager` singleton, `HEARTBEAT_INTERVAL_S` constant, `_get_run`, `_get_persisted_events`, `_stream_events` helpers, `websocket_endpoint` handler |

## Commits Made

| Hash | Message |
| --- | --- |
| `aebd1e5` | chore(state): master-25-websocket-live-events -> initialization |
| `1982c5d` | chore(state): master-25-websocket-live-events -> research |
| `2531d86` | chore(state): master-25-websocket-live-events -> research |
| `7cae3d1` | chore(state): master-25-websocket-live-events -> research |
| `cfbe8d6` | chore(state): master-25-websocket-live-events -> validate |
| `5b4614e` | docs(validate-A): master-25-websocket-live-events |
| `40ce361` | chore(state): master-25-websocket-live-events -> planning |
| `f789088` | docs(planning-A): master-25-websocket-live-events |
| `4592e7c` | chore(state): master-25-websocket-live-events -> implementation |
| `9be9d49` | chore(state): master-25-websocket-live-events -> implementation |
| `e8a9c91` | chore(state): master-25-websocket-live-events -> implementation |
| `80f0a82` | docs(implementation-A): master-25-websocket-live-events |
| `0a8f476` | docs(implementation-B): master-25-websocket-live-events |
| `736740e` | chore(state): master-25-websocket-live-events -> implementation |
| `96cf450` | chore(state): master-25-websocket-live-events -> summary |

## Deviations from Plan

- **Per-client queue (task spec deviation)**: Task spec originally described a single `asyncio.Queue` per run (`_run_queues: Dict[str, asyncio.Queue]`). This was replaced with per-client queues before planning began (CEO decision #3). Single-queue-per-run is broken for multi-client: only one consumer receives each event from `queue.get()`. This deviation was resolved and codified in PLAN.md before implementation started; it is not a deviation from PLAN.md.
- **`defaultdict` for internal storage**: PLAN.md described plain dicts with key-existence checks in `connect`. Implementation used `defaultdict(list)` for both `_connections` and `_queues`, simplifying `connect` to a single append. Functionally equivalent; `disconnect` still cleans up empty keys explicitly.
- **`queue` initialized to `None` before try block**: PLAN.md noted this requirement explicitly; implementation followed it. Not a deviation.
- **Testing and review phases excluded**: CEO decision before planning; reflected in PLAN.md phase list. Only implementation phases A and B were executed.

## Issues Encountered

### Race condition: broadcast_to_run called before queue registered in async handler
`TestClient` runs the ASGI app in a background thread. `manager.connect()` is called inside the async handler after `await websocket.accept()`. Without synchronization, test code calling `broadcast_to_run` immediately after the `with websocket_connect()` context was entered ran before the queue existed, resulting in the event being dropped. The live streaming test then received only a heartbeat (after the 30s timeout -- or a hang in tests that did not monkeypatch the interval).

**Resolution:** Added `_wait_for_connection(run_id, count)` helper that polls `manager._queues` with 5ms sleep until the async handler thread has called `manager.connect()`. Called in each live stream test after the `websocket_connect` context is entered.

### Manager singleton state leaking between tests
`manager` is a module-level singleton shared across all tests in the same process. Stale queues from one test caused `signal_run_complete` in subsequent tests to insert `None` sentinels into queues with no active consumers, producing spurious `stream_complete` messages in unrelated receive calls.

**Resolution:** Added `autouse` fixture `_clean_manager` that clears both `manager._connections` and `manager._queues` (as `defaultdict`, `clear()` resets them) before and after each test.

### Heartbeat test ordering
With `HEARTBEAT_INTERVAL_S=0.01`, calling `_wait_for_connection` before `receive_json` caused the heartbeat to arrive while the spin-wait was still running. The receive call returned the heartbeat, then `_wait_for_connection` returned immediately (queue already registered), then `signal_run_complete` was called.

**Resolution:** Ordered the heartbeat test as: `receive_json()` first (blocks until heartbeat arrives, ~10ms), then `_wait_for_connection()` (queue already registered, returns immediately), then `signal_run_complete()`, then drain `stream_complete`. This ordering is correct and deterministic.

## Success Criteria

- [x] `GET /ws/runs/{run_id}` WebSocket endpoint exists and accepts connections -- verified by all 6 tests connecting successfully
- [x] Connecting to a completed run sends all persisted events then `replay_complete` then closes with 1000 -- `test_batch_replay_completed_run` asserts 4 events + `replay_complete` with `event_count=4`, `run_status="completed"`
- [x] Connecting to a failed run with 0 events sends `replay_complete` with `event_count=0` then closes with 1000 -- `test_batch_replay_failed_run_empty` asserts 0 events + `replay_complete` with `event_count=0`, `run_status="failed"`
- [x] Connecting to a nonexistent run sends `{"type": "error", "detail": "Run not found"}` then closes with 4004 -- `test_run_not_found` asserts exact message
- [x] Connecting to a running run enters live stream mode; injected events via `manager.broadcast_to_run` are received -- `test_live_stream_events` verifies event receipt and `stream_complete`
- [x] `manager.signal_run_complete` causes `stream_complete` message -- verified in `test_live_stream_events` and `test_live_stream_multiple_clients`
- [x] Heartbeat `{"type": "heartbeat", "timestamp": "..."}` sent after inactivity -- `test_heartbeat` monkeypatches interval to 0.01s and asserts heartbeat JSON structure
- [x] Two clients connected to same running run both receive every broadcast event (fan-out) -- `test_live_stream_multiple_clients` verifies both ws1 and ws2 receive the event and `stream_complete`
- [x] `manager` singleton exported from `llm_pipeline.ui.routes.websocket` with `broadcast_to_run` and `signal_run_complete` methods callable from sync context -- confirmed by test imports and direct calls
- [x] All existing tests (`pytest`) continue to pass -- 627 tests pass (2 pre-existing failures unrelated to this change confirmed pre-existing via stash test)
- [x] No new runtime dependencies required -- only stdlib (`asyncio`, `collections`, `datetime`) and existing deps (`fastapi`, `sqlmodel`)

## Recommendations for Follow-up

1. **Task 26 (UIBridge)**: The `manager` singleton public API is ready: `broadcast_to_run(run_id, event_data)` and `signal_run_complete(run_id)`. Task 26 should import `manager` from `llm_pipeline.ui.routes.websocket` and call these via `asyncio.run_coroutine_threadsafe()` or directly from the event loop thread (both are safe since the methods are sync `put_nowait` calls).
2. **Authentication**: WS endpoint has no auth, consistent with current REST endpoints. If auth is added to REST routes, apply the same mechanism here (e.g., token query param on connect URL, validated before `accept()`).
3. **Multi-worker support**: `ConnectionManager` holds in-process state. A second Uvicorn worker would have its own `manager` instance and miss events broadcast to the other worker's clients. If horizontal scaling is needed, replace in-process queues with Redis pub/sub (one channel per `run_id`).
4. **Connection limit enforcement**: No hard cap on concurrent connections. For production, consider adding a limit in `manager.connect()` (e.g., raise if `len(self._connections[run_id]) >= MAX_CLIENTS`) to prevent resource exhaustion.
5. **Shutdown cleanup**: No lifespan handler cancels active WS connections on server shutdown. Uvicorn handles connection teardown at process exit. If graceful shutdown is needed, add a lifespan event that calls `manager.signal_run_complete` for all active runs before shutdown.
6. **Race condition (run transitions during connect)**: If a run transitions from `running` to `completed` between the `_get_run` status check and `manager.connect()`, the client enters live stream mode but receives no events (pipeline already done) and eventually times out after 30s. Client mitigation: reconnect on `stream_complete` absence; if reconnect returns `replay_complete`, all events are available. This is acceptable per CEO.
7. **`asyncio.to_thread` with multi-worker SQLite**: Current setup uses StaticPool with `check_same_thread=False` in tests. In production with a real DB file, `asyncio.to_thread` dispatches to the thread pool, which is correct. If SQLAlchemy async engine is ever adopted, replace `asyncio.to_thread` wrappers with native `async with AsyncSession` patterns.
