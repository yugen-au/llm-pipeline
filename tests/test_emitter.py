"""Tests for PipelineEventEmitter Protocol and CompositeEmitter dispatcher."""
import threading
from unittest.mock import MagicMock, Mock, patch

import pytest

from llm_pipeline.events.emitter import CompositeEmitter, PipelineEventEmitter
from llm_pipeline.events.types import PipelineEvent, PipelineStarted


# -- Helpers -------------------------------------------------------------------


def _make_event() -> PipelineStarted:
    """Create a minimal concrete PipelineEvent for testing."""
    return PipelineStarted(run_id="run-1", pipeline_name="test-pipeline")


# -- PipelineEventEmitter Protocol ---------------------------------------------


class TestPipelineEventEmitter:
    """Protocol isinstance checks via @runtime_checkable."""

    def test_conforming_class_passes_isinstance(self):
        """Object with matching emit(event) method satisfies Protocol."""

        class _Handler:
            def emit(self, event: PipelineEvent) -> None:
                pass

        assert isinstance(_Handler(), PipelineEventEmitter)

    def test_duck_typed_object_passes_isinstance(self):
        """Bare object with emit function attribute satisfies Protocol."""
        handler = type("_DuckHandler", (), {"emit": lambda self, event: None})()
        assert isinstance(handler, PipelineEventEmitter)

    def test_non_conforming_object_fails_isinstance(self):
        """Object without emit method does NOT satisfy Protocol."""

        class _NoEmit:
            pass

        assert not isinstance(_NoEmit(), PipelineEventEmitter)

    def test_wrong_name_fails_isinstance(self):
        """Object with differently-named method does NOT satisfy Protocol."""

        class _WrongName:
            def send(self, event: PipelineEvent) -> None:
                pass

        assert not isinstance(_WrongName(), PipelineEventEmitter)


# -- CompositeEmitter ----------------------------------------------------------


class TestCompositeEmitterInstantiation:
    """Construction with various handler lists."""

    def test_empty_handlers(self):
        emitter = CompositeEmitter(handlers=[])
        assert repr(emitter) == "CompositeEmitter(handlers=0)"

    def test_single_handler(self):
        handler = Mock(spec=["emit"])
        emitter = CompositeEmitter(handlers=[handler])
        assert repr(emitter) == "CompositeEmitter(handlers=1)"

    def test_multiple_handlers(self):
        handlers = [Mock(spec=["emit"]) for _ in range(5)]
        emitter = CompositeEmitter(handlers=handlers)
        assert repr(emitter) == "CompositeEmitter(handlers=5)"

    def test_handlers_stored_as_tuple(self):
        """Internal _handlers is a tuple (immutable) regardless of input list."""
        handlers = [Mock(spec=["emit"])]
        emitter = CompositeEmitter(handlers=handlers)
        assert isinstance(emitter._handlers, tuple)


class TestCompositeEmitterEmit:
    """Dispatch behavior: all handlers called in order with same event."""

    def test_all_handlers_called(self):
        h1, h2, h3 = Mock(), Mock(), Mock()
        emitter = CompositeEmitter(handlers=[h1, h2, h3])
        event = _make_event()

        emitter.emit(event)

        h1.emit.assert_called_once_with(event)
        h2.emit.assert_called_once_with(event)
        h3.emit.assert_called_once_with(event)

    def test_handlers_called_in_order(self):
        """Handlers invoked sequentially in insertion order."""
        call_order: list[int] = []
        h1 = Mock(side_effect=lambda e: call_order.append(1))
        h2 = Mock(side_effect=lambda e: call_order.append(2))
        h3 = Mock(side_effect=lambda e: call_order.append(3))
        # Mock.emit needs to be the callable
        h1.emit = h1
        h2.emit = h2
        h3.emit = h3

        emitter = CompositeEmitter(handlers=[h1, h2, h3])
        emitter.emit(_make_event())

        assert call_order == [1, 2, 3]

    def test_emit_with_no_handlers(self):
        """Emit on empty handler list does nothing, no error."""
        emitter = CompositeEmitter(handlers=[])
        emitter.emit(_make_event())  # should not raise


class TestCompositeEmitterErrorIsolation:
    """Per-handler exception isolation: failing handler does not block others."""

    def test_failing_handler_does_not_block_others(self):
        h1 = Mock()
        h2 = Mock()
        h2.emit.side_effect = RuntimeError("boom")
        h3 = Mock()

        emitter = CompositeEmitter(handlers=[h1, h2, h3])
        event = _make_event()

        emitter.emit(event)

        h1.emit.assert_called_once_with(event)
        h2.emit.assert_called_once_with(event)
        h3.emit.assert_called_once_with(event)

    @patch("llm_pipeline.events.emitter.logger")
    def test_logger_exception_called(self, mock_logger):
        """logger.exception called with handler repr and event_type context."""
        h1 = Mock()
        h1.emit.side_effect = ValueError("test error")
        h1.__repr__ = lambda self: "<FailingHandler>"

        emitter = CompositeEmitter(handlers=[h1])
        event = _make_event()
        emitter.emit(event)

        mock_logger.exception.assert_called_once()
        args = mock_logger.exception.call_args
        log_msg = args[0][0]  # format string
        assert "Handler" in log_msg
        # Handler repr and event_type passed as format args
        assert args[0][1] == h1  # handler (formatted via %r)
        assert args[0][2] == event.event_type  # event_type (formatted via %s)

    @patch("llm_pipeline.events.emitter.logger")
    def test_multiple_failures_all_logged(self, mock_logger):
        """Each failing handler gets its own logger.exception call."""
        h1 = Mock()
        h1.emit.side_effect = RuntimeError("err1")
        h2 = Mock()
        h2.emit.side_effect = TypeError("err2")

        emitter = CompositeEmitter(handlers=[h1, h2])
        emitter.emit(_make_event())

        assert mock_logger.exception.call_count == 2


class TestCompositeEmitterThreadSafety:
    """Concurrent emit calls from multiple threads."""

    def test_concurrent_emit(self):
        """Multiple threads emitting concurrently; all handlers receive all events."""
        num_threads = 10
        events_per_thread = 20
        total_expected = num_threads * events_per_thread

        # Thread-safe counter via list append (GIL-protected)
        received: list[PipelineEvent] = []
        lock = threading.Lock()

        class _SafeHandler:
            def emit(self, event: PipelineEvent) -> None:
                with lock:
                    received.append(event)

        handler = _SafeHandler()
        emitter = CompositeEmitter(handlers=[handler])

        def _worker():
            for _ in range(events_per_thread):
                emitter.emit(_make_event())

        threads = [threading.Thread(target=_worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == total_expected

    def test_concurrent_emit_multiple_handlers(self):
        """Multiple handlers each receive all events from concurrent threads."""
        num_threads = 5
        events_per_thread = 10
        total_expected = num_threads * events_per_thread

        counts = [0, 0]
        lock = threading.Lock()

        class _CountingHandler:
            def __init__(self, idx: int):
                self._idx = idx

            def emit(self, event: PipelineEvent) -> None:
                with lock:
                    counts[self._idx] += 1

        h1, h2 = _CountingHandler(0), _CountingHandler(1)
        emitter = CompositeEmitter(handlers=[h1, h2])

        def _worker():
            for _ in range(events_per_thread):
                emitter.emit(_make_event())

        threads = [threading.Thread(target=_worker) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counts[0] == total_expected
        assert counts[1] == total_expected


class TestCompositeEmitterRepr:
    """__repr__ format verification."""

    def test_repr_format(self):
        handlers = [Mock(spec=["emit"]) for _ in range(3)]
        emitter = CompositeEmitter(handlers=handlers)
        assert repr(emitter) == "CompositeEmitter(handlers=3)"

    def test_repr_empty(self):
        emitter = CompositeEmitter(handlers=[])
        assert repr(emitter) == "CompositeEmitter(handlers=0)"


class TestCompositeEmitterSlots:
    """__slots__ enforcement."""

    def test_slots_defined(self):
        assert hasattr(CompositeEmitter, "__slots__")
        assert "_handlers" in CompositeEmitter.__slots__

    def test_cannot_add_arbitrary_attributes(self):
        """__slots__ prevents setting attributes not in __slots__."""
        emitter = CompositeEmitter(handlers=[])
        with pytest.raises(AttributeError):
            emitter.arbitrary_attr = "nope"
