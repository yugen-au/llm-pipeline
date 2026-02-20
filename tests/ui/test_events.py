"""Endpoint tests for /api/runs/{run_id}/events routes."""

RUN_1 = "aaaaaaaa-0000-0000-0000-000000000001"
RUN_2 = "aaaaaaaa-0000-0000-0000-000000000002"
RUN_3 = "aaaaaaaa-0000-0000-0000-000000000003"
NONEXISTENT = "ffffffff-0000-0000-0000-000000000099"


class TestListEvents:
    def test_returns_200_with_events_for_run1(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{RUN_1}/events")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 4

    def test_events_ordered_by_timestamp_asc(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{RUN_1}/events")
        items = resp.json()["items"]
        timestamps = [item["timestamp"] for item in items]
        assert timestamps == sorted(timestamps)

    def test_event_fields_present(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_1}/events").json()
        item = body["items"][0]
        for field in ("event_type", "pipeline_name", "run_id", "timestamp", "event_data"):
            assert field in item

    def test_response_pagination_fields_present(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_1}/events").json()
        for field in ("items", "total", "offset", "limit"):
            assert field in body

    def test_total_matches_row_count(self, seeded_app_client):
        body = seeded_app_client.get(f"/api/runs/{RUN_1}/events").json()
        assert body["total"] == len(body["items"])
        assert body["total"] == 4

    def test_filter_by_event_type(self, seeded_app_client):
        resp = seeded_app_client.get(
            f"/api/runs/{RUN_1}/events", params={"event_type": "pipeline_started"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["event_type"] == "pipeline_started"

    def test_filter_by_event_type_no_match(self, seeded_app_client):
        resp = seeded_app_client.get(
            f"/api/runs/{RUN_1}/events", params={"event_type": "nonexistent_type"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []

    def test_returns_empty_list_for_run_with_no_events(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{RUN_2}/events")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_404_for_nonexistent_run(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{NONEXISTENT}/events")
        assert resp.status_code == 404

    def test_pagination_limit(self, seeded_app_client):
        resp = seeded_app_client.get(
            f"/api/runs/{RUN_1}/events", params={"limit": 2}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 4

    def test_pagination_offset(self, seeded_app_client):
        resp = seeded_app_client.get(
            f"/api/runs/{RUN_1}/events", params={"offset": 2, "limit": 10}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 2
        assert body["total"] == 4

    def test_limit_above_500_returns_422(self, seeded_app_client):
        resp = seeded_app_client.get(
            f"/api/runs/{RUN_1}/events", params={"limit": 501}
        )
        assert resp.status_code == 422

    def test_negative_offset_returns_422(self, seeded_app_client):
        resp = seeded_app_client.get(
            f"/api/runs/{RUN_1}/events", params={"offset": -1}
        )
        assert resp.status_code == 422
