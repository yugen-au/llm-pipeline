"""WebSocket endpoint tests covering all connection lifecycle paths."""
import time
import pytest

from llm_pipeline.ui.routes.websocket import manager


def _wait_for_connection(run_id: str, count: int = 1, timeout: float = 2.0) -> None:
    """Spin until `count` clients are registered in manager for run_id."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(manager._queues.get(run_id, [])) >= count:
            return
        time.sleep(0.005)
    raise TimeoutError(f"Expected {count} connection(s) for {run_id} within {timeout}s")

RUN_COMPLETED = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_FAILED = "aaaaaaaa-0000-0000-0000-000000000002"
RUN_RUNNING = "aaaaaaaa-0000-0000-0000-000000000003"
RUN_NONEXISTENT = "nonexistent-run-id"


@pytest.fixture(autouse=True)
def _clean_manager():
    """Clear module-level singleton state between tests."""
    manager._connections.clear()
    manager._queues.clear()
    yield
    manager._connections.clear()
    manager._queues.clear()


class TestBatchReplay:
    def test_batch_replay_completed_run(self, seeded_app_client):
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_COMPLETED}") as ws:
            events = []
            while True:
                msg = ws.receive_json()
                if msg.get("type") == "replay_complete":
                    replay_complete = msg
                    break
                events.append(msg)

        assert len(events) == 4
        assert replay_complete["event_count"] == 4
        assert replay_complete["run_status"] == "completed"

    def test_batch_replay_failed_run_empty(self, seeded_app_client):
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_FAILED}") as ws:
            events = []
            while True:
                msg = ws.receive_json()
                if msg.get("type") == "replay_complete":
                    replay_complete = msg
                    break
                events.append(msg)

        assert len(events) == 0
        assert replay_complete["event_count"] == 0
        assert replay_complete["run_status"] == "failed"


class TestNotFound:
    def test_run_not_found(self, seeded_app_client):
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_NONEXISTENT}") as ws:
            msg = ws.receive_json()

        assert msg == {"type": "error", "detail": "Run not found"}


class TestLiveStream:
    def test_live_stream_events(self, seeded_app_client):
        event_payload = {"event_type": "step_started", "run_id": RUN_RUNNING}

        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws:
            _wait_for_connection(RUN_RUNNING, count=1)
            manager.broadcast_to_run(RUN_RUNNING, event_payload)
            manager.signal_run_complete(RUN_RUNNING)

            first = ws.receive_json()
            second = ws.receive_json()

        assert first == event_payload
        assert second["type"] == "stream_complete"
        assert second["run_id"] == RUN_RUNNING

    def test_live_stream_multiple_clients(self, seeded_app_client):
        event_payload = {"event_type": "step_completed", "run_id": RUN_RUNNING}

        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws1:
            with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws2:
                _wait_for_connection(RUN_RUNNING, count=2)
                manager.broadcast_to_run(RUN_RUNNING, event_payload)
                manager.signal_run_complete(RUN_RUNNING)

                ws1_event = ws1.receive_json()
                ws1_complete = ws1.receive_json()
                ws2_event = ws2.receive_json()
                ws2_complete = ws2.receive_json()

        assert ws1_event == event_payload
        assert ws1_complete["type"] == "stream_complete"
        assert ws2_event == event_payload
        assert ws2_complete["type"] == "stream_complete"


class TestHeartbeat:
    def test_heartbeat(self, seeded_app_client, monkeypatch):
        import llm_pipeline.ui.routes.websocket as ws_module

        monkeypatch.setattr(ws_module, "HEARTBEAT_INTERVAL_S", 0.01)

        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws:
            # Receive first message - with 10ms timeout it will be a heartbeat.
            heartbeat = ws.receive_json()
            # Signal complete so the handler exits; drain stream_complete.
            _wait_for_connection(RUN_RUNNING, count=1)
            manager.signal_run_complete(RUN_RUNNING)
            while True:
                m = ws.receive_json()
                if m.get("type") == "stream_complete":
                    break

        assert heartbeat["type"] == "heartbeat"
        assert "timestamp" in heartbeat
