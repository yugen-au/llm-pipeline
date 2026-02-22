"""Cross-component integration tests for Phase 2 backend (REST API + WebSocket).

Covers 5 genuine integration gaps not addressed by existing per-route unit tests:
- GAP 1: E2E POST /api/runs -> UIBridge -> WS live stream (CRITICAL)
- GAP 3: trigger failing pipeline -> DB status=failed + completed_at set
- GAP 5: WS disconnect mid-stream -> ConnectionManager cleanup
- GAP 6: combined multi-param query filters on /api/runs and /api/runs/{id}/events
- GAP 7: actual CORS response headers in HTTP responses

All tests use _make_app() (StaticPool pattern) from conftest.py. No source changes.
"""
import threading
import time
from datetime import datetime, timezone

import pytest
from sqlmodel import Session, select
from starlette.testclient import TestClient

from llm_pipeline.events.types import PipelineCompleted, PipelineStarted
from llm_pipeline.state import PipelineRun
from llm_pipeline.ui.routes.websocket import manager

from tests.ui.conftest import _make_app


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
def _clean_manager():
    """Clear module-level singleton state between tests."""
    manager._connections.clear()
    manager._queues.clear()
    yield
    manager._connections.clear()
    manager._queues.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _wait_for_connection(run_id: str, count: int = 1, timeout: float = 2.0) -> None:
    """Spin until count clients are registered in manager for run_id."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if len(manager._queues.get(run_id, [])) >= count:
            return
        time.sleep(0.005)
    raise TimeoutError(f"Expected {count} connection(s) for {run_id} within {timeout}s")


def _make_emitting_pipeline_factory():
    """Return a factory that emits PipelineStarted + PipelineCompleted via UIBridge.

    Factory signature: (run_id, engine, event_emitter=None, **kw) -> pipeline
    The returned pipeline object:
    - execute(): inserts a PipelineRun row, emits both events via event_emitter
    - save(): updates PipelineRun.status to completed and sets completed_at
    """
    class _EmittingPipeline:
        def __init__(self, run_id, engine, event_emitter=None):
            self._run_id = run_id
            self._engine = engine
            self._emitter = event_emitter

        def execute(self):
            with Session(self._engine) as session:
                run = PipelineRun(
                    run_id=self._run_id,
                    pipeline_name="integration_test_pipeline",
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                session.add(run)
                session.commit()

            if self._emitter is not None:
                self._emitter.emit(
                    PipelineStarted(
                        run_id=self._run_id,
                        pipeline_name="integration_test_pipeline",
                    )
                )
                self._emitter.emit(
                    PipelineCompleted(
                        run_id=self._run_id,
                        pipeline_name="integration_test_pipeline",
                        execution_time_ms=10.0,
                        steps_executed=0,
                    )
                )

        def save(self):
            with Session(self._engine) as session:
                stmt = select(PipelineRun).where(PipelineRun.run_id == self._run_id)
                run = session.exec(stmt).first()
                if run:
                    run.status = "completed"
                    run.completed_at = datetime.now(timezone.utc)
                    session.add(run)
                    session.commit()

    def factory(run_id, engine, event_emitter=None, **kw):
        return _EmittingPipeline(run_id, engine, event_emitter)

    return factory


def _make_failing_pipeline_factory():
    """Return a factory whose execute() raises RuntimeError after inserting a PipelineRun row.

    The trigger_run except block in runs.py catches this and sets status=failed + completed_at.
    """
    class _FailingPipeline:
        def __init__(self, run_id, engine, event_emitter=None):
            self._run_id = run_id
            self._engine = engine

        def execute(self):
            with Session(self._engine) as session:
                run = PipelineRun(
                    run_id=self._run_id,
                    pipeline_name="failing_test_pipeline",
                    status="running",
                    started_at=datetime.now(timezone.utc),
                )
                session.add(run)
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


def _make_no_op_factory():
    """No-op factory: background task runs but does not emit events.

    Used to get a valid run_id from POST /api/runs without racing the WS.
    The test manually seeds the PipelineRun row and drives UIBridge emission
    after the WS client is confirmed connected.
    """
    class _NoOpPipeline:
        def __init__(self, run_id, engine, event_emitter=None):
            self._run_id = run_id
            self._engine = engine

        def execute(self):
            # Insert the PipelineRun row so trigger_run's except block can find it
            with Session(self._engine) as session:
                session.add(PipelineRun(
                    run_id=self._run_id,
                    pipeline_name="integration_test_pipeline",
                    status="running",
                    started_at=datetime.now(timezone.utc),
                ))
                session.commit()
            # Deliberately block until the test signals us to proceed.
            # We use a threading.Event stored on the engine (injected below).
            gate = getattr(self._engine, "_test_gate", None)
            if gate is not None:
                gate.wait(timeout=5.0)

        def save(self):
            pass

    def factory(run_id, engine, event_emitter=None, **kw):
        return _NoOpPipeline(run_id, engine, event_emitter)

    return factory


class TestE2ETriggerWebSocket:
    """POST /api/runs triggers a real UIBridge -> WS fan-out.

    Strategy: POST returns run_id; background task is blocked by a gate event
    until the WS client connects and is confirmed registered. Then UIBridge
    emits events directly (same bridge used by the actual flow) -- this
    exercises ConnectionManager.broadcast_to_run() -> WS client path without
    a race between the background task and WS connection.
    """

    def _setup(self):
        """Create app + client + gate event. Returns (app, client, gate)."""
        gate = threading.Event()
        app = _make_app()
        app.state.engine._test_gate = gate
        app.state.pipeline_registry = {
            "integration_test_pipeline": _make_no_op_factory()
        }
        return app, TestClient(app), gate

    def _collect_events(self, client, run_id):
        """Open WS, collect until stream_complete/replay_complete. Returns (received, done_event)."""
        received = []
        done = threading.Event()

        def _run():
            try:
                with client.websocket_connect(f"/ws/runs/{run_id}") as ws:
                    while True:
                        msg = ws.receive_json()
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

    def test_trigger_then_ws_receives_pipeline_started(self):
        from llm_pipeline.ui.bridge import UIBridge

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
            _wait_for_connection(run_id, count=1, timeout=3.0)

            # WS is connected; now emit via UIBridge (same path as real pipeline)
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

        event_types = [m.get("event_type") for m in received if "event_type" in m]
        assert "pipeline_started" in event_types

    def test_trigger_then_ws_receives_pipeline_completed(self):
        from llm_pipeline.ui.bridge import UIBridge

        app, client, gate = self._setup()
        with client:
            resp = client.post("/api/runs", json={"pipeline_name": "integration_test_pipeline"})
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                with Session(app.state.engine) as s:
                    row = s.exec(select(PipelineRun).where(PipelineRun.run_id == run_id)).first()
                if row is not None:
                    break
                time.sleep(0.01)

            received, done = self._collect_events(client, run_id)
            _wait_for_connection(run_id, count=1, timeout=3.0)

            bridge = UIBridge(run_id=run_id)
            bridge.emit(PipelineStarted(run_id=run_id, pipeline_name="integration_test_pipeline"))
            bridge.emit(PipelineCompleted(
                run_id=run_id,
                pipeline_name="integration_test_pipeline",
                execution_time_ms=10.0,
                steps_executed=0,
            ))
            done.wait(timeout=3.0)
            gate.set()

        event_types = [m.get("event_type") for m in received if "event_type" in m]
        assert "pipeline_completed" in event_types

    def test_trigger_ws_stream_complete_sent_on_finish(self):
        from llm_pipeline.ui.bridge import UIBridge

        app, client, gate = self._setup()
        with client:
            resp = client.post("/api/runs", json={"pipeline_name": "integration_test_pipeline"})
            assert resp.status_code == 202
            run_id = resp.json()["run_id"]

            deadline = time.monotonic() + 3.0
            while time.monotonic() < deadline:
                with Session(app.state.engine) as s:
                    row = s.exec(select(PipelineRun).where(PipelineRun.run_id == run_id)).first()
                if row is not None:
                    break
                time.sleep(0.01)

            received, done = self._collect_events(client, run_id)
            _wait_for_connection(run_id, count=1, timeout=3.0)

            bridge = UIBridge(run_id=run_id)
            bridge.emit(PipelineStarted(run_id=run_id, pipeline_name="integration_test_pipeline"))
            bridge.emit(PipelineCompleted(
                run_id=run_id,
                pipeline_name="integration_test_pipeline",
                execution_time_ms=10.0,
                steps_executed=0,
            ))
            done.wait(timeout=3.0)
            gate.set()

        terminal = [m for m in received if m.get("type") == "stream_complete"]
        assert len(terminal) == 1
        assert terminal[0]["run_id"] == run_id


# ---------------------------------------------------------------------------
# GAP 3: trigger failing pipeline -> DB status=failed + completed_at set
# ---------------------------------------------------------------------------


class TestTriggerRunErrorHandling:
    """Failing pipeline execute() -> runs.py except block sets DB status=failed."""

    def _make_failing_client(self):
        app = _make_app()
        app.state.pipeline_registry = {
            "failing_test_pipeline": _make_failing_pipeline_factory()
        }
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
        from datetime import timedelta
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
        from datetime import timedelta
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

    def test_disconnect_mid_stream_removes_from_queues(self, seeded_app_client):
        # RUN_RUNNING -> live stream path (status=running in seeded data)
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws:
            _wait_for_connection(RUN_RUNNING, count=1)
            # Confirm client is registered
            assert len(manager._queues.get(RUN_RUNNING, [])) == 1
            # Exit context manager early -> triggers WebSocketDisconnect on server
        # After disconnect, manager should have cleaned up
        assert RUN_RUNNING not in manager._queues

    def test_disconnect_mid_stream_removes_from_connections(self, seeded_app_client):
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws:
            _wait_for_connection(RUN_RUNNING, count=1)
            assert len(manager._connections.get(RUN_RUNNING, [])) == 1
        assert RUN_RUNNING not in manager._connections

    def test_second_client_connects_after_first_disconnects(self, seeded_app_client):
        # First client connects and disconnects
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws:
            _wait_for_connection(RUN_RUNNING, count=1)
        assert RUN_RUNNING not in manager._queues

        # Second client can connect cleanly to the same run_id
        with seeded_app_client.websocket_connect(f"/ws/runs/{RUN_RUNNING}") as ws:
            _wait_for_connection(RUN_RUNNING, count=1)
            assert len(manager._queues.get(RUN_RUNNING, [])) == 1
            manager.signal_run_complete(RUN_RUNNING)
            msg = ws.receive_json()
        assert msg["type"] == "stream_complete"
