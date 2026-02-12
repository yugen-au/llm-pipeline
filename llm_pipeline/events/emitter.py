"""Pipeline event emitter protocol and composite dispatcher.

Defines :class:`PipelineEventEmitter`, a :func:`~typing.runtime_checkable`
Protocol with a single ``emit()`` method for receiving pipeline events.

:class:`CompositeEmitter` dispatches events to multiple handlers sequentially,
isolating per-handler errors so that a failing handler never prevents delivery
to subsequent handlers.
"""

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from llm_pipeline.events.types import PipelineEvent

logger = logging.getLogger(__name__)


@runtime_checkable
class PipelineEventEmitter(Protocol):
    """Protocol for objects that receive pipeline events.

    Any object with a conforming ``emit(event) -> None`` signature satisfies
    this protocol (duck typing).  The ``@runtime_checkable`` decorator allows
    ``isinstance()`` checks at runtime.

    Example::

        class LoggingHandler:
            def emit(self, event: PipelineEvent) -> None:
                print(f"[{event.event_type}] {event.pipeline_name}")

        handler = LoggingHandler()
        assert isinstance(handler, PipelineEventEmitter)

        emitter = CompositeEmitter(handlers=[handler])
        emitter.emit(some_event)
    """

    def emit(self, event: "PipelineEvent") -> None: ...


class CompositeEmitter:
    """Dispatch events to multiple handlers with per-handler error isolation.

    Handlers are stored as an immutable tuple at construction time.
    Each handler's ``emit()`` is called sequentially; if a handler raises
    :class:`Exception`, the error is logged via :func:`logger.exception`
    and dispatch continues to the remaining handlers.
    """

    __slots__ = ("_handlers",)

    def __init__(self, handlers: list[PipelineEventEmitter]) -> None:
        self._handlers: tuple[PipelineEventEmitter, ...] = tuple(handlers)

    def emit(self, event: "PipelineEvent") -> None:
        for handler in self._handlers:
            try:
                handler.emit(event)
            except Exception:
                logger.exception(
                    "Handler %r failed for event %s",
                    handler,
                    event.event_type,
                )

    def __repr__(self) -> str:
        return f"CompositeEmitter(handlers={len(self._handlers)})"


__all__ = ["PipelineEventEmitter", "CompositeEmitter"]
