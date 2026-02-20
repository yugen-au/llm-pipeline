# Research: FastAPI WebSocket Patterns for Live Pipeline Event Streaming

## 1. Codebase State Analysis

### Current WebSocket Infrastructure
- `llm_pipeline/ui/routes/websocket.py` exists as empty stub (router only, no endpoints)
- WebSocket router already mounted WITHOUT `/api` prefix in `app.py` line 80: `app.include_router(ws_router)`
- Route path will be `/ws/runs/{run_id}` (not `/api/ws/runs/{run_id}`)

### Sync-Only Codebase
- **Zero** asyncio/async/await usage anywhere in `llm_pipeline/`
- All UI endpoints use sync `def` (not `async def`) per established pattern
- Pipeline execution (`PipelineConfig.execute()`) is entirely synchronous
- Event emission via `_emit()` is synchronous: `handler.emit(event)` on the calling thread
- `InMemoryEventHandler` uses `threading.Lock` for thread safety (not asyncio.Lock)

### Event System Architecture
- `PipelineEventEmitter`: Protocol with sync `emit(event: PipelineEvent) -> None`
- `CompositeEmitter`: Dispatches to multiple handlers with per-handler error isolation
- `InMemoryEventHandler`: Thread-safe in-memory store, events as `list[dict]`
- `SQLiteEventHandler`: Session-per-emit DB persistence
- `PipelineEventRecord`: SQLModel table for persisted events (indexed on `run_id + event_type`)
- 31 concrete event types across 9 categories, all frozen dataclasses with `to_dict()` / `to_json()`

### Pipeline Trigger Flow (runs.py)
- `POST /api/runs` triggers pipeline via `BackgroundTasks.add_task(run_pipeline)`
- `run_pipeline()` is sync, runs in Starlette's threadpool
- No event handler hookup in trigger_run currently (bare factory call)
- Pipeline constructor accepts `event_emitter: Optional[PipelineEventEmitter]`

### Dependencies
- `fastapi>=0.100` (supports WebSocket, Annotated types)
- `uvicorn[standard]>=0.20` (includes websockets library for WebSocket protocol)
- No `pytest-asyncio` in dev deps (will need for async WebSocket tests)
- `starlette.testclient.TestClient` already used, supports `websocket_connect()`

## 2. FastAPI WebSocket Endpoint Pattern

### Core Endpoint Structure
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio

router = APIRouter(tags=["websocket"])

@router.websocket("/ws/runs/{run_id}")
async def websocket_run_events(websocket: WebSocket, run_id: str):
    await websocket.accept()
    try:
        # ... stream events or batch replay
    except WebSocketDisconnect:
        # cleanup connection from registry
    finally:
        # ensure cleanup even on unexpected errors
```

### Key WebSocket Methods (from Starlette)
| Method | Description |
|--------|-------------|
| `await websocket.accept()` | Accept the WebSocket handshake |
| `await websocket.send_json(data)` | Send JSON-serializable dict as text frame |
| `await websocket.send_text(text)` | Send raw text frame |
| `await websocket.close(code=1000)` | Initiate server-side close |
| `raise WebSocketDisconnect` | Caught when client disconnects |

### Error Handling
```python
from fastapi import WebSocketException, status

# Pre-accept validation (before accept())
if not valid_run_id:
    raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

# Post-accept error codes
await websocket.close(code=1000)  # Normal closure
await websocket.close(code=1011)  # Internal error
```

### WebSocket vs HTTP Exception Handling
- `HTTPException` does NOT work in WebSocket endpoints
- Use `WebSocketException` for pre-accept rejection
- Use `websocket.close(code=...)` for post-accept closure
- `WebSocketDisconnect` is raised when client disconnects (catch in try/except)

## 3. Connection Registry Pattern

### Module-Level Registries (per task spec)
```python
import asyncio
from typing import Dict, List
from fastapi import WebSocket

# Per-run connection tracking
_run_connections: Dict[str, List[WebSocket]] = {}

# Per-client event queues (see section 4 for why per-client, not per-run)
_client_queues: Dict[str, List[asyncio.Queue]] = {}
```

### Connection Lifecycle
```python
def _register_connection(run_id: str, websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Register a WebSocket client for a run."""
    if run_id not in _run_connections:
        _run_connections[run_id] = []
        _client_queues[run_id] = []
    _run_connections[run_id].append(websocket)
    _client_queues[run_id].append(queue)

def _unregister_connection(run_id: str, websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Remove a WebSocket client from a run."""
    conns = _run_connections.get(run_id, [])
    queues = _client_queues.get(run_id, [])
    if websocket in conns:
        idx = conns.index(websocket)
        conns.pop(idx)
        queues.pop(idx)
    # Cleanup empty entries
    if not conns:
        _run_connections.pop(run_id, None)
        _client_queues.pop(run_id, None)
```

### Thread Safety for Module-Level Dicts
- `_run_connections` and `_client_queues` are accessed ONLY from the asyncio event loop thread (WebSocket handlers are async)
- No threading.Lock needed for these dicts as long as only async code touches them
- The sync->async bridge (task 26 UIBridge) will use `asyncio.run_coroutine_threadsafe()` to schedule queue puts on the event loop thread
- **Key invariant: all mutations to these dicts happen on the event loop thread**

## 4. Event Distribution: Fan-Out Pattern

### Problem with Single Queue Per Run
The task description shows `_run_queues: Dict[str, asyncio.Queue]` with a single queue per run. This has a critical flaw: when multiple clients call `await queue.get()`, only ONE client receives each event (queue is FIFO, single consumer wins). This breaks the 100+ concurrent connections requirement.

### Recommended: Per-Client Queue Fan-Out
```python
_client_queues: Dict[str, List[asyncio.Queue]] = {}
# Maps run_id -> list of queues, one per connected WebSocket client

def broadcast_to_run(run_id: str, event_dict: dict) -> None:
    """Put event into all client queues for a run. Called from event loop thread."""
    for queue in _client_queues.get(run_id, []):
        try:
            queue.put_nowait(event_dict)
        except asyncio.QueueFull:
            pass  # backpressure: drop event for slow client (see section 7)

def signal_run_complete(run_id: str) -> None:
    """Send sentinel to all client queues, signaling run is done."""
    for queue in _client_queues.get(run_id, []):
        try:
            queue.put_nowait(None)  # None = sentinel
        except asyncio.QueueFull:
            queue.put_nowait(None)  # force sentinel even if full
```

### How UIBridge (Task 26) Plugs In
Task 26 creates a `UIBridge` that calls `broadcast_to_run()` via `asyncio.run_coroutine_threadsafe()` from the sync pipeline thread. Task 25 exposes `broadcast_to_run()` and `signal_run_complete()` as the public API that task 26 calls into.

### Alternative: Single Queue + Broadcaster Task
```python
# One queue per run, one asyncio.Task reads and broadcasts
async def _run_broadcaster(run_id: str, source_queue: asyncio.Queue):
    while True:
        event = await source_queue.get()
        if event is None:
            break
        for ws in _run_connections.get(run_id, []):
            try:
                await ws.send_json(event)
            except Exception:
                pass  # dead connection
```
This is simpler but has drawbacks: if one `send_json` blocks (slow client), it delays all other clients. Per-client queues with independent send loops avoid this head-of-line blocking.

**Recommendation: Per-client queue pattern for production-grade 100+ connection support.**

## 5. Heartbeat via asyncio.wait_for

### Pattern
```python
HEARTBEAT_INTERVAL_S = 30

async def _stream_events(websocket: WebSocket, queue: asyncio.Queue) -> None:
    """Read from client queue and send to WebSocket, with heartbeat on timeout."""
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_S)
        except asyncio.TimeoutError:
            # No events for 30s, send heartbeat to keep connection alive
            await websocket.send_json({"type": "heartbeat", "timestamp": utc_now().isoformat()})
            continue

        if event is None:  # Sentinel: run complete
            await websocket.send_json({"type": "run_complete"})
            break

        await websocket.send_json(event)
```

### Why Application-Level Heartbeat
- WebSocket protocol has native ping/pong frames, but they're transparent to application code
- Uvicorn handles protocol-level pings automatically with `websockets` library
- Application-level heartbeat serves a different purpose: confirms the event stream is alive, not just the TCP connection
- Client can distinguish "no events happening" from "connection dropped"
- The `{"type": "heartbeat"}` message lets the UI show "connected, waiting for events..."

### Timeout Value
- 30s matches task description specification
- Reasonable for LLM pipelines where steps can take 10-60s each
- If steps routinely take >30s, heartbeats fill the gap between real events

## 6. Batch Replay for Completed Runs

### Flow
```python
@router.websocket("/ws/runs/{run_id}")
async def websocket_run_events(websocket: WebSocket, run_id: str):
    await websocket.accept()

    # Check if run exists and is complete
    run_status = await asyncio.to_thread(_get_run_status, run_id)

    if run_status is None:
        await websocket.send_json({"type": "error", "message": "Run not found"})
        await websocket.close(code=1008)
        return

    if run_status in ("completed", "failed"):
        # Batch replay: send all persisted events, then close
        events = await asyncio.to_thread(_get_persisted_events, run_id)
        for event in events:
            await websocket.send_json(event)
        await websocket.send_json({"type": "run_complete", "status": run_status})
        await websocket.close(code=1000)
        return

    # Live streaming path (run is "running")
    # ... register connection, stream from queue, heartbeat loop
```

### DB Access from Async Context
Since SQLite is sync and all DB access uses sync `Session`, we must use `asyncio.to_thread()` to avoid blocking the event loop:

```python
from sqlmodel import Session, select
from llm_pipeline.state import PipelineRun
from llm_pipeline.events.models import PipelineEventRecord

def _get_run_status(run_id: str, engine) -> str | None:
    """Sync DB query, called via asyncio.to_thread()."""
    with Session(engine) as session:
        run = session.exec(
            select(PipelineRun).where(PipelineRun.run_id == run_id)
        ).first()
        return run.status if run else None

def _get_persisted_events(run_id: str, engine) -> list[dict]:
    """Sync DB query, called via asyncio.to_thread()."""
    with Session(engine) as session:
        records = session.exec(
            select(PipelineEventRecord)
            .where(PipelineEventRecord.run_id == run_id)
            .order_by(PipelineEventRecord.timestamp)
        ).all()
        return [r.event_data for r in records]
```

### Engine Access in WebSocket Handler
WebSocket endpoints don't have the same dependency injection as HTTP. Access engine via `websocket.app.state.engine`:
```python
engine = websocket.app.state.engine
```

## 7. Backpressure Handling

### Bounded Queues
```python
MAX_QUEUE_SIZE = 1000  # per client

queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
```

### Drop Policy for Slow Clients
```python
def broadcast_to_run(run_id: str, event_dict: dict) -> None:
    for queue in _client_queues.get(run_id, []):
        try:
            queue.put_nowait(event_dict)
        except asyncio.QueueFull:
            # Option A: Drop oldest event (drain one, put new)
            try:
                queue.get_nowait()  # discard oldest
            except asyncio.QueueEmpty:
                pass
            try:
                queue.put_nowait(event_dict)
            except asyncio.QueueFull:
                pass  # queue is thrashing, skip

            # Option B: Simply drop the new event (simpler)
            # pass
```

### Disconnect Slow Clients (Alternative)
```python
# Track consecutive drops per client
# If > N drops in a row, close the WebSocket
# More aggressive but prevents memory buildup
```

**Recommendation:** Bounded queue with drop-newest policy (Option B: `pass` on QueueFull). Simpler, and for a monitoring UI, missing a few events is acceptable. The UI can always fetch full event history via REST `GET /api/runs/{run_id}/events`.

### Memory Budget
- 100 concurrent connections
- 1000 events max per queue
- ~1KB per event dict
- Total: 100 * 1000 * 1KB = ~100MB worst case
- Acceptable for server-side monitoring application

## 8. Graceful Disconnect Handling

### WebSocketDisconnect Exception
```python
from fastapi import WebSocketDisconnect

@router.websocket("/ws/runs/{run_id}")
async def websocket_run_events(websocket: WebSocket, run_id: str):
    await websocket.accept()
    queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
    _register_connection(run_id, websocket, queue)
    try:
        await _stream_events(websocket, queue)
    except WebSocketDisconnect:
        pass  # client disconnected, cleanup below
    except Exception:
        # Unexpected error -- log and close
        import logging
        logging.getLogger(__name__).exception("WebSocket error for run %s", run_id)
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
    finally:
        _unregister_connection(run_id, websocket, queue)
```

### Cleanup Guarantees
- `finally` block ensures `_unregister_connection` always runs
- Removes WebSocket from `_run_connections[run_id]`
- Removes queue from `_client_queues[run_id]`
- Cleans up empty dicts when last client disconnects

### Run Completion Cleanup
When a run completes (task 26 UIBridge calls `signal_run_complete()`):
1. `None` sentinel put into all client queues
2. Each client's `_stream_events` loop breaks on sentinel
3. Client handler sends `{"type": "run_complete"}` and closes
4. `finally` block cleans up each connection
5. After all clients disconnect, `_run_connections[run_id]` and `_client_queues[run_id]` are auto-cleaned

### Stale Connection Detection
- If a client disconnects without proper close frame (network drop), `send_json()` will raise
- The heartbeat loop (every 30s) ensures stale connections are detected within 30s
- On send failure, exception propagates and `finally` cleanup triggers

## 9. Memory Management

### Lifecycle Summary
| Event | Action |
|-------|--------|
| WebSocket connect | Create queue, register in both dicts |
| WebSocket disconnect | Remove from both dicts, GC queue |
| Run completes | Sentinel to all queues, clients close, dicts cleaned |
| Server shutdown | All WebSocket connections close (Uvicorn handles) |

### Preventing Orphaned Queues
- If a run completes but no WebSocket clients are connected, `_client_queues[run_id]` is empty
- `broadcast_to_run()` iterates empty list, no-op
- No orphaned queues because queues are created per-client, not per-run

### App Shutdown
```python
# In app.py lifespan or shutdown event:
@app.on_event("shutdown")
async def cleanup_websockets():
    # Close all active WebSocket connections
    for run_id, connections in _run_connections.items():
        for ws in connections:
            try:
                await ws.close(code=1001)  # Going Away
            except Exception:
                pass
    _run_connections.clear()
    _client_queues.clear()
```

**Note:** FastAPI lifespan context manager is the modern approach (vs `on_event`). But this codebase doesn't use lifespan yet, so either pattern works.

## 10. Testing Patterns

### Starlette TestClient WebSocket Support
```python
from starlette.testclient import TestClient

def test_websocket_connect(seeded_app_client):
    with seeded_app_client.websocket_connect("/ws/runs/some-run-id") as ws:
        data = ws.receive_json()
        assert data["type"] == "run_complete"  # completed run = batch replay
```

### Test Scenarios
1. **Batch replay for completed run:** Connect, receive all persisted events, receive `run_complete`, connection closes
2. **404 for nonexistent run:** Connect, receive error message, connection closes with 1008
3. **Live streaming:** Connect to running run, push events to client queue, verify receipt
4. **Heartbeat:** Connect, wait >30s, verify heartbeat message received
5. **Disconnect cleanup:** Connect, disconnect, verify connection removed from registry
6. **Multiple clients:** Connect two clients to same run, verify both receive events

### Test Helper for Live Streaming
```python
import asyncio

def test_live_event_streaming(app_client):
    # Need to set up a "running" run in DB and inject events into client queue
    # This requires accessing module-level _client_queues from test code
    # Consider: expose get/set functions for testability
```

### async Test Considerations
- Starlette's `TestClient.websocket_connect()` is synchronous (blocks)
- Works for basic connect/receive/close flows
- For testing concurrent connections or timeouts, may need `pytest-asyncio` with `httpx.AsyncClient`
- Current dev deps lack `pytest-asyncio` -- may need to add

### Fixture Extensions
```python
# Extend seeded_app_client with a "running" run for live streaming tests
run_running = PipelineRun(
    run_id="aaaaaaaa-0000-0000-0000-000000000003",
    pipeline_name="alpha_pipeline",
    status="running",
    started_at=_utc(-100),
)
# This run already exists in seeded data!
```

## 11. Existing Codebase Patterns to Follow

### Pattern Consistency
| Aspect | Existing Pattern | WebSocket Adaptation |
|--------|-----------------|---------------------|
| Router definition | `router = APIRouter(tags=["..."])` | Same, `tags=["websocket"]` |
| Endpoint prefix | HTTP routes get `/api`, WS does not | Already configured in app.py |
| Error handling | `HTTPException(404)` | `websocket.close(code=1008)` |
| DB access | Sync with `DBSession` dependency | `asyncio.to_thread()` with manual Session |
| Response models | Pydantic BaseModel | JSON dicts via `send_json()` |
| Logging | `logging.getLogger(__name__)` | Same |

### Dependency Injection Limitation
FastAPI WebSocket endpoints have limited dependency injection compared to HTTP:
- `WebSocket` object is injected automatically
- Path parameters work (`run_id: str`)
- Query parameters work
- `Depends()` works but `DBSession` pattern needs adaptation (WebSocket is async, DBSession is sync generator)
- **Recommendation:** Access engine directly via `websocket.app.state.engine` and create sessions manually in `asyncio.to_thread()` calls

## 12. Protocol Message Types

### Standard Event Message
```json
{
  "event_type": "step_started",
  "pipeline_name": "alpha_pipeline",
  "run_id": "abc-123",
  "timestamp": "2026-02-20T12:00:00Z",
  "step_name": "step_a",
  "step_number": 1
}
```
This is the output of `PipelineEvent.to_dict()` -- already the format used by `InMemoryEventHandler`.

### Control Messages (WebSocket-specific)
```json
{"type": "heartbeat", "timestamp": "2026-02-20T12:00:30Z"}
{"type": "run_complete", "status": "completed"}
{"type": "error", "message": "Run not found"}
```

### Distinguishing Event vs Control Messages
- Pipeline events have `"event_type"` key (from `PipelineEvent.to_dict()`)
- Control messages have `"type"` key
- No overlap: `event_type` is always a snake_case event name, `type` is a control keyword

## 13. Concurrency for 100+ Connections (NFR-003)

### asyncio Scalability
- Each WebSocket connection is an asyncio Task (coroutine)
- asyncio can handle 10,000+ concurrent tasks on a single thread
- 100 connections is trivial for asyncio
- Bottleneck is not connection count but event throughput

### Event Throughput
- A typical pipeline emits 20-50 events per run
- At 100 concurrent runs: 2,000-5,000 events to distribute
- Each event: ~1KB JSON, `put_nowait()` into 100 queues = 100 * 1KB = 100KB
- Total throughput: well within single-thread asyncio capacity

### Memory Per Connection
- asyncio.Queue overhead: ~1KB empty
- WebSocket connection: ~2KB Starlette state
- Per-client total: ~3KB + buffered events
- 100 clients: ~300KB + buffered events
- With 1000-event bounded queue: ~1MB per client, 100MB total (worst case)

### Uvicorn Workers
- Single Uvicorn worker handles all WebSocket connections
- Module-level dicts are per-process (single worker is required for WebSocket state sharing)
- If multi-worker needed later: move to Redis pub/sub for cross-process broadcast
- For 100 connections: single worker is sufficient

## 14. Summary of Recommended Implementation

### File: `llm_pipeline/ui/routes/websocket.py`

**Public API (consumed by task 26 UIBridge):**
- `broadcast_to_run(run_id: str, event_dict: dict) -> None`
- `signal_run_complete(run_id: str) -> None`

**Internal state:**
- `_run_connections: Dict[str, List[WebSocket]]`
- `_client_queues: Dict[str, List[asyncio.Queue]]`
- `_register_connection(run_id, websocket, queue)`
- `_unregister_connection(run_id, websocket, queue)`

**WebSocket endpoint:**
- `@router.websocket("/ws/runs/{run_id}")` -- async def
- Accept, check run status via `asyncio.to_thread()`
- Completed run: batch replay from DB, close
- Running run: register, stream from per-client queue with heartbeat, cleanup on disconnect

**Constants:**
- `HEARTBEAT_INTERVAL_S = 30`
- `MAX_QUEUE_SIZE = 1000`

### Dependencies to Add
- `pytest-asyncio` in dev deps (for async WebSocket tests, if needed beyond TestClient)
- No new runtime deps (fastapi/starlette already include WebSocket support)
