"""Tests for the /runs/{run_id}/trace endpoint."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx


# ---------------------------------------------------------------------------
# 404 + unconfigured paths
# ---------------------------------------------------------------------------


class TestTraceEndpoint404AndUnconfigured:
    def test_returns_404_for_unknown_run_id(self, seeded_app_client):
        resp = seeded_app_client.get("/api/runs/no-such-run/trace")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Run not found"

    def test_returns_empty_when_no_backend_configured(
        self, seeded_app_client, monkeypatch,
    ):
        """conftest auto-strips OTEL/Phoenix env vars; verify the
        endpoint responds gracefully without a backend URL configured."""
        monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

        resp = seeded_app_client.get(
            "/api/runs/aaaaaaaa-0000-0000-0000-000000000001/trace",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == "aaaaaaaa-0000-0000-0000-000000000001"
        assert body["pipeline_name"] == "alpha_pipeline"
        assert body["trace_backend_configured"] is False
        assert body["traces"] == []
        assert body["observations"] == []


# ---------------------------------------------------------------------------
# Phoenix REST happy path
# ---------------------------------------------------------------------------


def _phoenix_response(data):
    """Build a MagicMock httpx.Response carrying ``{"data": data}``."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"data": data}
    resp.raise_for_status.return_value = None
    return resp


def _two_step_phoenix(traces, spans_by_trace):
    """Build a side_effect for ``client.get`` that mirrors the two-step
    Phoenix fetch: first call -> trace list, subsequent calls -> spans
    keyed on the ``trace_id`` query parameter.
    """
    def _handler(url, params=None, **kwargs):
        params = params or {}
        if url.endswith("/traces"):
            return _phoenix_response(traces)
        if url.endswith("/spans"):
            tid = params.get("trace_id")
            return _phoenix_response(spans_by_trace.get(tid, []))
        return _phoenix_response([])
    return _handler


class TestTraceEndpointPhoenixHappyPath:
    def test_maps_phoenix_spans_to_observations(
        self, seeded_app_client, monkeypatch,
    ):
        monkeypatch.setenv("PHOENIX_BASE_URL", "http://phoenix.invalid")
        monkeypatch.setenv("PHOENIX_PROJECT", "default")

        trace_id = "abcd1234abcd1234abcd1234abcd1234"
        # Phoenix's traces endpoint (with include_spans=false) returns
        # a list of trace metadata. Each entry's spans field is empty.
        traces = [
            {
                "id": "trace-internal-1",
                "trace_id": trace_id,
                "project_id": "UHJvamVjdDox",
                "start_time": "2026-01-01T12:00:00+00:00",
                "end_time": "2026-01-01T12:00:01+00:00",
                "spans": [],
            },
        ]
        # Phoenix's spans endpoint returns full span detail. Phoenix
        # mirrors the OTEL span_id at the top level, and parent_id
        # also references the OTEL hex span_id directly. Attributes
        # are populated.
        spans = [
            {
                "id": "span-root",
                "span_id": "0000000000000001",
                "name": "pipeline.alpha_pipeline",
                "span_kind": "CHAIN",
                "parent_id": None,
                "start_time": "2026-01-01T12:00:00+00:00",
                "end_time": "2026-01-01T12:00:01+00:00",
                "status_code": "OK",
                "status_message": "",
                "attributes": {
                    "session.id": "aaaaaaaa-0000-0000-0000-000000000001",
                    "openinference.span.kind": "CHAIN",
                    "input.value": '{"data": "raw"}',
                    "input.mime_type": "application/json",
                    "tag.tags": '["alpha_pipeline"]',
                },
                "events": [],
            },
            {
                "id": "span-step",
                "span_id": "0000000000000002",
                "name": "step.detect",
                "span_kind": "CHAIN",
                "parent_id": "0000000000000001",
                "start_time": "2026-01-01T12:00:00.100+00:00",
                "end_time": "2026-01-01T12:00:00.900+00:00",
                "status_code": "OK",
                "status_message": "",
                "attributes": {
                    "openinference.span.kind": "CHAIN",
                    "session.id": "aaaaaaaa-0000-0000-0000-000000000001",
                },
                "events": [],
            },
            {
                "id": "span-llm",
                "span_id": "0000000000000003",
                "name": "chat openai:gpt-4",
                "span_kind": "LLM",
                "parent_id": "0000000000000002",
                "start_time": "2026-01-01T12:00:00.200+00:00",
                "end_time": "2026-01-01T12:00:00.850+00:00",
                "status_code": "OK",
                "status_message": "",
                "attributes": {
                    "gen_ai.request.model": "gpt-4",
                    "gen_ai.usage.input_tokens": 142,
                    "gen_ai.usage.output_tokens": 89,
                },
                "events": [],
            },
        ]

        with patch("httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.side_effect = _two_step_phoenix(
                traces, {trace_id: spans},
            )
            resp = seeded_app_client.get(
                "/api/runs/aaaaaaaa-0000-0000-0000-000000000001/trace",
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_backend_configured"] is True
        assert len(body["traces"]) == 1

        trace = body["traces"][0]
        assert trace["id"] == trace_id
        assert trace["session_id"] == "aaaaaaaa-0000-0000-0000-000000000001"
        assert trace["tags"] == ["alpha_pipeline"]
        assert len(trace["observations"]) == 3

        # Generation classification + token rollup.
        gen = next(o for o in trace["observations"] if o["type"] == "GENERATION")
        assert gen["model"] == "gpt-4"
        assert gen["input_tokens"] == 142
        assert gen["output_tokens"] == 89
        assert gen["total_tokens"] == 142 + 89

        # parent_observation_id resolves to OTEL span_id (passes through
        # parent_id directly when it's already a hex span_id).
        step = next(o for o in trace["observations"] if o["name"] == "step.detect")
        assert step["parent_observation_id"] == "0000000000000001"
        assert gen["parent_observation_id"] == "0000000000000002"

        # Top-level observations array is the flat union, sorted by start_time.
        assert len(body["observations"]) == 3
        assert [o["id"] for o in body["observations"]] == [
            "0000000000000001",
            "0000000000000002",
            "0000000000000003",
        ]

        # Verify both Phoenix endpoints were hit.
        urls = [call.args[0] for call in client.get.call_args_list]
        assert any(u.endswith("/v1/projects/default/traces") for u in urls)
        assert any(u.endswith("/v1/projects/default/spans") for u in urls)

    def test_swallows_phoenix_errors(self, seeded_app_client, monkeypatch):
        """If Phoenix is unreachable / 5xx, return empty traces (with
        ``trace_backend_configured=True``) rather than failing the
        request — the run-detail page must still render."""
        monkeypatch.setenv("PHOENIX_BASE_URL", "http://phoenix.invalid")

        with patch("httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.side_effect = httpx.ConnectError("connection refused")
            resp = seeded_app_client.get(
                "/api/runs/aaaaaaaa-0000-0000-0000-000000000001/trace",
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["trace_backend_configured"] is True
        assert body["traces"] == []

    def test_404_from_phoenix_returns_empty(self, seeded_app_client, monkeypatch):
        """Project doesn't exist yet → empty traces, no error surfaced."""
        monkeypatch.setenv("PHOENIX_BASE_URL", "http://phoenix.invalid")

        with patch("httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            resp_obj = MagicMock(spec=httpx.Response)
            resp_obj.status_code = 404
            client.get.return_value = resp_obj
            resp = seeded_app_client.get(
                "/api/runs/aaaaaaaa-0000-0000-0000-000000000001/trace",
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["traces"] == []

    def test_phoenix_url_derived_from_otlp_endpoint(
        self, seeded_app_client, monkeypatch,
    ):
        """If only OTEL_EXPORTER_OTLP_ENDPOINT is set, derive the
        Phoenix base URL by stripping the /v1/traces suffix."""
        monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
        monkeypatch.setenv(
            "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:6006/v1/traces",
        )

        with patch("httpx.Client") as client_cls:
            client = client_cls.return_value.__enter__.return_value
            client.get.return_value = _phoenix_response([])
            seeded_app_client.get(
                "/api/runs/aaaaaaaa-0000-0000-0000-000000000001/trace",
            )

        assert client.get.called
        url = client.get.call_args[0][0]
        assert url.startswith("http://localhost:6006/v1/projects/")
