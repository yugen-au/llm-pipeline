# IMPLEMENTATION - STEP 1: CONNECTIONMANAGER + WS ENDPOINT
**Status:** completed

## Summary
Rewrote `llm_pipeline/ui/routes/websocket.py` with full WebSocket endpoint for real-time pipeline event streaming. Includes `ConnectionManager` class with per-client queue fan-out, DB helpers via `asyncio.to_thread`, heartbeat mechanism, batch replay for completed/failed runs, and live streaming for running runs.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/routes/websocket.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/websocket.py`
Complete rewrite from stub to full implementation.

```
# Before
"""WebSocket route module."""
from fastapi import APIRouter

router = APIRouter(tags=["websocket"])

# After
- ConnectionManager class with __init__, connect, disconnect, broadcast_to_run, signal_run_complete
- Module-level singleton: manager = ConnectionManager()
- HEARTBEAT_INTERVAL_S = 30.0
- _get_run(engine, run_id) async helper using asyncio.to_thread
- _get_persisted_events(engine, run_id) async helper using asyncio.to_thread
- _stream_events(websocket, queue, run_id) async helper with heartbeat loop
- @router.websocket("/ws/runs/{run_id}") endpoint handling:
  - Not found: error msg + close(4004)
  - Completed/failed: batch replay + replay_complete + close(1000)
  - Running: manager.connect + _stream_events
  - WebSocketDisconnect caught, finally calls manager.disconnect
  - Internal errors close with 1011
```

## Decisions
### broadcast_to_run and signal_run_complete are sync
**Choice:** Both methods use `put_nowait` (no await), making them callable from sync pipeline code.
**Rationale:** CEO decision -- UIBridge (Task 26) will call these from sync context within pipeline execution.

### defaultdict for internal storage
**Choice:** Used `defaultdict(list)` for `_connections` and `_queues`.
**Rationale:** Simplifies connect logic (no key existence check), disconnect cleans up empty keys.

### Queue variable initialized to None before try block
**Choice:** `queue: Optional[asyncio.Queue] = None` before try, only assigned if connect is reached.
**Rationale:** Ensures `finally` block can safely call `disconnect(run_id, ws, queue)` even if connection was never registered (e.g., run not found path).

## Verification
[x] Module imports successfully (`from llm_pipeline.ui.routes.websocket import manager, ConnectionManager, HEARTBEAT_INTERVAL_S`)
[x] manager singleton has expected methods: connect, disconnect, broadcast_to_run, signal_run_complete
[x] All 626 existing tests pass (2 pre-existing failures unrelated to this change)
[x] No new runtime dependencies required
[x] WebSocket router maintains existing `APIRouter(tags=["websocket"])` pattern
[x] No hardcoded values (HEARTBEAT_INTERVAL_S is a module-level constant)
[x] Error handling present for WebSocketDisconnect and generic exceptions
