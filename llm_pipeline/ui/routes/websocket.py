"""WebSocket route module for real-time pipeline event streaming.

Single unified endpoint at /ws/runs. Clients subscribe/unsubscribe to
individual run_id streams via JSON messages. Global broadcasts
(run_created) go to all connected clients.
"""
import asyncio
import json
import logging
import queue as thread_queue
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from llm_pipeline.state import PipelineRun

router = APIRouter(tags=["websocket"])
logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S: float = 30.0


class ConnectionManager:
    """Per-client queue fan-out with run-level subscriptions.

    Each connected client gets one Queue. Clients subscribe to run_ids
    to receive per-run pipeline events. Global broadcasts (run_created)
    go to every connected client.

    broadcast_to_run and signal_run_complete are sync (put_nowait) so
    they can be called from sync pipeline code.
    """

    def __init__(self) -> None:
        # ws -> queue mapping for all connected clients
        self._client_queues: dict[int, thread_queue.Queue] = {}
        # ws id -> set of subscribed run_ids
        self._subscriptions: dict[int, set[str]] = defaultdict(set)
        # run_id -> set of ws ids subscribed
        self._run_subscribers: dict[str, set[int]] = defaultdict(set)
        # ws id -> WebSocket (for reference)
        self._websockets: dict[int, WebSocket] = {}

    def connect(self, ws: WebSocket) -> thread_queue.Queue:
        """Register a client, return its dedicated event queue."""
        ws_id = id(ws)
        q: thread_queue.Queue = thread_queue.Queue()
        self._client_queues[ws_id] = q
        self._websockets[ws_id] = ws
        return q

    def disconnect(self, ws: WebSocket) -> None:
        """Unregister a client and all its subscriptions."""
        ws_id = id(ws)
        # Remove from all run subscriptions
        for run_id in list(self._subscriptions.get(ws_id, [])):
            subs = self._run_subscribers.get(run_id)
            if subs:
                subs.discard(ws_id)
                if not subs:
                    del self._run_subscribers[run_id]
        self._subscriptions.pop(ws_id, None)
        self._client_queues.pop(ws_id, None)
        self._websockets.pop(ws_id, None)

    def subscribe(self, ws: WebSocket, run_id: str) -> None:
        """Subscribe a client to events for a specific run."""
        ws_id = id(ws)
        self._subscriptions[ws_id].add(run_id)
        self._run_subscribers[run_id].add(ws_id)

    def unsubscribe(self, ws: WebSocket, run_id: str) -> None:
        """Unsubscribe a client from events for a specific run."""
        ws_id = id(ws)
        subs = self._subscriptions.get(ws_id)
        if subs:
            subs.discard(run_id)
        run_subs = self._run_subscribers.get(run_id)
        if run_subs:
            run_subs.discard(ws_id)
            if not run_subs:
                del self._run_subscribers[run_id]

    def is_subscribed(self, ws: WebSocket, run_id: str) -> bool:
        """Check if a client is subscribed to a run."""
        return run_id in self._subscriptions.get(id(ws), set())

    def broadcast_to_run(self, run_id: str, event_data: dict) -> None:
        """Fan-out an event dict to every client subscribed to this run. Sync."""
        for ws_id in list(self._run_subscribers.get(run_id, [])):
            q = self._client_queues.get(ws_id)
            if q:
                q.put_nowait(event_data)

    def signal_run_complete(self, run_id: str) -> None:
        """Send (run_id, None) sentinel to every client subscribed to this run. Sync."""
        for ws_id in list(self._run_subscribers.get(run_id, [])):
            q = self._client_queues.get(ws_id)
            if q:
                q.put_nowait((_SENTINEL_RUN_COMPLETE, run_id))

    def broadcast_global(self, event_data: dict) -> None:
        """Fan-out an event dict to every connected client. Sync, thread-safe."""
        for q in list(self._client_queues.values()):
            q.put_nowait(event_data)


# Sentinel marker to distinguish run-complete from regular events
_SENTINEL_RUN_COMPLETE = object()

manager = ConnectionManager()


async def _get_run(engine, run_id: str) -> Optional[PipelineRun]:
    """Fetch a PipelineRun by run_id without blocking the event loop."""
    def _query():
        with Session(engine) as session:
            stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
            return session.exec(stmt).first()
    return await asyncio.to_thread(_query)


async def _build_stream_complete(engine, run_id: str) -> dict:
    """Build enriched stream_complete message with run state from DB."""
    run = await _get_run(engine, run_id)
    msg: dict = {"type": "stream_complete", "run_id": run_id}
    if run:
        msg["status"] = run.status
        msg["completed_at"] = run.completed_at.isoformat() if run.completed_at else None
        msg["total_time_ms"] = run.total_time_ms
        msg["step_count"] = run.step_count
    return msg


async def _handle_subscribe(ws: WebSocket, run_id: str, engine) -> None:
    """Handle a subscribe request: replay persisted events, then stream live."""
    manager.subscribe(ws, run_id)

    run = await _get_run(engine, run_id)
    if run is None:
        await ws.send_json({"type": "error", "detail": "Run not found", "run_id": run_id})
        manager.unsubscribe(ws, run_id)
        return

    if run.status in ("completed", "failed"):
        # Past traces live in Langfuse, not in the local DB. The UI's
        # run-detail page surfaces them by linking to the Langfuse trace
        # URL — no replay needed here.
        await ws.send_json({
            "type": "replay_complete",
            "run_id": run_id,
            "run_status": run.status,
            "event_count": 0,
        })


@router.websocket("/ws/runs")
async def unified_websocket_endpoint(websocket: WebSocket) -> None:
    """Unified WebSocket endpoint for all pipeline event streaming.

    Clients send JSON messages to subscribe/unsubscribe from runs:
      {"action": "subscribe", "run_id": "xxx"}
      {"action": "unsubscribe", "run_id": "xxx"}

    Server sends:
      - run_created: broadcast to ALL clients
      - pipeline events: only to subscribers of that run_id
      - stream_complete: enriched with run state, to subscribers only
      - replay_complete: after replaying persisted events for completed runs
      - heartbeat: periodic keep-alive
    """
    await websocket.accept()
    q: thread_queue.Queue = manager.connect(websocket)

    # Task for draining the queue (events from pipeline threads)
    async def drain_queue():
        while True:
            try:
                item = await asyncio.to_thread(q.get, True, HEARTBEAT_INTERVAL_S)
            except thread_queue.Empty:
                await websocket.send_json({
                    "type": "heartbeat",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                continue

            # Run-complete sentinel
            if isinstance(item, tuple) and len(item) == 2 and item[0] is _SENTINEL_RUN_COMPLETE:
                run_id = item[1]
                try:
                    engine = websocket.app.state.engine
                    msg = await _build_stream_complete(engine, run_id)
                except Exception:
                    msg = {"type": "stream_complete", "run_id": run_id}
                await websocket.send_json(msg)
                continue

            # Regular event or global broadcast
            await websocket.send_json(item)

    # Task for receiving client messages (subscribe/unsubscribe)
    async def receive_messages():
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            action = msg.get("action")
            run_id = msg.get("run_id")
            if not action or not run_id:
                continue

            engine = websocket.app.state.engine

            if action == "subscribe":
                await _handle_subscribe(websocket, run_id, engine)
            elif action == "unsubscribe":
                manager.unsubscribe(websocket, run_id)

    try:
        # Run both tasks concurrently; if either fails, we cancel both
        drain_task = asyncio.create_task(drain_queue())
        recv_task = asyncio.create_task(receive_messages())
        done, pending = await asyncio.wait(
            [drain_task, recv_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        # Re-raise if a task failed with a non-disconnect exception
        for task in done:
            exc = task.exception()
            if exc and not isinstance(exc, WebSocketDisconnect):
                raise exc
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(1011)
        except Exception:
            pass
    finally:
        manager.disconnect(websocket)
