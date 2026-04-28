"""Tests for the /runs/{run_id}/trace endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 404 + langfuse-unconfigured paths
# ---------------------------------------------------------------------------


class TestTraceEndpoint404AndUnconfigured:
    def test_returns_404_for_unknown_run_id(self, seeded_app_client):
        resp = seeded_app_client.get("/api/runs/no-such-run/trace")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Run not found"

    def test_returns_empty_traces_when_langfuse_unconfigured(
        self, seeded_app_client, monkeypatch,
    ):
        """conftest auto-strips LANGFUSE_* in tests; verify the endpoint
        responds gracefully without Langfuse configuration."""
        monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
        monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

        resp = seeded_app_client.get(
            "/api/runs/aaaaaaaa-0000-0000-0000-000000000001/trace",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["run_id"] == "aaaaaaaa-0000-0000-0000-000000000001"
        assert body["pipeline_name"] == "alpha_pipeline"
        assert body["langfuse_configured"] is False
        assert body["traces"] == []
        assert body["observations"] == []


# ---------------------------------------------------------------------------
# Path with mocked Langfuse SDK
# ---------------------------------------------------------------------------


def _make_mock_observation(
    *, id: str, name: str, type_: str = "SPAN",
    parent_id: str | None = None,
    start_offset: int = 0, end_offset: int = 1000,
    model: str | None = None, input_tokens: int | None = None,
    output_tokens: int | None = None, cost: float | None = None,
):
    """Build a MagicMock standing in for a Langfuse ObservationsView item."""
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    obs = MagicMock()
    obs.id = id
    obs.name = name
    obs.type = type_
    obs.parent_observation_id = parent_id
    obs.start_time = datetime.fromtimestamp(
        base.timestamp() + start_offset / 1000, tz=timezone.utc,
    )
    obs.end_time = datetime.fromtimestamp(
        base.timestamp() + end_offset / 1000, tz=timezone.utc,
    )
    obs.level = "DEFAULT"
    obs.status_message = None
    obs.model = model
    obs.usage_details = (
        {"input": input_tokens, "output": output_tokens,
         "total": (input_tokens or 0) + (output_tokens or 0)}
        if input_tokens is not None or output_tokens is not None else {}
    )
    obs.cost_details = {"total": cost} if cost is not None else {}
    obs.input = {"q": "hello"} if type_ == "GENERATION" else None
    obs.output = "hi" if type_ == "GENERATION" else None
    obs.metadata = {}
    return obs


class TestTraceEndpointWithMockedLangfuse:
    def test_returns_traces_with_observations(
        self, seeded_app_client, monkeypatch,
    ):
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-fake")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-fake")

        # Mock the Langfuse SDK's trace API.
        # `list` returns minimal stubs (only id) — the route then calls
        # `trace.get` to fetch the full TraceWithFullDetails (including
        # nested observations with names/inputs/usage).
        mock_trace_stub = MagicMock()
        mock_trace_stub.id = "lf-trace-1"

        mock_traces_page = MagicMock()
        mock_traces_page.data = [mock_trace_stub]

        mock_full_trace = MagicMock()
        mock_full_trace.id = "lf-trace-1"
        mock_full_trace.name = "pipeline.alpha_pipeline"
        mock_full_trace.user_id = None
        mock_full_trace.session_id = "aaaaaaaa-0000-0000-0000-000000000001"
        mock_full_trace.tags = ["alpha_pipeline"]
        mock_full_trace.timestamp = datetime(
            2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc,
        )
        mock_full_trace.latency = 1.234
        mock_full_trace.observations = [
            _make_mock_observation(
                id="obs-root", name="pipeline.alpha_pipeline", type_="SPAN",
                start_offset=0, end_offset=1234,
            ),
            _make_mock_observation(
                id="obs-step", name="step.detect", type_="SPAN",
                parent_id="obs-root",
                start_offset=10, end_offset=900,
            ),
            _make_mock_observation(
                id="obs-llm", name="gen_ai chat openai:gpt-4",
                type_="GENERATION",
                parent_id="obs-step",
                start_offset=20, end_offset=850,
                model="gpt-4", input_tokens=142, output_tokens=89,
                cost=0.0011,
            ),
        ]

        mock_client_cls = MagicMock()
        mock_client = mock_client_cls.return_value
        mock_client.api.trace.list.return_value = mock_traces_page
        mock_client.api.trace.get.return_value = mock_full_trace

        with patch("langfuse.Langfuse", mock_client_cls):
            resp = seeded_app_client.get(
                "/api/runs/aaaaaaaa-0000-0000-0000-000000000001/trace",
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["langfuse_configured"] is True
        assert len(body["traces"]) == 1

        trace = body["traces"][0]
        assert trace["id"] == "lf-trace-1"
        assert trace["name"] == "pipeline.alpha_pipeline"
        assert trace["session_id"] == "aaaaaaaa-0000-0000-0000-000000000001"
        assert trace["tags"] == ["alpha_pipeline"]
        assert len(trace["observations"]) == 3

        # Generation observation has token + cost details
        gen = next(o for o in trace["observations"] if o["type"] == "GENERATION")
        assert gen["model"] == "gpt-4"
        assert gen["input_tokens"] == 142
        assert gen["output_tokens"] == 89
        assert gen["total_cost"] == 0.0011

        # Flat observations array contains all 3 (sorted by start_time)
        assert len(body["observations"]) == 3
        assert [o["id"] for o in body["observations"]] == [
            "obs-root", "obs-step", "obs-llm",
        ]

        mock_client.api.trace.list.assert_called_once_with(
            session_id="aaaaaaaa-0000-0000-0000-000000000001", limit=50,
        )

    def test_swallows_langfuse_errors(self, seeded_app_client, monkeypatch):
        """If Langfuse SDK throws (network error, auth, etc.), the
        endpoint returns langfuse_configured=True with empty traces
        rather than failing the request — the run-detail page must
        still render."""
        monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-fake")
        monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-fake")

        mock_client_cls = MagicMock(side_effect=RuntimeError("langfuse down"))
        with patch("langfuse.Langfuse", mock_client_cls):
            resp = seeded_app_client.get(
                "/api/runs/aaaaaaaa-0000-0000-0000-000000000001/trace",
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["langfuse_configured"] is True
        assert body["traces"] == []
