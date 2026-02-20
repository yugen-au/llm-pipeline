# WebSocket Architecture Research -- Task 25

## 1. Codebase Context

### Existing Event System
- `llm_pipeline/events/types.py`: 25+ frozen dataclass event types, auto-registry via `__init_subclass__`, `to_dict()` serialization
- `llm_pipeline/events/emitter.py`: `PipelineEventEmitter` (runtime_checkable Protocol, sync `emit(event) -> None`), `CompositeEmitter` dispatches to multiple handlers
- `llm_pipeline/events/handlers.py`: `InMemoryEventHandler` (thread-safe list), `SQLiteEventHandler` (session-per-emit persistence), `LoggingEventHandler`
- `llm_pipeline/events/models.py`: `PipelineEventRecord` SQLModel table (`pipeline_events`), indexed on `(run_id, event_type)` and `(event_type)`

### Event Persistence (Task 21, done)
- `SQLiteEventHandler.emit()` creates a `PipelineEventRecord` per event with `run_id`, `event_type`, `pipeline_name`, `timestamp`, `event_data` (JSON)
- REST endpoint `GET /api/runs/{run_id}/events` queries `PipelineEventRecord` table with pagination and optional `event_type` filter
- Events are persisted synchronously during pipeline execution

### WebSocket Stub
- `llm_pipeline/ui/routes/websocket.py`: 4-line stub with empty `APIRouter(tags=["websocket"])`
- `app.py` line 80: `app.include_router(ws_router)` -- mounted WITHOUT `/api` prefix (WebSocket routes are unprefixed by convention)

### Pipeline Execution Model
- `PipelineConfig.execute()` is **synchronous** (runs in background thread via `BackgroundTasks` in `runs.py` `trigger_run`)
- Events emitted via `self._emit()` which calls `event_emitter.emit(event)` -- also synchronous
- `PipelineRun` model tracks run status: `running` / `completed` / `failed` with timestamps

### Existing Test Infrastructure
- `tests/ui/conftest.py`: `_make_app()` factory with in-memory SQLite (StaticPool), seeded `PipelineRun`, `PipelineStepState`, `PipelineEventRecord` rows
- `TestClient` from Starlette used for all UI tests; `TestClient.websocket_connect()` available for WS testing

---

## 2. WebSocket Endpoint Design

### URL
```
/ws/runs/{run_id}
```
Consistent with app.py no-prefix mounting for WS routes.

### Connection Lifecycle
```
Client connects -> accept()
  |
  +-> Check PipelineRun.status
  |     |
  |     +-> "completed" or "failed": BATCH REPLAY path
  |     |     Send all persisted PipelineEventRecord rows as JSON
  |     |     Send {"type": "replay_complete", "run_status": "completed"}
  |     |     close()
  |     |
  |     +-> "running": LIVE STREAM path
  |     |     Register in ConnectionManager
  |     |     Loop: await queue.get() with 30s timeout
  |     |       - event received: send_json(event)
  |     |       - timeout: send ping frame (keepalive)
  |     |       - sentinel None: run complete, break
  |     |     Unregister, close()
  |     |
  |     +-> Not found: send {"type": "error", "detail": "Run not found"}, close(4004)
  |
  +-> WebSocketDisconnect: cleanup connection from manager
```

### Message Format (server -> client)
All messages are JSON matching `PipelineEvent.to_dict()` format:
```json
{
  "event_type": "step_started",
  "run_id": "uuid",
  "pipeline_name": "my_pipeline",
  "timestamp": "2026-02-20T12:00:00+00:00",
  "step_name": "step_a",
  "step_number": 1,
  "system_key": "sys_prompt_key",
  "user_key": "user_prompt_key"
}
```
This matches `PipelineEventRecord.event_data` and what `InMemoryEventHandler` stores. Consistent with REST event endpoint.

### Control Messages (server -> client)
```json
{"type": "replay_complete", "run_status": "completed", "event_count": 42}
{"type": "stream_complete", "run_id": "uuid"}
{"type": "error", "detail": "Run not found"}
```

---

## 3. Connection Management

### ConnectionManager Class
Encapsulate state in a class (not module-level dicts) for testability and lifecycle management.

```python
class ConnectionManager:
    """Manage per-run WebSocket connections and event queues."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()  # protects dict mutations

    async def connect(self, run_id: str, ws: WebSocket) -> None:
        """Register a WebSocket for a run."""
        async with self._lock:
            if run_id not in self._connections:
                self._connections[run_id] = set()
            self._connections[run_id].add(ws)

    async def disconnect(self, run_id: str, ws: WebSocket) -> None:
        """Unregister a WebSocket. Cleanup queue if no connections remain."""
        async with self._lock:
            conns = self._connections.get(run_id)
            if conns:
                conns.discard(ws)
                if not conns:
                    del self._connections[run_id]
                    self._queues.pop(run_id, None)

    def get_or_create_queue(self, run_id: str) -> asyncio.Queue:
        """Get or create event queue for a run."""
        if run_id not in self._queues:
            self._queues[run_id] = asyncio.Queue()
        return self._queues[run_id]

    async def broadcast_to_run(self, run_id: str, event_data: dict) -> None:
        """Broadcast event to all connected clients for a run."""
        conns = self._connections.get(run_id, set())
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_json(event_data)
            except Exception:
                dead.append(ws)
        # Cleanup dead connections
        for ws in dead:
            conns.discard(ws)

    async def complete_run(self, run_id: str) -> None:
        """Signal run completion to all waiting consumers."""
        queue = self._queues.get(run_id)
        if queue:
            await queue.put(None)  # sentinel
```

### Module-Level Instance
```python
manager = ConnectionManager()
```
Exposed as module-level singleton in `websocket.py`. Task 26 (UIBridge) imports this to call `broadcast_to_run()`.

### Thread Safety Note
`ConnectionManager` methods are async and use `asyncio.Lock`. They run in the event loop. Task 26's `UIBridge` will need `asyncio.run_coroutine_threadsafe()` to call `broadcast_to_run` from the sync pipeline thread. This is Task 26's responsibility.

---

## 4. Per-Run Event Queue Architecture

### Design
- One `asyncio.Queue` per active run_id
- Created lazily on first WebSocket connect for a running run
- Destroyed when last client disconnects (in `disconnect()`)
- Unbounded (`maxsize=0`): events are small dicts (~500B), runs are finite (typically 2-10 steps, ~20-50 events)

### Producer Side (Task 26 scope, interface defined here)
Task 26's `UIBridge` will:
1. Receive sync `emit(event)` calls from pipeline thread
2. Serialize event via `event.to_dict()`
3. Put into queue via `asyncio.run_coroutine_threadsafe(manager.get_or_create_queue(run_id).put(event_dict), loop)`

### Consumer Side (Task 25 scope)
WebSocket handler:
1. Gets queue via `manager.get_or_create_queue(run_id)`
2. Loop: `await asyncio.wait_for(queue.get(), timeout=30.0)`
3. On event: `await ws.send_json(event_data)`
4. On sentinel (None): break, send stream_complete, close
5. On timeout: send ping frame

### Broadcasting vs. Queue-per-Connection
Two viable approaches:
- **Option A (queue-per-connection)**: Each WebSocket gets its own queue. Producer puts event into all queues. Simple consumer loop but N queues per run.
- **Option B (single queue + broadcast)**: One queue per run. A single consumer task reads the queue and broadcasts to all connections. More efficient for multiple clients.

**Recommendation: Option B** -- matches the ConnectionManager.broadcast_to_run pattern. However, the WebSocket handler loop becomes simpler with Option A (each handler reads its own queue). For 100+ connections, Option B is better (fewer queue operations).

**Refined approach: hybrid** -- The queue is read by the first consumer coroutine, which broadcasts. But this creates a leader-election problem. Simpler: the producer (UIBridge, Task 26) calls `broadcast_to_run()` directly, bypassing the queue entirely. The queue is only needed if we want to decouple production from consumption timing.

**Final recommendation**: Skip the queue pattern for broadcast. Task 26's UIBridge calls `manager.broadcast_to_run(run_id, event_dict)` directly via `asyncio.run_coroutine_threadsafe`. Each WebSocket handler just blocks on a per-connection `asyncio.Event` or similar signal for run completion. This eliminates queue complexity.

**BUT**: The task description explicitly specifies per-run queues. Honor the task description.

**Reconciled design**: Per-run queue exists. A dedicated background task per run consumes the queue and broadcasts. Each WebSocket handler waits for broadcast via a per-connection asyncio.Queue (fan-out). This is clean and matches the task spec.

**Simplest correct design**:
```
Producer (Task 26) -> per-run asyncio.Queue -> broadcaster coroutine -> per-connection asyncio.Queue -> WS handler send loop
```

Actually, let me simplify further. Each WS handler can share the same per-run queue if we use a **fan-out pattern**:

```
Producer puts event into per-run queue
-> A "run consumer" task reads queue, calls broadcast_to_run
-> broadcast_to_run sends to all registered WebSockets directly
```

The WS handler just needs to stay alive (keepalive loop) and gets events pushed to it via broadcast_to_run. But then the handler loop needs to be `receive` based (waiting for client messages or disconnect), not `queue.get` based.

**Final final design (honoring task spec)**:
Each WebSocket connection gets its own asyncio.Queue. The producer puts events into ALL per-connection queues for that run_id. Each handler reads its own queue. This is Option A -- straightforward, O(connections) memory per run, no broadcaster task needed.

```python
# _run_connections: dict[str, dict[WebSocket, asyncio.Queue]]
# Producer: for each ws, queue pair in run's connections: queue.put_nowait(event)
# Consumer (WS handler): await queue.get() with timeout
```

This is cleaner and each handler is self-contained.

---

## 5. Heartbeat / Keepalive Strategy

### Mechanism: asyncio.wait_for timeout
```python
try:
    event = await asyncio.wait_for(queue.get(), timeout=30.0)
except asyncio.TimeoutError:
    # Send WebSocket ping frame
    await websocket.send({"type": "websocket.ping", "bytes": b""})
    continue
```

### Why Ping Frames (not JSON heartbeat)
- WebSocket ping/pong is protocol-level; browser WebSocket API handles pong automatically
- No application-level noise; client doesn't need to parse/ignore heartbeat messages
- Starlette supports sending raw ASGI messages including ping frames
- 30s interval prevents proxy/load-balancer idle timeouts (typically 60s)

### Client Disconnect Detection
- If ping fails (client gone), `send()` raises exception -> triggers cleanup in except block
- `WebSocketDisconnect` caught in outer try/except

---

## 6. Batch Replay Pattern

### Flow for Completed/Failed Runs
```python
# 1. Query PipelineRun status
run = session.exec(select(PipelineRun).where(PipelineRun.run_id == run_id)).first()
if run is None:
    await websocket.send_json({"type": "error", "detail": "Run not found"})
    await websocket.close(code=4004)
    return

if run.status in ("completed", "failed"):
    # 2. Query all persisted events
    events = session.exec(
        select(PipelineEventRecord)
        .where(PipelineEventRecord.run_id == run_id)
        .order_by(PipelineEventRecord.timestamp)
    ).all()
    # 3. Send each event
    for evt in events:
        await websocket.send_json(evt.event_data)
    # 4. Send completion signal
    await websocket.send_json({
        "type": "replay_complete",
        "run_status": run.status,
        "event_count": len(events),
    })
    await websocket.close()
    return
```

### DB Session Management
WebSocket handler is `async def`. Need a sync Session for SQLite queries. Options:
1. Create Session directly from `app.state.engine` (consistent with `trigger_run` in runs.py)
2. Use `run_in_executor` for sync DB calls within async handler

**Recommendation**: Create Session directly. SQLite queries are fast (<1ms for indexed lookups). The initial status check and event replay are one-shot operations at connection time, not in a loop.

---

## 7. Concurrency & Scalability (NFR-003: 100+ connections)

### asyncio Capacity
- Each WebSocket is a coroutine; asyncio event loop handles 10K+ concurrent coroutines
- Memory per connection: ~1KB (WebSocket) + ~1KB (Queue) + overhead = ~4-8KB
- 100 connections = ~400KB-800KB -- trivially fits in memory

### Broadcasting Performance
- `send_json` serializes dict to JSON per call; for N clients watching same run, JSON serialization happens N times
- Optimization (optional): serialize once, use `send_text(json_str)` for all clients
- At 100 connections with ~50 events/run: 5000 send operations total -- well within capacity

### Backpressure
- If a client is slow, `send_json` awaits until the OS TCP buffer accepts the data
- This blocks only that client's send, not others (each runs in its own coroutine via the per-connection queue)
- If a client is completely stuck, the per-connection queue grows -- bounded by run event count (finite, typically <100)

---

## 8. Testing Patterns

### TestClient WebSocket Testing
```python
def test_websocket_replay_completed_run(seeded_app_client):
    """Completed run sends all events then closes."""
    with seeded_app_client.websocket_connect("/ws/runs/aaaaaaaa-0000-0000-0000-000000000001") as ws:
        events = []
        while True:
            data = ws.receive_json()
            if data.get("type") == "replay_complete":
                break
            events.append(data)
        assert len(events) == 4  # 4 seeded events for RUN_1
        assert data["event_count"] == 4

def test_websocket_unknown_run(app_client):
    """Unknown run_id gets error and close."""
    with app_client.websocket_connect("/ws/runs/nonexistent") as ws:
        data = ws.receive_json()
        assert data["type"] == "error"
```

### Live Stream Testing
- Requires async test setup or threading to simulate producer + consumer
- Create ConnectionManager, manually put events into queue, verify WS receives them
- Use `pytest-asyncio` for async test functions if needed (not currently in dev deps -- may need to add or use threading approach)

---

## 9. Dependencies & Conventions

### No New Dependencies
- FastAPI WebSocket support is built-in (already in `ui` optional deps)
- `asyncio` is stdlib
- `TestClient.websocket_connect()` available from starlette (transitive via fastapi)

### Convention Alignment
| Aspect | Existing Pattern | WebSocket Handler |
|--------|-----------------|-------------------|
| Router prefix | REST: `/api`, WS: none | `/ws/runs/{run_id}` (no prefix) |
| DB access | `DBSession` (ReadOnlySession) | Direct `Session(engine)` for initial queries |
| Function type | REST: sync `def` | WS: `async def` (required) |
| Response format | Pydantic `BaseModel` | JSON dicts (event_data format) |
| Error codes | HTTP 404 | WS close code 4004 (custom) |

---

## 10. Interface for Task 26 (UIBridge)

### What Task 25 Exposes
```python
# llm_pipeline/ui/routes/websocket.py
manager = ConnectionManager()  # module-level singleton

# Task 26 imports:
# from llm_pipeline.ui.routes.websocket import manager
# Then calls: asyncio.run_coroutine_threadsafe(
#     manager.broadcast_to_run(run_id, event_dict), loop
# )
```

### Completion Signal
Task 26's UIBridge calls `manager.complete_run(run_id)` when pipeline finishes, which puts `None` sentinel into all per-connection queues for that run_id.

---

## 11. Implementation Plan (high-level)

### Files to Create/Modify
| File | Action | Purpose |
|------|--------|---------|
| `llm_pipeline/ui/routes/websocket.py` | Rewrite | ConnectionManager class, WebSocket endpoint |
| `tests/ui/test_websocket.py` | Create | Connection lifecycle, replay, error tests |
| `tests/ui/conftest.py` | Modify | Add fixture for WS testing (running run seed data) |

### No Changes Needed
- `app.py` -- ws_router already registered without prefix
- `events/` -- event system unchanged
- `state.py` -- PipelineRun model unchanged
- `pyproject.toml` -- no new dependencies

---

## 12. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Starlette ping frame support varies by version | Keepalive fails | Use `websocket.send({"type": "websocket.ping", "bytes": b""})` per ASGI spec; verify in tests |
| SQLite blocking in async handler | Event loop blocked during replay | Queries are <1ms for indexed lookups; acceptable. Could wrap in `run_in_executor` if needed. |
| Memory leak if connections not cleaned up | Gradual memory growth | `disconnect()` removes queue + connection set when last client leaves |
| Race: client connects while run transitions to completed | Client misses events | Initial status check is atomic; if status changes mid-connect, client can reconnect and get replay |
| TestClient WebSocket doesn't support ping frames | Can't test heartbeat | Test heartbeat logic separately via unit test on ConnectionManager; integration test verifies no crash on timeout |
