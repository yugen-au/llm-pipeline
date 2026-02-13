"""Pipeline event handler implementations.

Concrete :class:`~llm_pipeline.events.emitter.PipelineEventEmitter` handlers
for logging, in-memory storage, and database persistence.

No internal error handling: exceptions propagate to
:class:`~llm_pipeline.events.emitter.CompositeEmitter` which isolates
per-handler failures.
"""

import logging
import threading
from typing import TYPE_CHECKING

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel

from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.events.types import (
    CATEGORY_CACHE,
    CATEGORY_CONSENSUS,
    CATEGORY_EXTRACTION,
    CATEGORY_INSTRUCTIONS_CONTEXT,
    CATEGORY_LLM_CALL,
    CATEGORY_PIPELINE_LIFECYCLE,
    CATEGORY_STATE,
    CATEGORY_STEP_LIFECYCLE,
    CATEGORY_TRANSFORMATION,
)

if TYPE_CHECKING:
    from llm_pipeline.events.types import PipelineEvent

DEFAULT_LEVEL_MAP: dict[str, int] = {
    # Lifecycle-significant events at INFO
    CATEGORY_PIPELINE_LIFECYCLE: logging.INFO,
    CATEGORY_STEP_LIFECYCLE: logging.INFO,
    CATEGORY_LLM_CALL: logging.INFO,
    CATEGORY_CONSENSUS: logging.INFO,
    # Implementation details at DEBUG
    CATEGORY_CACHE: logging.DEBUG,
    CATEGORY_INSTRUCTIONS_CONTEXT: logging.DEBUG,
    CATEGORY_TRANSFORMATION: logging.DEBUG,
    CATEGORY_EXTRACTION: logging.DEBUG,
    CATEGORY_STATE: logging.DEBUG,
}


class LoggingEventHandler:
    """Log pipeline events via Python logging with category-based levels.

    Uses :data:`DEFAULT_LEVEL_MAP` to resolve log level from the event's
    ``EVENT_CATEGORY`` class variable. Unknown categories fall back to INFO.

    No try/except -- CompositeEmitter handles isolation.
    """

    __slots__ = ("_logger", "_level_map")

    def __init__(
        self,
        logger: logging.Logger | None = None,
        level_map: dict[str, int] | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger(__name__)
        self._level_map = level_map if level_map is not None else DEFAULT_LEVEL_MAP

    def emit(self, event: "PipelineEvent") -> None:
        category: str = getattr(type(event), "EVENT_CATEGORY", "unknown")
        level = self._level_map.get(category, logging.INFO)
        self._logger.log(
            level,
            "%s: %s - %s",
            event.event_type,
            event.pipeline_name,
            event.run_id,
            extra={"event_data": event.to_dict()},
        )

    def __repr__(self) -> str:
        return f"LoggingEventHandler(logger={self._logger.name})"


class InMemoryEventHandler:
    """Thread-safe in-memory event store for UI/testing use cases.

    Events are stored as dicts (via ``PipelineEvent.to_dict()``) in an
    internal list protected by a :class:`threading.Lock`.  Query methods
    return copies so callers cannot mutate the internal store.

    Example::

        handler = InMemoryEventHandler()
        emitter = CompositeEmitter(handlers=[handler])
        emitter.emit(some_event)
        events = handler.get_events(run_id="abc-123")
    """

    __slots__ = ("_events", "_lock")

    def __init__(self) -> None:
        self._events: list[dict] = []
        self._lock = threading.Lock()

    def emit(self, event: "PipelineEvent") -> None:
        """Append serialised event to internal store."""
        with self._lock:
            self._events.append(event.to_dict())

    def get_events(self, run_id: str | None = None) -> list[dict]:
        """Return stored events, optionally filtered by *run_id*.

        Returns a shallow copy; callers may mutate the returned list
        without affecting the internal store.
        """
        with self._lock:
            snapshot = list(self._events)
        if run_id is None:
            return snapshot
        return [e for e in snapshot if e.get("run_id") == run_id]

    def get_events_by_type(
        self, event_type: str, run_id: str | None = None
    ) -> list[dict]:
        """Return events matching *event_type*, optionally filtered by *run_id*."""
        return [
            e for e in self.get_events(run_id) if e.get("event_type") == event_type
        ]

    def clear(self) -> None:
        """Remove all stored events."""
        with self._lock:
            self._events.clear()

    def __repr__(self) -> str:
        return f"InMemoryEventHandler(events={len(self._events)})"


class SQLiteEventHandler:
    """Persist pipeline events to a SQLite ``pipeline_events`` table.

    Uses a session-per-emit pattern: a new :class:`sqlmodel.Session` is
    created for each :meth:`emit` call and closed in a ``finally`` block
    to prevent session leaks.

    Table creation is idempotent -- :meth:`SQLModel.metadata.create_all`
    is called with an explicit ``tables`` list so it never conflicts with
    existing pipeline DB initialisation.

    No try/except beyond session cleanup -- CompositeEmitter handles
    isolation.
    """

    __slots__ = ("_engine",)

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        SQLModel.metadata.create_all(
            engine, tables=[PipelineEventRecord.__table__]
        )

    def emit(self, event: "PipelineEvent") -> None:
        """Persist a single event as a :class:`PipelineEventRecord` row."""
        session = Session(self._engine)
        try:
            record = PipelineEventRecord(
                run_id=event.run_id,
                event_type=event.event_type,
                pipeline_name=event.pipeline_name,
                timestamp=event.timestamp,
                event_data=event.to_dict(),
            )
            session.add(record)
            session.commit()
        finally:
            session.close()

    def __repr__(self) -> str:
        return f"SQLiteEventHandler(engine={self._engine.url})"


__all__ = [
    "DEFAULT_LEVEL_MAP",
    "LoggingEventHandler",
    "InMemoryEventHandler",
    "SQLiteEventHandler",
]
