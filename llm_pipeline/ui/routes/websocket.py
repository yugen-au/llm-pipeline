"""WebSocket route module for real-time pipeline event streaming."""
import asyncio
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
    """Per-client asyncio.Queue fan-out for WebSocket connections.

    Each connected client gets its own Queue. broadcast_to_run and
    signal_run_complete are sync (put_nowait) so they can be called
    from sync pipeline code.
    """

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def connect(self, run_id: str, ws: WebSocket) -> asyncio.Queue:
        """Register a client, return its dedicated event queue."""
        queue: asyncio.Queue = asyncio.Queue()
        self._connections[run_id].append(ws)
        self._queues[run_id].append(queue)
        return queue

    def disconnect(self, run_id: str, ws: WebSocket, queue: Optional[asyncio.Queue]) -> None:
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


async def _stream_events(websocket: WebSocket, queue: asyncio.Queue, run_id: str) -> None:
    """Stream live events from queue with heartbeat on inactivity."""
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_S)
        except asyncio.TimeoutError:
            await websocket.send_json({
                "type": "heartbeat",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            continue
        if event is None:
            await websocket.send_json({"type": "stream_complete", "run_id": run_id})
            break
        await websocket.send_json(event)


@router.websocket("/ws/runs/{run_id}")
async def websocket_endpoint(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint for real-time pipeline event streaming.

    - Completed/failed runs: batch replay of persisted events then close.
    - Running runs: live stream via ConnectionManager queue fan-out.
    - Unknown run_id: error message then close with 4004.
    """
    await websocket.accept()
    queue: Optional[asyncio.Queue] = None
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
