"""Sync adapter bridging pipeline events to WebSocket clients.

UIBridge implements :class:`~llm_pipeline.events.emitter.PipelineEventEmitter`
and delegates each ``emit()`` call to
:meth:`ConnectionManager.broadcast_to_run() <llm_pipeline.ui.routes.websocket.ConnectionManager.broadcast_to_run>`,
which enqueues the serialized event dict onto every client's
:class:`queue.Queue` via ``put_nowait()``.

**Spec deviation (task 26):** The original task spec prescribes
``asyncio.Queue`` and ``asyncio.run_coroutine_threadsafe()``.  Task 25
shipped ``threading.Queue`` with sync ``put_nowait`` methods on
ConnectionManager, so no asyncio bridging is needed.  UIBridge is purely
synchronous.

**Threading model:** Pipeline execution runs in a
:class:`~starlette.background.BackgroundTasks` threadpool worker.
``emit()`` calls ``put_nowait()`` on stdlib ``queue.Queue`` which is
thread-safe by design.  The ``_completed`` flag is only accessed from the
single pipeline thread (CompositeEmitter dispatches sequentially), so no
additional locking is required.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from llm_pipeline.events.types import PipelineCompleted, PipelineError, PipelineEvent

if TYPE_CHECKING:
    from llm_pipeline.ui.routes.websocket import ConnectionManager

logger = logging.getLogger(__name__)


class UIBridge:
    """Thin sync adapter forwarding pipeline events to WebSocket clients.

    Satisfies :class:`~llm_pipeline.events.emitter.PipelineEventEmitter`
    (runtime-checkable Protocol) via duck typing -- provides a conforming
    ``emit(event) -> None`` method.

    Terminal events (:class:`PipelineCompleted`, :class:`PipelineError`)
    automatically trigger :meth:`complete`, which sends the ``None``
    sentinel via :meth:`ConnectionManager.signal_run_complete`.  An
    idempotent ``_completed`` guard ensures the sentinel is sent at most
    once per bridge instance.
    """

    __slots__ = ("run_id", "_manager", "_completed")

    def __init__(
        self,
        run_id: str,
        manager: ConnectionManager | None = None,
    ) -> None:
        self.run_id = run_id
        if manager is None:
            # Lazy import to avoid circular imports at module level
            from llm_pipeline.ui.routes.websocket import (
                manager as _singleton,
            )

            manager = _singleton
        self._manager: ConnectionManager = manager
        self._completed: bool = False

    def emit(self, event: PipelineEvent) -> None:
        """Serialize *event* and broadcast to all WebSocket clients for this run.

        If *event* is a terminal type (:class:`PipelineCompleted` or
        :class:`PipelineError`), :meth:`complete` is called automatically.
        """
        self._manager.broadcast_to_run(self.run_id, event.to_dict())
        if isinstance(event, (PipelineCompleted, PipelineError)):
            self.complete()

    def complete(self) -> None:
        """Signal run completion to all connected clients (idempotent).

        Safe to call multiple times -- the ``None`` sentinel is sent at
        most once.  Intended as both an auto-detect hook (called from
        :meth:`emit` on terminal events) and an explicit safety net
        (called from ``trigger_run``'s ``finally`` block).
        """
        if not self._completed:
            self._completed = True
            self._manager.signal_run_complete(self.run_id)

    def __repr__(self) -> str:
        return f"UIBridge(run_id={self.run_id!r})"


__all__ = ["UIBridge"]
