"""Unit tests for UIBridge - sync adapter bridging pipeline events to WebSocket clients."""
import pytest

from llm_pipeline.events.emitter import PipelineEventEmitter
from llm_pipeline.events.types import (
    PipelineCompleted,
    PipelineError,
    PipelineStarted,
)
from llm_pipeline.ui.bridge import UIBridge


RUN_ID = "test-run-id-1234"
PIPELINE_NAME = "test_pipeline"


# -- Helpers -------------------------------------------------------------------


class _StubManager:
    """Minimal ConnectionManager stub tracking broadcast and signal calls."""

    def __init__(self) -> None:
        self.broadcast_calls: list[tuple[str, dict]] = []
        self.signal_calls: list[str] = []

    def broadcast_to_run(self, run_id: str, event_data: dict) -> None:
        self.broadcast_calls.append((run_id, event_data))

    def signal_run_complete(self, run_id: str) -> None:
        self.signal_calls.append(run_id)


def _make_bridge(run_id: str = RUN_ID) -> tuple[UIBridge, _StubManager]:
    manager = _StubManager()
    bridge = UIBridge(run_id=run_id, manager=manager)
    return bridge, manager


def _make_started() -> PipelineStarted:
    return PipelineStarted(run_id=RUN_ID, pipeline_name=PIPELINE_NAME)


def _make_completed() -> PipelineCompleted:
    return PipelineCompleted(
        run_id=RUN_ID,
        pipeline_name=PIPELINE_NAME,
        execution_time_ms=1234.5,
        steps_executed=3,
    )


def _make_error() -> PipelineError:
    return PipelineError(
        run_id=RUN_ID,
        pipeline_name=PIPELINE_NAME,
        error_type="ValueError",
        error_message="something went wrong",
    )


# -- TestUIBridgeEmit ----------------------------------------------------------


class TestUIBridgeEmit:
    """emit() delegates to broadcast_to_run and auto-triggers completion on terminal events."""

    def test_emit_calls_broadcast_with_run_id_and_event_dict(self):
        bridge, manager = _make_bridge()
        event = _make_started()
        bridge.emit(event)

        assert len(manager.broadcast_calls) == 1
        called_run_id, called_data = manager.broadcast_calls[0]
        assert called_run_id == RUN_ID
        assert called_data == event.to_dict()

    def test_emit_non_terminal_does_not_call_signal_run_complete(self):
        bridge, manager = _make_bridge()
        bridge.emit(_make_started())

        assert manager.signal_calls == []

    def test_emit_pipeline_completed_auto_calls_signal_run_complete(self):
        bridge, manager = _make_bridge()
        bridge.emit(_make_completed())

        assert manager.signal_calls == [RUN_ID]

    def test_emit_pipeline_error_auto_calls_signal_run_complete(self):
        bridge, manager = _make_bridge()
        bridge.emit(_make_error())

        assert manager.signal_calls == [RUN_ID]

    def test_emit_pipeline_completed_broadcasts_before_signaling(self):
        """broadcast_to_run must be called before signal_run_complete."""
        call_order: list[str] = []

        class _OrderedManager:
            def broadcast_to_run(self, run_id, event_data):
                call_order.append("broadcast")

            def signal_run_complete(self, run_id):
                call_order.append("signal")

        bridge = UIBridge(run_id=RUN_ID, manager=_OrderedManager())
        bridge.emit(_make_completed())

        assert call_order == ["broadcast", "signal"]

    def test_emit_passes_correct_event_dict_content(self):
        bridge, manager = _make_bridge()
        event = _make_started()
        bridge.emit(event)

        _, called_data = manager.broadcast_calls[0]
        assert called_data["event_type"] == "pipeline_started"
        assert called_data["run_id"] == RUN_ID
        assert called_data["pipeline_name"] == PIPELINE_NAME

    def test_emit_multiple_non_terminal_events_no_signal(self):
        bridge, manager = _make_bridge()
        for _ in range(5):
            bridge.emit(_make_started())

        assert len(manager.broadcast_calls) == 5
        assert manager.signal_calls == []

    def test_emit_pipeline_error_broadcasts_event_dict(self):
        bridge, manager = _make_bridge()
        event = _make_error()
        bridge.emit(event)

        assert len(manager.broadcast_calls) == 1
        _, called_data = manager.broadcast_calls[0]
        assert called_data == event.to_dict()


# -- TestUIBridgeComplete ------------------------------------------------------


class TestUIBridgeComplete:
    """complete() calls signal_run_complete and is idempotent."""

    def test_explicit_complete_calls_signal_run_complete(self):
        bridge, manager = _make_bridge()
        bridge.complete()

        assert manager.signal_calls == [RUN_ID]

    def test_complete_is_idempotent_second_call_is_no_op(self):
        bridge, manager = _make_bridge()
        bridge.complete()
        bridge.complete()

        assert len(manager.signal_calls) == 1

    def test_complete_after_terminal_event_is_no_op(self):
        """complete() after PipelineCompleted does not call signal_run_complete again."""
        bridge, manager = _make_bridge()
        bridge.emit(_make_completed())  # auto-completes
        bridge.complete()  # explicit call - should be no-op

        assert len(manager.signal_calls) == 1

    def test_complete_sets_completed_flag(self):
        bridge, manager = _make_bridge()
        assert bridge._completed is False
        bridge.complete()
        assert bridge._completed is True

    def test_complete_after_pipeline_error_is_no_op(self):
        bridge, manager = _make_bridge()
        bridge.emit(_make_error())
        bridge.complete()

        assert len(manager.signal_calls) == 1

    def test_complete_uses_correct_run_id(self):
        custom_run_id = "custom-run-xyz"
        manager = _StubManager()
        bridge = UIBridge(run_id=custom_run_id, manager=manager)
        bridge.complete()

        assert manager.signal_calls == [custom_run_id]

    def test_multiple_complete_calls_signal_called_exactly_once(self):
        bridge, manager = _make_bridge()
        for _ in range(10):
            bridge.complete()

        assert len(manager.signal_calls) == 1


# -- TestUIBridgeDI ------------------------------------------------------------


class TestUIBridgeDI:
    """Dependency injection: custom manager vs module-level singleton."""

    def test_custom_manager_injection_works(self):
        manager = _StubManager()
        bridge = UIBridge(run_id=RUN_ID, manager=manager)
        bridge.emit(_make_started())

        assert len(manager.broadcast_calls) == 1

    def test_custom_manager_stored_as_manager_attr(self):
        manager = _StubManager()
        bridge = UIBridge(run_id=RUN_ID, manager=manager)

        assert bridge._manager is manager

    def test_no_manager_arg_uses_module_singleton(self):
        from llm_pipeline.ui.routes.websocket import manager as _singleton

        bridge = UIBridge(run_id=RUN_ID)

        assert bridge._manager is _singleton

    def test_run_id_stored_correctly(self):
        bridge, _ = _make_bridge(run_id="specific-run-id")
        assert bridge.run_id == "specific-run-id"

    def test_initial_completed_flag_is_false(self):
        bridge, _ = _make_bridge()
        assert bridge._completed is False


# -- TestUIBridgeRepr ----------------------------------------------------------


class TestUIBridgeRepr:
    """__repr__ includes run_id."""

    def test_repr_includes_run_id(self):
        bridge, _ = _make_bridge(run_id="repr-test-run")
        result = repr(bridge)

        assert "repr-test-run" in result

    def test_repr_format(self):
        bridge, _ = _make_bridge(run_id="my-run")
        assert repr(bridge) == "UIBridge(run_id='my-run')"

    def test_repr_with_different_run_ids(self):
        for run_id in ("abc", "123", "run-with-dashes"):
            bridge, _ = _make_bridge(run_id=run_id)
            assert run_id in repr(bridge)


# -- TestUIBridgeProtocol ------------------------------------------------------


class TestUIBridgeProtocol:
    """UIBridge satisfies PipelineEventEmitter runtime-checkable Protocol."""

    def test_isinstance_pipeline_event_emitter(self):
        bridge, _ = _make_bridge()
        assert isinstance(bridge, PipelineEventEmitter)

    def test_protocol_check_with_different_run_ids(self):
        for run_id in ("run-1", "run-2"):
            bridge, _ = _make_bridge(run_id=run_id)
            assert isinstance(bridge, PipelineEventEmitter)

    def test_protocol_check_without_injected_manager(self):
        bridge = UIBridge(run_id=RUN_ID)
        assert isinstance(bridge, PipelineEventEmitter)
