# Research Summary

## Executive Summary

Consolidated findings from two research phases for Task 25 (WebSocket Handler for Live Events). Both research documents were validated against the actual codebase. All 7 architectural decisions resolved by CEO. The existing event system (Task 21), WebSocket stub, and app mounting are confirmed ready. No new runtime dependencies needed. Per-client queue fan-out pattern selected over single-queue-per-run to support 100+ concurrent connections (NFR-003). Task 26 (UIBridge) is downstream and OUT OF SCOPE -- Task 25 only exposes the public API surface it will consume.

---

## Domain Findings

### Codebase State (Verified)
**Source:** step-1, step-2, direct codebase inspection

- `llm_pipeline/ui/routes/websocket.py`: 4-line stub, empty `APIRouter(tags=["websocket"])`
- `app.py` line 80: `app.include_router(ws_router)` -- mounted WITHOUT `/api` prefix
- Zero async/await usage anywhere in `llm_pipeline/` source (confirmed via grep)
- `PipelineRun.status` field: `"running"` (default), `"completed"`, `"failed"` -- confirmed in `state.py`
- `PipelineEventRecord` table: indexed on `(run_id, event_type)` and `(event_type)`, stores `event_data` as JSON column
- `PipelineConfig.execute()` is sync, dispatched via `BackgroundTasks.add_task()` in `runs.py`
- `PipelineEventEmitter`: sync Protocol with `emit(event) -> None`
- `CompositeEmitter`: sequential dispatch with per-handler error isolation
- Test infra: `_make_app()` factory with in-memory SQLite (StaticPool), `TestClient` from starlette
- Seeded data: RUN_1 (completed, 4 events), RUN_2 (failed, 0 events), RUN_3 (running, 0 events)
- `fastapi>=0.100` and `uvicorn[standard]>=0.20` already in `[ui]` optional deps -- includes WebSocket support
- No `pytest-asyncio` in dev deps (not needed if all tests use sync TestClient)

### WebSocket Endpoint Design (CEO-Resolved)
**Source:** step-1 section 2, step-2 section 2, CEO decisions

**URL:** `/ws/runs/{run_id}` (no prefix, consistent with app.py mounting)

**Connection lifecycle:**
```
Client connects -> accept()
  |
  +-> Check PipelineRun.status via asyncio.to_thread()
  |     |
  |     +-> Not found: send {"type": "error", "detail": "Run not found"}, close(4004)
  |     |
  |     +-> "completed" or "failed": BATCH REPLAY
  |     |     Send all PipelineEventRecord rows as JSON (ordered by timestamp)
  |     |     Send {"type": "replay_complete", "run_status": "completed", "event_count": N}
  |     |     close(1000)
  |     |
  |     +-> "running": LIVE STREAM
  |           Register in ConnectionManager (per-client queue created)
  |           Loop: await asyncio.wait_for(queue.get(), timeout=30.0)
  |             - event received: send_json(event)
  |             - timeout: send_json({"type": "heartbeat", "timestamp": "..."})
  |             - sentinel None: send {"type": "stream_complete", "run_id": "..."}, close(1000)
  |
  +-> WebSocketDisconnect: cleanup in finally block
```

### Connection Management (CEO-Resolved: Class-Based)
**Source:** step-1 section 3, step-2 section 3, CEO decision #2

Class-based `ConnectionManager` chosen over module-level dicts for testability and encapsulation. Module-level singleton instance exposed for Task 26 import.

```python
class ConnectionManager:
    """Per-run WebSocket connections with per-client queue fan-out."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = {}
        self._queues: dict[str, list[asyncio.Queue]] = {}

    def connect(self, run_id: str, ws: WebSocket) -> asyncio.Queue:
        """Register WS, create per-client queue, return it."""

    def disconnect(self, run_id: str, ws: WebSocket, queue: asyncio.Queue) -> None:
        """Unregister WS and queue. Cleanup empty entries."""

    def broadcast_to_run(self, run_id: str, event_dict: dict) -> None:
        """put_nowait(event_dict) into all client queues for run. Sync."""

    def signal_run_complete(self, run_id: str) -> None:
        """put_nowait(None) sentinel into all client queues for run. Sync."""

# Module-level singleton
manager = ConnectionManager()
```

**Thread safety note:** All dict mutations happen on the asyncio event loop thread (WebSocket handlers are async). No asyncio.Lock needed. Task 26's UIBridge calls `broadcast_to_run`/`signal_run_complete` via `asyncio.run_coroutine_threadsafe()` which schedules on the event loop thread.

### Per-Client Queue Fan-Out (CEO-Resolved: Deviate from Task Spec)
**Source:** step-1 section 4, step-2 section 4, CEO decision #3

Task spec shows single `_run_queues: Dict[str, asyncio.Queue]` per run. This is broken for multi-client: only one client gets each event from `queue.get()`. Per-client queue fan-out selected instead.

**Pattern:**
```
Producer (Task 26 UIBridge)
  -> manager.broadcast_to_run(run_id, event_dict)
    -> put_nowait into each client's asyncio.Queue
      -> each WS handler loop reads its own queue -> send_json
```

**Queues are unbounded** (CEO decision #6). Pipelines emit <100 events per run. Memory per 100 connections: ~300KB + buffered events (trivial).

### Heartbeat (CEO-Resolved: JSON Application-Level)
**Source:** step-1 section 5 (ping frames), step-2 section 5 (JSON), CEO decision #1

JSON heartbeat chosen. Format: `{"type": "heartbeat", "timestamp": "2026-02-20T12:00:30+00:00"}`

Rationale: client-visible (JS WebSocket API doesn't expose protocol-level ping/pong), lets UI show "connected, waiting for events...", works reliably across all browsers and proxies.

Implementation: `asyncio.wait_for(queue.get(), timeout=30.0)` -- on TimeoutError, send heartbeat JSON and continue loop.

### Batch Replay (Validated)
**Source:** step-1 section 6, step-2 section 6

For completed/failed runs: query `PipelineEventRecord` ordered by timestamp, send each as JSON, then send `{"type": "replay_complete", "run_status": "<status>", "event_count": N}` and close.

DB access via `asyncio.to_thread()` with manual `Session(engine)` (CEO-aligned with step-2 recommendation). Engine accessed via `websocket.app.state.engine`.

### Close Codes (CEO-Resolved: 4004)
**Source:** step-1 (4004), step-2 (1008), CEO decision #4

- Run not found: `close(4004)` -- custom code in application-use range (4000-4999), mimics HTTP 404
- Normal closure (replay/stream complete): `close(1000)`
- Internal error: `close(1011)`

### Control Messages (CEO-Resolved: Separate Names)
**Source:** step-1 (separate), step-2 (unified), CEO decision #5

| Message | When | Format |
|---------|------|--------|
| Heartbeat | No events for 30s | `{"type": "heartbeat", "timestamp": "..."}` |
| Replay complete | After batch replay | `{"type": "replay_complete", "run_status": "...", "event_count": N}` |
| Stream complete | Live run finishes | `{"type": "stream_complete", "run_id": "..."}` |
| Error | Run not found | `{"type": "error", "detail": "Run not found"}` |

Pipeline events use `"event_type"` key (from `to_dict()`). Control messages use `"type"` key. No overlap.

### Concurrency (NFR-003: 100+ Connections)
**Source:** step-1 section 7, step-2 section 13

- asyncio handles 10K+ coroutines; 100 connections is trivial
- Memory: ~3KB per connection + buffered events; 100 clients = ~300KB
- Broadcasting: `put_nowait` into N queues per event; each WS handler sends independently (no head-of-line blocking)
- Single Uvicorn worker required for in-process state sharing (Redis pub/sub if multi-worker needed later)

### Testing Strategy (Validated)
**Source:** step-1 section 8, step-2 section 10

**Sync TestClient sufficient for:**
1. Batch replay (completed run): connect, receive 4 events + replay_complete, verify close
2. Batch replay (failed run): connect, receive 0 events + replay_complete
3. Error (unknown run): connect, receive error, verify close code
4. Live streaming: connect to running run, inject events into client queue from test code, verify receipt
5. Multiple clients: two TestClient WS connections to same run, verify both receive events

**Live streaming test approach:** After `websocket_connect()`, access `manager._queues` or `manager._connections` from test code to inject events via `put_nowait`. No pytest-asyncio needed.

**Heartbeat testing:** Reduce `HEARTBEAT_INTERVAL_S` via monkeypatch or parameterization for fast tests. Verify heartbeat JSON received after timeout.

**Fixture extensions needed:** Existing `seeded_app_client` already has RUN_3 with `status="running"` -- usable for live streaming tests. RUN_2 (`status="failed"`) has 0 events -- good edge case for empty replay.

### Files to Create/Modify
**Source:** step-1 section 11, validated

| File | Action | Purpose |
|------|--------|---------|
| `llm_pipeline/ui/routes/websocket.py` | Rewrite | ConnectionManager class, WS endpoint, public API |
| `tests/ui/test_websocket.py` | Create | Connection lifecycle, replay, live stream, error tests |
| `tests/ui/conftest.py` | Possibly extend | Additional seed data if needed (RUN_3 already seeded) |

**No changes needed to:** `app.py` (ws_router already mounted), `events/` (unchanged), `state.py` (unchanged), `pyproject.toml` (no new deps).

### Interface for Task 26 (UIBridge) -- OUT OF SCOPE but Defined
**Source:** step-1 section 10, task 26 description

Task 25 exposes from `llm_pipeline/ui/routes/websocket.py`:
```python
manager = ConnectionManager()  # singleton

# Task 26 imports and calls (via asyncio.run_coroutine_threadsafe):
# manager.broadcast_to_run(run_id, event_dict)  -> fan-out to all client queues
# manager.signal_run_complete(run_id)            -> sentinel to all client queues
```

Task 26 is responsible for: capturing event loop reference, calling `asyncio.run_coroutine_threadsafe()`, creating UIBridge as PipelineEventEmitter, hooking into pipeline execution in `trigger_run`.

---

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Heartbeat: JSON app-level vs WebSocket ping frames? | JSON heartbeat `{"type": "heartbeat"}` | Client can distinguish "no events" from "connection dropped". Avoids Starlette version-dependent ping frame behavior. |
| Connection management: class-based vs module-level dicts? | Class-based `ConnectionManager` | Better testability (inject/reset in tests), cleaner encapsulation, matches FastAPI documented patterns. |
| Per-client queue fan-out (deviates from task spec single-queue)? | Yes, per-client queues | Task spec single-queue is broken for multi-client (only one consumer gets each event). Per-client fan-out required for NFR-003 (100+ connections). |
| Close code for "run not found": 4004 vs 1008? | 4004 (custom, mimics HTTP 404) | Within RFC 6455 application-use range (4000-4999). Intuitive for developers. |
| Completion message naming: separate vs unified? | Separate: `replay_complete` / `stream_complete` | Client can distinguish replay from live mode without tracking connection state. |
| Queue bounding: unbounded vs bounded at 1000? | Unbounded | Pipelines emit <100 events per run. Bounded adds drop-policy complexity for no real benefit at this scale. |
| Shutdown cleanup handler in Task 25? | Defer to later task | No lifespan pattern in codebase yet. Uvicorn handles connection teardown on process exit. |

---

## Assumptions Validated

- [x] WebSocket stub exists and is already mounted without /api prefix (confirmed: `app.py` line 80)
- [x] PipelineRun.status values are exactly "running", "completed", "failed" (confirmed: `state.py` field definition + seed data)
- [x] PipelineEventRecord.event_data is a JSON dict matching PipelineEvent.to_dict() format (confirmed: `models.py` + seed data)
- [x] PipelineEventRecord table has index on run_id for efficient queries (confirmed: `ix_pipeline_events_run_event`)
- [x] Pipeline execution is entirely synchronous, dispatched via BackgroundTasks (confirmed: `runs.py` `trigger_run`)
- [x] PipelineEventEmitter Protocol is sync `emit(event) -> None` (confirmed: `emitter.py`)
- [x] No async code exists anywhere in llm_pipeline/ source (confirmed: grep returned 0 files)
- [x] fastapi>=0.100 already in deps, includes WebSocket support (confirmed: `pyproject.toml`)
- [x] No new runtime dependencies required (confirmed: fastapi/starlette handle WebSocket)
- [x] TestClient.websocket_connect() available from starlette (confirmed: starlette in test deps via fastapi)
- [x] Seeded test data includes running run (RUN_3) for live stream tests (confirmed: `conftest.py` line 91-99)
- [x] Seeded test data includes completed run (RUN_1) with 4 events for replay tests (confirmed: `conftest.py` lines 142-176)
- [x] Seeded test data includes failed run (RUN_2) with 0 events for empty replay edge case (confirmed: `conftest.py` line 82-89)
- [x] Engine accessible via `websocket.app.state.engine` in WS handlers (confirmed: `app.py` sets `app.state.engine`)
- [x] Single Uvicorn worker assumption valid for in-process state sharing (documented as constraint)
- [x] asyncio event loop thread safety: all ConnectionManager mutations from async context only (no Lock needed)
- [x] `broadcast_to_run` and `signal_run_complete` are sync (use `put_nowait`, not `await`) -- callable from event loop thread

---

## Open Items

- Authentication/authorization for WS endpoint deferred (consistent with REST endpoints having no auth)
- No hard connection limit enforcement (NFR says 100+, no max cap discussed). Acceptable for now; add limit if needed.
- Shutdown cleanup handler deferred per CEO decision (no lifespan pattern in codebase yet)
- Multi-worker support deferred (Redis pub/sub needed; single Uvicorn worker sufficient for 100 connections)
- Race condition: client connects while run transitions completed -> client sees "running" but gets no events. Mitigation: client reconnects and gets replay. Acceptable risk.
- `pytest-asyncio` not added to dev deps. If sync TestClient proves insufficient for edge case tests (concurrent timeouts), revisit.

---

## Recommendations for Planning

1. **Rewrite `websocket.py` as single file** containing `ConnectionManager` class, private helpers (`_get_run_status`, `_get_persisted_events`), the WS endpoint, and module-level `manager` singleton. No need for separate files.
2. **DB access via `asyncio.to_thread()`** for `_get_run_status` and `_get_persisted_events` to avoid blocking the event loop, even though SQLite queries are fast.
3. **ConnectionManager methods `broadcast_to_run` and `signal_run_complete` must be sync** (use `put_nowait`) so Task 26 can call them via `asyncio.run_coroutine_threadsafe()` wrapping a simple sync call. The `connect` and `disconnect` methods can also be sync since they only mutate dicts.
4. **Test live streaming by directly accessing `manager`** from test code: after `websocket_connect()`, use `manager.broadcast_to_run()` and `manager.signal_run_complete()` to inject events. Avoids needing pytest-asyncio.
5. **Monkeypatch `HEARTBEAT_INTERVAL_S`** to a small value (e.g., 0.5s) in heartbeat tests to avoid slow test suites.
6. **Use existing seeded fixtures** -- RUN_1 (completed, 4 events), RUN_2 (failed, 0 events), RUN_3 (running) cover all three connection paths.
7. **Ensure `_stream_events` helper is a separate async function** (not inlined in endpoint) for unit-testability of the event loop logic.
8. **Document the `manager` singleton as the public API** that Task 26 will import. Keep the interface minimal: `broadcast_to_run(run_id, event_dict)` and `signal_run_complete(run_id)`.
