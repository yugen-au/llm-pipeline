"""WebSocket endpoint tests covering the unified /ws/runs endpoint."""
import json
import time
import pytest

from llm_pipeline.ui.routes.websocket import manager


def _wait_for_subscription(run_id: str, count: int = 1, timeout: float = 2.0) -> None:
    """Spin until `count` clients are subscribed to run_id."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(manager._run_subscribers.get(run_id, set())) >= count:
            return
        time.sleep(0.005)
    raise TimeoutError(f"Expected {count} subscriber(s) for {run_id} within {timeout}s")


def _wait_for_connection(count: int = 1, timeout: float = 2.0) -> None:
    """Spin until `count` clients are connected."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(manager._client_queues) >= count:
            return
        time.sleep(0.005)
    raise TimeoutError(f"Expected {count} connection(s) within {timeout}s")


RUN_COMPLETED = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_FAILED = "aaaaaaaa-0000-0000-0000-000000000002"
RUN_RUNNING = "aaaaaaaa-0000-0000-0000-000000000003"
RUN_NONEXISTENT = "nonexistent-run-id"


@pytest.fixture(autouse=True)
def _fast_heartbeat(monkeypatch):
    """Use a short heartbeat so tests don't block 30s on teardown."""
    import llm_pipeline.ui.routes.websocket as ws_module
    monkeypatch.setattr(ws_module, "HEARTBEAT_INTERVAL_S", 0.05)


@pytest.fixture(autouse=True)
def _clean_manager():
    """Clear module-level singleton state between tests."""
    manager._client_queues.clear()
    manager._subscriptions.clear()
    manager._run_subscribers.clear()
    manager._websockets.clear()
    yield
    manager._client_queues.clear()
    manager._subscriptions.clear()
    manager._run_subscribers.clear()
    manager._websockets.clear()


class TestBatchReplay:
    def test_batch_replay_completed_run(self, seeded_app_client):
        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "run_id": RUN_COMPLETED}))
            events = []
            while True:
                msg = ws.receive_json()
                if msg.get("type") == "heartbeat":
                    continue
                if msg.get("type") == "replay_complete":
                    replay_complete = msg
                    break
                events.append(msg)

        # Past traces live in Langfuse, not in the local DB.
        # WS replay no longer streams persisted events — it just signals
        # replay_complete with the run's terminal status.
        assert len(events) == 0
        assert replay_complete["event_count"] == 0
        assert replay_complete["run_status"] == "completed"
        assert replay_complete["run_id"] == RUN_COMPLETED

    def test_batch_replay_failed_run_empty(self, seeded_app_client):
        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "run_id": RUN_FAILED}))
            events = []
            while True:
                msg = ws.receive_json()
                if msg.get("type") == "heartbeat":
                    continue
                if msg.get("type") == "replay_complete":
                    replay_complete = msg
                    break
                events.append(msg)

        assert len(events) == 0
        assert replay_complete["event_count"] == 0
        assert replay_complete["run_status"] == "failed"


class TestNotFound:
    def test_run_not_found(self, seeded_app_client):
        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            ws.send_text(json.dumps({"action": "subscribe", "run_id": RUN_NONEXISTENT}))
            msg = ws.receive_json()
            # Skip heartbeats
            while msg.get("type") == "heartbeat":
                msg = ws.receive_json()

        assert msg["type"] == "error"
        assert msg["detail"] == "Run not found"
        assert msg["run_id"] == RUN_NONEXISTENT


class TestLiveStream:
    def test_live_stream_events(self, seeded_app_client):
        event_payload = {"event_type": "step_started", "run_id": RUN_RUNNING}

        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            _wait_for_connection(count=1)
            ws.send_text(json.dumps({"action": "subscribe", "run_id": RUN_RUNNING}))
            _wait_for_subscription(RUN_RUNNING, count=1)

            manager.broadcast_to_run(RUN_RUNNING, event_payload)
            manager.signal_run_complete(RUN_RUNNING)

            first = ws.receive_json()
            second = ws.receive_json()

        assert first == event_payload
        assert second["type"] == "stream_complete"
        assert second["run_id"] == RUN_RUNNING
        # Enriched fields from DB
        assert second["status"] == "running"

    def test_live_stream_multiple_clients(self, seeded_app_client):
        event_payload = {"event_type": "step_completed", "run_id": RUN_RUNNING}

        with seeded_app_client.websocket_connect("/ws/runs") as ws1:
            with seeded_app_client.websocket_connect("/ws/runs") as ws2:
                _wait_for_connection(count=2)
                ws1.send_text(json.dumps({"action": "subscribe", "run_id": RUN_RUNNING}))
                ws2.send_text(json.dumps({"action": "subscribe", "run_id": RUN_RUNNING}))
                _wait_for_subscription(RUN_RUNNING, count=2)

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

    def test_unsubscribe_stops_events(self, seeded_app_client):
        """After unsubscribing, client should not receive run events."""
        event_before = {"event_type": "step_started", "run_id": RUN_RUNNING, "seq": 1}
        global_event = {"type": "run_created", "run_id": "new-run", "pipeline_name": "test", "started_at": "2025-01-01T00:00:00Z"}

        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            _wait_for_connection(count=1)
            ws.send_text(json.dumps({"action": "subscribe", "run_id": RUN_RUNNING}))
            _wait_for_subscription(RUN_RUNNING, count=1)

            # Send event while subscribed
            manager.broadcast_to_run(RUN_RUNNING, event_before)
            first = ws.receive_json()
            assert first == event_before

            # Unsubscribe
            ws.send_text(json.dumps({"action": "unsubscribe", "run_id": RUN_RUNNING}))
            # Small delay for unsubscribe to process
            time.sleep(0.05)

            # Send another run event -- should NOT be received
            manager.broadcast_to_run(RUN_RUNNING, {"event_type": "step_completed", "run_id": RUN_RUNNING, "seq": 2})

            # Send a global event -- should be received
            manager.broadcast_global(global_event)
            msg = ws.receive_json()
            while msg.get("type") == "heartbeat":
                msg = ws.receive_json()
            assert msg["type"] == "run_created"


class TestGlobalBroadcast:
    def test_global_broadcast(self, seeded_app_client):
        global_event = {
            "type": "run_created",
            "run_id": "new-run-123",
            "pipeline_name": "test-pipeline",
            "started_at": "2025-01-01T00:00:00Z",
        }

        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            _wait_for_connection(count=1)
            manager.broadcast_global(global_event)
            msg = ws.receive_json()

        assert msg == global_event


class TestHeartbeat:
    def test_heartbeat(self, seeded_app_client):
        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            heartbeat = ws.receive_json()

        assert heartbeat["type"] == "heartbeat"
        assert "timestamp" in heartbeat
