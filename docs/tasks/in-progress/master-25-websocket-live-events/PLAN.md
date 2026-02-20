# PLANNING

## Summary

Implement a FastAPI WebSocket endpoint at `/ws/runs/{run_id}` that streams pipeline events to connected clients in real time. The handler uses a class-based `ConnectionManager` with per-client `asyncio.Queue` fan-out to support 100+ concurrent connections (NFR-003). Completed/failed runs replay persisted events in batch; running runs stream live events via heartbeat-protected queue loops.

## Plugin & Agents

**Plugin:** backend-development, python-development
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Implementation**: Rewrite `websocket.py` with `ConnectionManager`, WS endpoint, and private helpers. No new files outside of test file.
2. **Testing**: Create `tests/ui/test_websocket.py` covering all connection lifecycle paths.

## Architecture Decisions

### ConnectionManager: Class-Based Singleton

**Choice:** Class-based `ConnectionManager` with module-level `manager = ConnectionManager()` singleton.
**Rationale:** CEO decision #2. Class is testable (can instantiate fresh instances in tests), encapsulates state, matches FastAPI documented patterns. Module-level singleton provides stable import surface for Task 26 UIBridge.
**Alternatives:** Module-level dicts (less testable, harder to reset between tests).

### Per-Client Queue Fan-Out

**Choice:** Each connected client gets its own `asyncio.Queue`; `broadcast_to_run` does `put_nowait` into every client's queue.
**Rationale:** CEO decision #3. Single-queue-per-run is broken for multi-client (only one consumer gets each event from `queue.get()`). Per-client fan-out ensures every client receives every event.
**Alternatives:** Single queue per run (task spec original -- rejected as broken for multi-client).

### Heartbeat: JSON Application-Level

**Choice:** `{"type": "heartbeat", "timestamp": "..."}` via `asyncio.wait_for(queue.get(), timeout=30.0)` + `TimeoutError` handler.
**Rationale:** CEO decision #1. JS WebSocket API does not expose protocol-level ping/pong frames. JSON heartbeat is client-visible, lets UI show "connected, waiting for events...", works across all browsers and proxies.
**Alternatives:** WebSocket protocol-level ping frames (Starlette version-dependent behavior, not visible in JS).

### DB Access: asyncio.to_thread

**Choice:** Wrap `Session(engine)` queries in `asyncio.to_thread()` for both run status check and event batch fetch.
**Rationale:** Avoids blocking the asyncio event loop on SQLite I/O, even though SQLite is fast. Engine accessed via `websocket.app.state.engine` (confirmed in `app.py` line 48).
**Alternatives:** Sync DB calls directly in async handler (blocks event loop, bad practice).

### Close Codes

**Choice:** Run not found: `close(4004)`. Normal close (replay or stream complete): `close(1000)`. Internal error: `close(1011)`.
**Rationale:** CEO decision #4. 4004 is in RFC 6455 application-use range (4000-4999), intuitively maps to HTTP 404.
**Alternatives:** 1008 (policy violation -- less intuitive for not-found).

### Control Message Naming: Separate

**Choice:** Distinct `"type"` values: `replay_complete`, `stream_complete`, `heartbeat`, `error`.
**Rationale:** CEO decision #5. Client can distinguish replay from live mode without tracking connection state. Pipeline events use `"event_type"` key (no overlap with control `"type"` key).
**Alternatives:** Unified `complete` message with mode field (requires client to track state).

### Unbounded Queues

**Choice:** `asyncio.Queue()` with no `maxsize`.
**Rationale:** CEO decision #6. Pipelines emit <100 events per run. Bounded queues add drop-policy complexity for no real benefit at this scale (~300KB for 100 clients).
**Alternatives:** `asyncio.Queue(maxsize=1000)` with drop policy (unnecessary complexity).

## Implementation Steps

### Step 1: Implement ConnectionManager and WebSocket Endpoint

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** A

1. Rewrite `llm_pipeline/ui/routes/websocket.py` entirely. Keep the existing `APIRouter(tags=["websocket"])` but add all implementation below it.
2. Add `ConnectionManager` class with `__init__`, `connect`, `disconnect`, `broadcast_to_run`, `signal_run_complete` methods. All methods are sync (use `put_nowait`, not `await`). `connect` creates a new `asyncio.Queue()` per client, appends it to `self._queues[run_id]`, appends `ws` to `self._connections[run_id]`, returns the queue. `disconnect` removes the ws and queue from those lists; if list becomes empty, deletes the key.
3. Add module-level singleton: `manager = ConnectionManager()`.
4. Add module-level constant: `HEARTBEAT_INTERVAL_S: float = 30.0`.
5. Add private async helper `_get_run(engine, run_id) -> PipelineRun | None` using `asyncio.to_thread` with `Session(engine)` and `select(PipelineRun).where(PipelineRun.run_id == run_id)`. Import `select` from `sqlmodel`.
6. Add private async helper `_get_persisted_events(engine, run_id) -> list[dict]` using `asyncio.to_thread` with `Session(engine)`, querying `PipelineEventRecord` ordered by `PipelineEventRecord.timestamp`, returning list of `record.event_data` dicts.
7. Add private async helper `_stream_events(websocket: WebSocket, queue: asyncio.Queue, run_id: str) -> None` that loops: calls `asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_S)`. On `asyncio.TimeoutError`: `await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()})` and continue. On `None` sentinel: `await websocket.send_json({"type": "stream_complete", "run_id": run_id})`, break. On event dict: `await websocket.send_json(event_dict)`.
8. Add WebSocket endpoint `@router.websocket("/ws/runs/{run_id}")` as `async def websocket_endpoint(websocket: WebSocket, run_id: str)`. Body: `await websocket.accept()`. Wrap everything after accept in `try/except WebSocketDisconnect` with a `finally` that calls `manager.disconnect(run_id, websocket, queue)` (where `queue` is only assigned if `connect` was reached). Use `engine = websocket.app.state.engine`.
9. In the endpoint body after accept: call `_get_run(engine, run_id)` via await. If `run is None`: `await websocket.send_json({"type": "error", "detail": "Run not found"})`, `await websocket.close(4004)`, return.
10. If `run.status in ("completed", "failed")`: call `_get_persisted_events(engine, run_id)`, send each event via `await websocket.send_json(event_data)`, then send `{"type": "replay_complete", "run_status": run.status, "event_count": len(events)}`, `await websocket.close(1000)`, return.
11. If `run.status == "running"`: `queue = manager.connect(run_id, websocket)`, then `await _stream_events(websocket, queue, run_id)`.
12. Add necessary imports at top: `asyncio`, `datetime` from `datetime`, `timezone` from `datetime`, `WebSocket`, `WebSocketDisconnect` from `fastapi`, `Session` from `sqlmodel`, `select` from `sqlmodel`, `PipelineRun` from `llm_pipeline.state`, `PipelineEventRecord` from `llm_pipeline.events.models`.

### Step 2: Create WebSocket Tests

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** B

1. Create `tests/ui/test_websocket.py`. Import `pytest`, `TestClient` from `starlette.testclient`, `seeded_app_client` fixture from `tests.ui.conftest` (via `conftest.py` fixture injection), and `manager` from `llm_pipeline.ui.routes.websocket`.
2. Write test `test_batch_replay_completed_run`: use `seeded_app_client`, connect to `/ws/runs/aaaaaaaa-0000-0000-0000-000000000001`, receive messages in a loop until `type == "replay_complete"`, assert exactly 4 event messages received before it, assert `replay_complete.event_count == 4`, assert `replay_complete.run_status == "completed"`.
3. Write test `test_batch_replay_failed_run_empty`: connect to `/ws/runs/aaaaaaaa-0000-0000-0000-000000000002`, receive until `replay_complete`, assert 0 events before it, `event_count == 0`, `run_status == "failed"`.
4. Write test `test_run_not_found`: connect to `/ws/runs/nonexistent-run-id`, receive first message, assert `{"type": "error", "detail": "Run not found"}`.
5. Write test `test_live_stream_events`: use `seeded_app_client` to connect to `/ws/runs/aaaaaaaa-0000-0000-0000-000000000003` (running run). After connection established (client in context), from test code call `manager.broadcast_to_run("aaaaaaaa-0000-0000-0000-000000000003", {"event_type": "step_started", "run_id": "aaaaaaaa-0000-0000-0000-000000000003"})` then `manager.signal_run_complete("aaaaaaaa-0000-0000-0000-000000000003")`. Receive messages: assert first is the event dict, second has `type == "stream_complete"`.
6. Write test `test_live_stream_multiple_clients`: open two WS connections to the same running run. Inject one event via `broadcast_to_run`, then signal complete. Assert both clients receive the event and `stream_complete`.
7. Write test `test_heartbeat`: monkeypatch `llm_pipeline.ui.routes.websocket.HEARTBEAT_INTERVAL_S` to `0.01`. Connect to running run. Receive one message, assert `type == "heartbeat"`. Then signal complete.
8. Ensure all tests use `with seeded_app_client.websocket_connect(...)` context manager from Starlette `TestClient`. Note: each test that modifies `manager` state should clean up or use fresh `seeded_app_client` fixture (each call creates a new app instance which imports a fresh `manager` singleton -- verify this pattern or use `manager._connections.clear()` / `manager._queues.clear()` in teardown if same module-level singleton is shared).

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Module-level `manager` singleton is shared across test invocations if same process reuses the module | Medium | Each `_make_app()` call in conftest imports ws_router but Python module cache means `manager` is the same object. Tests that modify manager state must clean up queues/connections after each test, or the test for live streaming must use a unique run_id per test to avoid state collision. |
| Race condition: run transitions from "running" to "completed" between status check and `manager.connect()` | Low | Client connects, sees "running", gets no events (pipeline already done), eventually times out. Mitigation: client should reconnect and gets batch replay. Acceptable per CEO. |
| `asyncio.to_thread` with StaticPool SQLite in tests: multiple threads sharing same in-memory DB | Medium | StaticPool + `check_same_thread=False` is already configured in `_make_app()` conftest. `asyncio.to_thread` dispatches to threadpool workers. The existing setup should handle this; verify in tests. |
| `websocket.close()` after `send_json` may raise if client already disconnected | Low | Wrap close calls in try/except or rely on WebSocketDisconnect being caught in the outer try/except block. |
| Starlette TestClient WebSocket context manager behavior with async handlers | Low | TestClient runs the ASGI app synchronously in a thread; WebSocket connections work via `with client.websocket_connect()`. Validated as sufficient in VALIDATED_RESEARCH.md. |

## Success Criteria

- [ ] `GET /ws/runs/{run_id}` WebSocket endpoint exists and accepts connections
- [ ] Connecting to a completed run sends all persisted events then `replay_complete` then closes with 1000
- [ ] Connecting to a failed run with 0 events sends `replay_complete` with `event_count=0` then closes with 1000
- [ ] Connecting to a nonexistent run sends `{"type": "error", "detail": "Run not found"}` then closes with 4004
- [ ] Connecting to a running run enters live stream mode; injected events via `manager.broadcast_to_run` are received
- [ ] `manager.signal_run_complete` causes `stream_complete` message and connection close
- [ ] Heartbeat `{"type": "heartbeat", "timestamp": "..."}` sent after 30s of queue inactivity
- [ ] Two clients connected to same running run both receive every broadcast event (fan-out)
- [ ] `manager` singleton exported from `llm_pipeline.ui.routes.websocket` with `broadcast_to_run` and `signal_run_complete` methods callable from sync context
- [ ] All existing tests (`pytest`) continue to pass
- [ ] No new runtime dependencies required

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All architectural decisions resolved by CEO, all assumptions validated against codebase, no new dependencies, existing test infra (StaticPool + TestClient) is confirmed sufficient, Task 21 provides all needed DB tables and seeded data. The implementation is a single file rewrite plus one new test file.
**Suggested Exclusions:** testing, review
