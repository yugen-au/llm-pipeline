"""Cross-component integration tests for Phase 2 backend (REST API + WebSocket).

Covers 5 genuine integration gaps not addressed by existing per-route unit tests:
- GAP 1: E2E POST /api/runs -> UIBridge -> WS live stream (CRITICAL)
- GAP 3: trigger failing pipeline -> DB status=failed + completed_at set
- GAP 5: WS disconnect mid-stream -> ConnectionManager cleanup
- GAP 6: combined multi-param query filters on /api/runs and /api/runs/{id}/events
- GAP 7: actual CORS response headers in HTTP responses

All tests use _make_app() (StaticPool pattern) from conftest.py. No source changes.
"""
import json
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import Session, select
from starlette.testclient import TestClient

from llm_pipeline.events.types import PipelineCompleted, PipelineStarted
from llm_pipeline.state import PipelineRun
from llm_pipeline.ui.bridge import UIBridge
from llm_pipeline.ui.routes.websocket import manager

from tests.ui.conftest import _make_app, _publish_all


# ---------------------------------------------------------------------------
# Seed data UUIDs (matching conftest.py seeded_app_client)
# ---------------------------------------------------------------------------

RUN_COMPLETED = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_FAILED = "aaaaaaaa-0000-0000-0000-000000000002"
RUN_RUNNING = "aaaaaaaa-0000-0000-0000-000000000003"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_connection(count: int = 1, timeout: float = 2.0) -> None:
    """Spin until count clients are connected to manager."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(manager._client_queues) >= count:
            return
        time.sleep(0.005)
    raise TimeoutError(f"Expected {count} connection(s) within {timeout}s")


def _wait_for_subscription(run_id: str, count: int = 1, timeout: float = 2.0) -> None:
    """Spin until count clients are subscribed to run_id."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(manager._run_subscribers.get(run_id, set())) >= count:
            return
        time.sleep(0.005)
    raise TimeoutError(f"Expected {count} subscriber(s) for {run_id} within {timeout}s")


def _make_failing_pipeline_factory():
    """Return a factory whose execute() raises RuntimeError after inserting a PipelineRun row.

    The trigger_run except block in runs.py catches this and sets status=failed + completed_at.
    """
    class _FailingPipeline:
        def __init__(self, run_id, engine, event_emitter=None):
            self._run_id = run_id
            self._engine = engine

        def execute(self, **kwargs):
            with Session(self._engine) as session:
                existing = session.exec(
                    select(PipelineRun).where(PipelineRun.run_id == self._run_id)
                ).first()
                if not existing:
                    session.add(PipelineRun(
                        run_id=self._run_id,
                        pipeline_name="failing_test_pipeline",
                        status="running",
                        started_at=datetime.now(timezone.utc),
                    ))
                    session.commit()
            raise RuntimeError("forced failure")

        def save(self):
            # not called -- exception in execute() prevents reaching save()
            pass

    def factory(run_id, engine, event_emitter=None, **kw):
        return _FailingPipeline(run_id, engine, event_emitter)

    return factory


# ---------------------------------------------------------------------------
# GAP 1 + GAP 4: E2E POST /api/runs -> UIBridge -> WS live stream
# ---------------------------------------------------------------------------


def _make_no_op_factory(gate: threading.Event):
    """No-op factory: background task inserts PipelineRun row then blocks on gate."""
    class _NoOpPipeline:
        def __init__(self, run_id, engine, event_emitter=None):
            self._run_id = run_id
            self._engine = engine

        def execute(self, **kwargs):
            with Session(self._engine) as session:
                existing = session.exec(
                    select(PipelineRun).where(PipelineRun.run_id == self._run_id)
                ).first()
                if not existing:
                    session.add(PipelineRun(
                        run_id=self._run_id,
                        pipeline_name="integration_test_pipeline",
                        status="running",
                        started_at=datetime.now(timezone.utc),
                    ))
                    session.commit()
            gate.wait(timeout=5.0)

        def save(self):
            pass

    def factory(run_id, engine, event_emitter=None, **kw):
        return _NoOpPipeline(run_id, engine, event_emitter)

    return factory


class TestE2ETriggerWebSocket:
    """POST /api/runs triggers a real UIBridge -> WS fan-out.

    Uses unified /ws/runs endpoint with subscribe messages.
    """

    def _setup(self):
        """Create app + client + gate event. Returns (app, client, gate)."""
        from llm_pipeline.db.pipeline_visibility import PipelineVisibility
        gate = threading.Event()
        app = _make_app()
        app.state._test_gate = gate
        app.state.pipeline_registry = {
            "integration_test_pipeline": _make_no_op_factory(gate)
        }
        with Session(app.state.engine) as s:
            s.add(PipelineVisibility(pipeline_name="integration_test_pipeline", status="published"))
            s.commit()
        return app, TestClient(app), gate

    def _collect_events(self, client, run_id):
        """Open WS, subscribe, collect until stream_complete/replay_complete."""
        received = []
        done = threading.Event()

        def _run():
            try:
                with client.websocket_connect("/ws/runs") as ws:
                    ws.send_text(json.dumps({"action": "subscribe", "run_id": run_id}))
                    while True:
                        msg = ws.receive_json()
                        if msg.get("type") == "heartbeat":
                            continue
                        received.append(msg)
                        if msg.get("type") in ("stream_complete", "replay_complete"):
                            break
            except Exception as exc:
                received.append({"_error": str(exc)})
            finally:
                done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return received, done

    def _trigger_and_collect(self):
        """POST trigger, connect WS, subscribe, emit events, collect until stream_complete."""
        app, client, gate = self._setup()
        with client:
            resp = client.post("/api/runs", json={"pipeline_name": "integration_test_pipeline"})
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

            # Background task inserts row then blocks on gate. Wait for row.
            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                with Session(app.state.engine) as s:
                    row = s.exec(select(PipelineRun).where(PipelineRun.run_id == run_id)).first()
                if row is not None:
                    break
                time.sleep(0.01)

            received, done = self._collect_events(client, run_id)
            _wait_for_subscription(run_id, count=1, timeout=3.0)

            # WS is subscribed; emit via UIBridge
            bridge = UIBridge(run_id=run_id)
            bridge.emit(PipelineStarted(run_id=run_id, pipeline_name="integration_test_pipeline"))
            bridge.emit(PipelineCompleted(
                run_id=run_id,
                pipeline_name="integration_test_pipeline",
                execution_time_ms=10.0,
                steps_executed=0,
            ))
            done.wait(timeout=3.0)
            gate.set()  # unblock background task so TestClient exits cleanly

        return run_id, received

    def test_trigger_then_ws_receives_pipeline_started(self):
        _, received = self._trigger_and_collect()
        event_types = [m.get("event_type") for m in received if "event_type" in m]
        assert "pipeline_started" in event_types

    def test_trigger_then_ws_receives_pipeline_completed(self):
        _, received = self._trigger_and_collect()
        event_types = [m.get("event_type") for m in received if "event_type" in m]
        assert "pipeline_completed" in event_types

    def test_trigger_ws_stream_complete_sent_on_finish(self):
        run_id, received = self._trigger_and_collect()
        terminal = [m for m in received if m.get("type") == "stream_complete"]
        assert len(terminal) == 1
        assert terminal[0]["run_id"] == run_id


# ---------------------------------------------------------------------------
# GAP 3: trigger failing pipeline -> DB status=failed + completed_at set
# ---------------------------------------------------------------------------


class TestTriggerRunErrorHandling:
    """Failing pipeline execute() -> runs.py except block sets DB status=failed."""

    def _make_failing_client(self):
        from llm_pipeline.db.pipeline_visibility import PipelineVisibility
        app = _make_app()
        app.state.pipeline_registry = {
            "failing_test_pipeline": _make_failing_pipeline_factory()
        }
        with Session(app.state.engine) as s:
            s.add(PipelineVisibility(pipeline_name="failing_test_pipeline", status="published"))
            s.commit()
        return app, TestClient(app)

    def test_trigger_failing_pipeline_sets_status_failed(self):
        app, client = self._make_failing_client()
        with client:
            resp = client.post(
                "/api/runs",
                json={"pipeline_name": "failing_test_pipeline"},
            )
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]
            # Background tasks flush on TestClient context exit (end of `with client`)

        # After context exit, background task has completed
        with Session(app.state.engine) as session:
            run = session.exec(
                select(PipelineRun).where(PipelineRun.run_id == run_id)
            ).first()
        assert run is not None
        assert run.status == "failed"

    def test_trigger_failing_pipeline_sets_completed_at(self):
        app, client = self._make_failing_client()
        with client:
            resp = client.post(
                "/api/runs",
                json={"pipeline_name": "failing_test_pipeline"},
            )
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

        with Session(app.state.engine) as session:
            run = session.exec(
                select(PipelineRun).where(PipelineRun.run_id == run_id)
            ).first()
        assert run is not None
        assert run.completed_at is not None

    def test_trigger_failing_pipeline_completed_at_is_datetime(self):
        app, client = self._make_failing_client()
        with client:
            resp = client.post(
                "/api/runs",
                json={"pipeline_name": "failing_test_pipeline"},
            )
            run_id = resp.json()["run_id"]

        with Session(app.state.engine) as session:
            run = session.exec(
                select(PipelineRun).where(PipelineRun.run_id == run_id)
            ).first()
        assert isinstance(run.completed_at, datetime)


# ---------------------------------------------------------------------------
# GAP 6: combined multi-param query filters
# ---------------------------------------------------------------------------


class TestCombinedFilters:
    """Multi-param filters on /api/runs and /api/runs/{id}/events."""

    def test_runs_filter_pipeline_name_and_status_match(self, seeded_app_client):
        resp = seeded_app_client.get(
            "/api/runs",
            params={"pipeline_name": "alpha_pipeline", "status": "completed"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["run_id"] == RUN_COMPLETED

    def test_runs_filter_pipeline_name_and_status_no_match(self, seeded_app_client):
        resp = seeded_app_client.get(
            "/api/runs",
            params={"pipeline_name": "beta_pipeline", "status": "completed"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_runs_filter_pipeline_name_and_started_after(self, seeded_app_client):
        # run3 (alpha_pipeline, running) started ~100s ago; use 150s cutoff
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=150)).isoformat()
        resp = seeded_app_client.get(
            "/api/runs",
            params={"pipeline_name": "alpha_pipeline", "started_after": cutoff},
        )
        assert resp.status_code == 200
        body = resp.json()
        # Only run3 matches (alpha_pipeline started ~100s ago)
        assert body["total"] == 1
        assert body["items"][0]["run_id"] == RUN_RUNNING

    def test_runs_filter_pipeline_name_and_started_after_no_match(self, seeded_app_client):
        # Cutoff at 50s ago -- no run started within last 50s
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=50)).isoformat()
        resp = seeded_app_client.get(
            "/api/runs",
            params={"pipeline_name": "alpha_pipeline", "started_after": cutoff},
        )
        body = resp.json()
        assert body["total"] == 0

    def test_events_filter_event_type_with_pagination(self, seeded_app_client):
        # RUN_1 has 1 step_started event (see conftest seed)
        resp = seeded_app_client.get(
            f"/api/runs/{RUN_COMPLETED}/events",
            params={"event_type": "step_started", "limit": 1, "offset": 0},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["event_type"] == "step_started"

    def test_events_filter_event_type_with_offset_returns_empty(self, seeded_app_client):
        # offset=1 with 1 matching event -> empty page
        resp = seeded_app_client.get(
            f"/api/runs/{RUN_COMPLETED}/events",
            params={"event_type": "step_started", "limit": 10, "offset": 1},
        )
        body = resp.json()
        assert body["total"] == 1
        assert body["items"] == []


# ---------------------------------------------------------------------------
# GAP 7: actual CORS response headers in HTTP responses
# ---------------------------------------------------------------------------


class TestCORSHeaders:
    """CORS headers must appear in actual HTTP responses, not just middleware config."""

    def test_cors_allows_any_origin_on_get(self, app_client):
        resp = app_client.get(
            "/api/runs",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-origin") == "*"

    def test_cors_preflight_options_returns_success(self, app_client):
        resp = app_client.options(
            "/api/runs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.status_code in (200, 204)

    def test_cors_preflight_includes_allow_origin_header(self, app_client):
        resp = app_client.options(
            "/api/runs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert "access-control-allow-origin" in resp.headers

    def test_cors_allow_methods_header_on_preflight(self, app_client):
        resp = app_client.options(
            "/api/runs",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert "access-control-allow-methods" in resp.headers


# ---------------------------------------------------------------------------
# GAP 5: WS disconnect mid-stream -> ConnectionManager cleanup
# ---------------------------------------------------------------------------


class TestWebSocketDisconnect:
    """Disconnecting a WS client mid-stream cleans up ConnectionManager state."""

    def test_disconnect_removes_client_from_manager(self, seeded_app_client):
        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            _wait_for_connection(count=1)
            assert len(manager._client_queues) == 1
        # After disconnect, manager should have cleaned up
        # Small delay for async cleanup
        time.sleep(0.1)
        assert len(manager._client_queues) == 0

    def test_disconnect_removes_subscriptions(self, seeded_app_client):
        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            _wait_for_connection(count=1)
            ws.send_text(json.dumps({"action": "subscribe", "run_id": RUN_RUNNING}))
            _wait_for_subscription(RUN_RUNNING, count=1)
            assert len(manager._run_subscribers.get(RUN_RUNNING, set())) == 1
        # After disconnect, subscriptions cleaned up
        time.sleep(0.1)
        assert len(manager._run_subscribers.get(RUN_RUNNING, set())) == 0

    def test_second_client_connects_after_first_disconnects(self, seeded_app_client):
        # First client connects and disconnects
        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            _wait_for_connection(count=1)
        time.sleep(0.1)
        assert len(manager._client_queues) == 0

        # Second client can connect and subscribe
        with seeded_app_client.websocket_connect("/ws/runs") as ws:
            _wait_for_connection(count=1)
            ws.send_text(json.dumps({"action": "subscribe", "run_id": RUN_RUNNING}))
            _wait_for_subscription(RUN_RUNNING, count=1)
            manager.broadcast_to_run(RUN_RUNNING, {"event_type": "test", "run_id": RUN_RUNNING})
            msg = ws.receive_json()
            while msg.get("type") == "heartbeat":
                msg = ws.receive_json()
        assert msg["event_type"] == "test"
