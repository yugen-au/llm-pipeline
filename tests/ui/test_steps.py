"""Endpoint tests for steps list/detail and context evolution routes."""

RUN_1 = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_2 = "aaaaaaaa-0000-0000-0000-000000000002"
RUN_3 = "aaaaaaaa-0000-0000-0000-000000000003"
NONEXISTENT = "ffffffff-0000-0000-0000-000000000099"


class TestListSteps:
    def test_returns_200_with_steps_for_run1(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{RUN_1}/steps")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2

    def test_steps_ordered_by_step_number_asc(self, seeded_app_client):
        items = seeded_app_client.get(f"/api/runs/{RUN_1}/steps").json()["items"]
        numbers = [i["step_number"] for i in items]
        assert numbers == sorted(numbers)

    def test_step_fields_present(self, seeded_app_client):
        item = seeded_app_client.get(f"/api/runs/{RUN_1}/steps").json()["items"][0]
        for field in ("step_name", "step_number", "execution_time_ms", "created_at", "model"):
            assert field in item

    def test_returns_empty_list_for_run_with_no_steps(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_3}/steps").json()
        assert body["items"] == []

    def test_returns_404_for_nonexistent_run(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{NONEXISTENT}/steps")
        assert resp.status_code == 404


class TestGetStep:
    def test_returns_200_with_full_step_detail(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{RUN_1}/steps/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["result_data"] == {"value": 1}
        assert body["context_snapshot"] == {"k": "v"}
        assert body["pipeline_name"] == "alpha_pipeline"
        assert body["run_id"] == RUN_1

    def test_step_detail_fields_present(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_1}/steps/1").json()
        expected = (
            "step_name", "step_number", "pipeline_name", "run_id",
            "input_hash", "result_data", "context_snapshot",
            "prompt_system_key", "prompt_user_key", "prompt_version",
            "model", "execution_time_ms", "created_at",
        )
        for field in expected:
            assert field in body

    def test_returns_404_for_nonexistent_step_number(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{RUN_1}/steps/999")
        assert resp.status_code == 404

    def test_returns_404_for_nonexistent_run(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{NONEXISTENT}/steps/1")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Run not found"


class TestContextEvolution:
    def test_returns_200_with_snapshots_for_run1(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{RUN_1}/context")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["snapshots"]) == 2

    def test_snapshots_ordered_by_step_number_asc(self, seeded_app_client):
        snapshots = seeded_app_client.get(f"/api/runs/{RUN_1}/context").json()["snapshots"]
        numbers = [s["step_number"] for s in snapshots]
        assert numbers == sorted(numbers)

    def test_snapshot_fields_present(self, seeded_app_client):
        snap = seeded_app_client.get(f"/api/runs/{RUN_1}/context").json()["snapshots"][0]
        for field in ("step_name", "step_number", "context_snapshot"):
            assert field in snap

    def test_returns_empty_snapshots_for_run_with_no_steps(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_3}/context").json()
        assert body["snapshots"] == []

    def test_returns_404_for_nonexistent_run(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{NONEXISTENT}/context")
        assert resp.status_code == 404
