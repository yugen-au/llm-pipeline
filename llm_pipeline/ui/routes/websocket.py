"""WebSocket route module for real-time pipeline event streaming."""
import asyncio
import queue as thread_queue
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import Session, select

from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.state import PipelineRun

router = APIRouter(tags=["websocket"])

HEARTBEAT_INTERVAL_S: float = 30.0


class ConnectionManager:
    """Per-client threading.Queue fan-out for WebSocket connections.

    Each connected client gets its own Queue. broadcast_to_run and
    signal_run_complete are sync (put_nowait) so they can be called
    from sync pipeline code.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._queues: dict[str, list[thread_queue.Queue]] = defaultdict(list)
        self._global_queues: list[thread_queue.Queue] = []

    def connect(self, run_id: str, ws: WebSocket) -> thread_queue.Queue:
        """Register a client, return its dedicated event queue."""
        queue: thread_queue.Queue = thread_queue.Queue()
        self._connections[run_id].append(ws)
        self._queues[run_id].append(queue)
        return queue

    def disconnect(self, run_id: str, ws: WebSocket, queue: Optional[thread_queue.Queue]) -> None:
        """Unregister a client. Safe to call even if never connected."""
        conns = self._connections.get(run_id)
        if conns and ws in conns:
            conns.remove(ws)
        if queue is not None:
            queues = self._queues.get(run_id)
            if queues and queue in queues:
                queues.remove(queue)
        # Clean up empty keys
        if run_id in self._connections and not self._connections[run_id]:
            del self._connections[run_id]
        if run_id in self._queues and not self._queues[run_id]:
            del self._queues[run_id]

    def broadcast_to_run(self, run_id: str, event_data: dict) -> None:
        """Fan-out an event dict to every client watching this run. Sync."""
        for q in self._queues.get(run_id, []):
            q.put_nowait(event_data)

    def signal_run_complete(self, run_id: str) -> None:
        """Send None sentinel to every client watching this run. Sync."""
        for q in self._queues.get(run_id, []):
            q.put_nowait(None)

    # -- Global subscriber support (for /ws/runs broadcast) --

    def connect_global(self, ws: WebSocket) -> thread_queue.Queue:
        """Register a global subscriber, return its dedicated event queue."""
        queue: thread_queue.Queue = thread_queue.Queue()
        self._global_queues.append(queue)
        return queue

    def disconnect_global(self, queue: thread_queue.Queue) -> None:
        """Unregister a global subscriber. Safe if not present."""
        try:
            self._global_queues.remove(queue)
        except ValueError:
            pass

    def broadcast_global(self, event_data: dict) -> None:
        """Fan-out an event dict to every global subscriber. Sync, thread-safe."""
        for q in self._global_queues:
            q.put_nowait(event_data)


manager = ConnectionManager()


async def _get_run(engine, run_id: str) -> Optional[PipelineRun]:
    """Fetch a PipelineRun by run_id without blocking the event loop."""
    def _query():
        with Session(engine) as session:
            stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
            return session.exec(stmt).first()
    return await asyncio.to_thread(_query)


async def _get_persisted_events(engine, run_id: str) -> list[dict]:
    """Fetch persisted events for a run, ordered by timestamp."""
    def _query():
        with Session(engine) as session:
            stmt = (
                select(PipelineEventRecord)
                .where(PipelineEventRecord.run_id == run_id)
                .order_by(PipelineEventRecord.timestamp)
            )
            return [record.event_data for record in session.exec(stmt).all()]
    return await asyncio.to_thread(_query)


async def _stream_events(websocket: WebSocket, queue: thread_queue.Queue, run_id: str) -> None:
    """Stream live events from queue with heartbeat on inactivity."""
    while True:
        try:
            event = await asyncio.to_thread(queue.get, True, HEARTBEAT_INTERVAL_S)
        except thread_queue.Empty:
            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue
        if event is None:
            await websocket.send_json({"type": "stream_complete", "run_id": run_id})
            break
        await websocket.send_json(event)


@router.websocket("/ws/runs")
async def global_websocket_endpoint(websocket: WebSocket) -> None:
    """Global WebSocket endpoint for run-creation notifications.

    Streams run_created events to connected clients so the UI can
    auto-detect Python-initiated runs. Never sends a None sentinel;
    heartbeats keep the connection alive until the client disconnects.
    """
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
            # Global stream ignores None sentinel (no terminal event)
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
    """WebSocket endpoint for real-time pipeline event streaming.

    - Completed/failed runs: batch replay of persisted events then close.
    - Running runs: live stream via ConnectionManager queue fan-out.
    - Unknown run_id: error message then close with 4004.
    """
    await websocket.accept()
    queue: Optional[thread_queue.Queue] = None
    try:
        engine = websocket.app.state.engine

        run = await _get_run(engine, run_id)
        if run is None:
            await websocket.send_json({"type": "error", "detail": "Run not found"})
            await websocket.close(4004)
            return

        if run.status in ("completed", "failed"):
            events = await _get_persisted_events(engine, run_id)
            for event_data in events:
                await websocket.send_json(event_data)
            await websocket.send_json({
                "type": "replay_complete",
                "run_status": run.status,
                "event_count": len(events),
            })
            await websocket.close(1000)
            return

        # Running run - live stream
        queue = manager.connect(run_id, websocket)
        await _stream_events(websocket, queue, run_id)

    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close(1011)
        except Exception:
            pass
    finally:
        manager.disconnect(run_id, websocket, queue)
