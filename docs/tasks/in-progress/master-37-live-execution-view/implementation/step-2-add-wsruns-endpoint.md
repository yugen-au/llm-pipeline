# IMPLEMENTATION - STEP 2: ADD /WS/RUNS ENDPOINT
**Status:** completed

## Summary
Added global WebSocket endpoint `/ws/runs` that streams run-creation notifications to connected clients. Registered BEFORE `/ws/runs/{run_id}` to avoid path conflict. Uses existing `_stream_events` pattern with heartbeat timeout loop; ignores `None` sentinel since global stream has no terminal event.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/routes/websocket.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/websocket.py`
Added `global_websocket_endpoint` handler at `/ws/runs`, registered before the parameterized `/ws/runs/{run_id}` route (lines 127-161).

```python
# Before (line 127)
@router.websocket("/ws/runs/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:

# After (lines 127-164)
@router.websocket("/ws/runs")
async def global_websocket_endpoint(websocket: WebSocket) -> None:
    """Global WebSocket endpoint for run-creation notifications."""
    await websocket.accept()
    queue: thread_queue.Queue = manager.connect_global(websocket)
    try:
        while True:
            try:
                event = await asyncio.to_thread(
                    queue.get, True, HEARTBEAT_INTERVAL_S
                )
            except thread_queue.Empty:
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue
            if event is None:
                continue
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(1011)
        except Exception:
            pass
    finally:
        manager.disconnect_global(queue)


@router.websocket("/ws/runs/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:
```

## Decisions
### None sentinel handling
**Choice:** `continue` instead of `break` on `None` sentinel
**Rationale:** Global stream has no terminal event -- heartbeats keep connection alive until client disconnects. If a `None` somehow enters the queue, ignoring it is safe.

### Route registration order
**Choice:** `/ws/runs` registered before `/ws/runs/{run_id}` in source order
**Rationale:** FastAPI matches routes in declaration order. Exact path must precede parameterized path to prevent `/ws/runs` from matching as `run_id="runs"`.

## Verification
[x] `/ws/runs` route declared before `/ws/runs/{run_id}` (line 127 vs 164)
[x] `manager.connect_global(websocket)` called after `websocket.accept()`
[x] `manager.disconnect_global(queue)` called in `finally` block
[x] Heartbeat sent on queue timeout (same pattern as `_stream_events`)
[x] `None` sentinel ignored (continue, not break)
[x] `WebSocketDisconnect` handled silently
[x] Error path closes with 1011
[x] Import verification passed: `python -c "from llm_pipeline.ui.routes.websocket import global_websocket_endpoint"`
