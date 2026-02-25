"""Endpoint tests for /api/runs routes."""
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from starlette.testclient import TestClient

from llm_pipeline.ui.app import create_app


RUN_1 = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_2 = "aaaaaaaa-0000-0000-0000-000000000002"
RUN_3 = "aaaaaaaa-0000-0000-0000-000000000003"


class TestListRuns:
    def test_empty_returns_200_with_empty_items(self, app_client):
        resp = app_client.get("/api/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_all_runs_no_filter(self, seeded_app_client):
        resp = seeded_app_client.get("/api/runs")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 3

    def test_total_matches_row_count(self, seeded_app_client):
        resp = seeded_app_client.get("/api/runs")
        body = resp.json()
        assert body["total"] == 3

    def test_pipeline_name_filter(self, seeded_app_client):
        resp = seeded_app_client.get("/api/runs", params={"pipeline_name": "alpha_pipeline"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert all(item["pipeline_name"] == "alpha_pipeline" for item in body["items"])

    def test_status_filter(self, seeded_app_client):
        resp = seeded_app_client.get("/api/runs", params={"status": "failed"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "failed"

    def test_started_after_filter(self, seeded_app_client):
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=150)).isoformat()
        resp = seeded_app_client.get("/api/runs", params={"started_after": cutoff})
        body = resp.json()
        # only run3 started ~100s ago
        assert body["total"] == 1
        assert body["items"][0]["run_id"] == RUN_3

    def test_started_before_filter(self, seeded_app_client):
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=250)).isoformat()
        resp = seeded_app_client.get("/api/runs", params={"started_before": cutoff})
        body = resp.json()
        # only run1 started ~300s ago
        assert body["total"] == 1
        assert body["items"][0]["run_id"] == RUN_1

    def test_pagination_offset_limit(self, seeded_app_client):
        # ordered desc by started_at: run3, run2, run1
        page1 = seeded_app_client.get("/api/runs", params={"limit": 2, "offset": 0}).json()
        page2 = seeded_app_client.get("/api/runs", params={"limit": 2, "offset": 2}).json()
        assert len(page1["items"]) == 2
        assert len(page2["items"]) == 1
        # page2 item must not appear in page1
        page1_ids = {i["run_id"] for i in page1["items"]}
        page2_ids = {i["run_id"] for i in page2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    def test_limit_above_200_returns_422(self, app_client):
        resp = app_client.get("/api/runs", params={"limit": 201})
        assert resp.status_code == 422

    def test_negative_offset_returns_422(self, app_client):
        resp = app_client.get("/api/runs", params={"offset": -1})
        assert resp.status_code == 422

    def test_results_ordered_by_started_at_desc(self, seeded_app_client):
        resp = seeded_app_client.get("/api/runs")
        items = resp.json()["items"]
        started_ats = [item["started_at"] for item in items]
        assert started_ats == sorted(started_ats, reverse=True)

    def test_response_schema_fields(self, seeded_app_client):
        body = seeded_app_client.get("/api/runs").json()
        assert "items" in body
        assert "total" in body
        assert "offset" in body
        assert "limit" in body
        item = body["items"][0]
        for field in ("run_id", "pipeline_name", "status", "started_at"):
            assert field in item


class TestGetRun:
    def test_returns_200_with_run_fields_and_steps(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{RUN_1}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == RUN_1
        assert body["pipeline_name"] == "alpha_pipeline"
        assert body["status"] == "completed"
        assert body["step_count"] == 2
        assert body["total_time_ms"] == 9800
        assert isinstance(body["steps"], list)
        assert len(body["steps"]) == 2

    def test_steps_ordered_by_step_number_asc(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_1}").json()
        step_numbers = [s["step_number"] for s in body["steps"]]
        assert step_numbers == sorted(step_numbers)

    def test_step_fields_present(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_1}").json()
        step = body["steps"][0]
        for field in ("step_name", "step_number", "execution_time_ms", "created_at"):
            assert field in step

    def test_returns_404_for_unknown_run_id(self, seeded_app_client):
        resp = seeded_app_client.get("/api/runs/nonexistent-run-id")
        assert resp.status_code == 404

    def test_running_status_has_null_completed_and_time(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_3}").json()
        assert body["status"] == "running"
        assert body["completed_at"] is None
        assert body["total_time_ms"] is None

    def test_run_with_no_steps_returns_empty_list(self, seeded_app_client):
        # run3 has no step states seeded
        body = seeded_app_client.get(f"/api/runs/{RUN_3}").json()
        assert body["steps"] == []


class TestTriggerRun:
    def _make_client_with_registry(self, factory):
        registry = {"test_pipeline": factory}
        app = create_app(db_path=":memory:", pipeline_registry=registry)
        return TestClient(app)

    def test_returns_202_with_run_id_and_accepted(self):
        executed = []

        class _FakePipeline:
            def __init__(self, run_id, engine):
                self._run_id = run_id

            def execute(self, **kwargs):
                executed.append(self._run_id)

            def save(self):
                pass

        client = self._make_client_with_registry(
            lambda run_id, engine, **kw: _FakePipeline(run_id, engine)
        )
        with client:
            resp = client.post("/api/runs", json={"pipeline_name": "test_pipeline"})
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "accepted"
        assert uuid.UUID(body["run_id"])  # valid UUID, no exception

    def test_run_id_is_valid_uuid(self):
        app = create_app(
            db_path=":memory:",
            pipeline_registry={"p": lambda run_id, engine, **kw: type("P", (), {"execute": lambda s, **kw: None, "save": lambda s: None})()},
        )
        with TestClient(app) as client:
            resp = client.post("/api/runs", json={"pipeline_name": "p"})
        run_id = resp.json()["run_id"]
        parsed = uuid.UUID(run_id)
        assert str(parsed) == run_id

    def test_returns_404_for_unregistered_pipeline(self):
        app = create_app(
            db_path=":memory:",
            pipeline_registry={"other_pipeline": lambda run_id, engine, **kw: None},
        )
        with TestClient(app) as client:
            resp = client.post("/api/runs", json={"pipeline_name": "missing_pipeline"})
        assert resp.status_code == 404

    def test_returns_404_when_registry_empty(self):
        app = create_app(db_path=":memory:")
        with TestClient(app) as client:
            resp = client.post("/api/runs", json={"pipeline_name": "any_pipeline"})
        assert resp.status_code == 404

    def test_background_task_executes_pipeline(self):
        executed = []

        class _TrackedPipeline:
            def __init__(self, run_id, engine):
                self._run_id = run_id

            def execute(self, **kwargs):
                executed.append(self._run_id)

            def save(self):
                pass

        app = create_app(
            db_path=":memory:",
            pipeline_registry={"tracked": lambda run_id, engine, **kw: _TrackedPipeline(run_id, engine)},
        )
        with TestClient(app) as client:
            resp = client.post("/api/runs", json={"pipeline_name": "tracked"})
            assert resp.status_code == 202
        # TestClient context exit flushes background tasks
        assert len(executed) == 1
        assert uuid.UUID(executed[0])

    def test_input_data_threaded_to_factory_and_execute(self):
        """input_data from POST body reaches factory kwargs and pipeline.execute initial_context."""
        factory_kwargs_log = []
        execute_kwargs_log = []

        class _SpyPipeline:
            def __init__(self, **kwargs):
                factory_kwargs_log.append(kwargs)

            def execute(self, **kwargs):
                execute_kwargs_log.append(kwargs)

            def save(self):
                pass

        def _spy_factory(run_id, engine, **kw):
            return _SpyPipeline(run_id=run_id, engine=engine, **kw)

        app = create_app(
            db_path=":memory:",
            pipeline_registry={"spy": _spy_factory},
        )
        payload = {"foo": "bar", "count": 42}
        with TestClient(app) as client:
            resp = client.post("/api/runs", json={"pipeline_name": "spy", "input_data": payload})
            assert resp.status_code == 202
        # factory received input_data kwarg
        assert len(factory_kwargs_log) == 1
        assert factory_kwargs_log[0]["input_data"] == payload
        # execute received initial_context matching input_data
        assert len(execute_kwargs_log) == 1
        assert execute_kwargs_log[0]["initial_context"] == payload
