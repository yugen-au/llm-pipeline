"""Tests for the Phoenix datasets/experiments REST client.

Mocks ``httpx.Client`` directly — same pattern as
``tests/test_phoenix_prompt_client.py``. Asserts URL/method/payload
shapes match the surface documented in the client module.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from llm_pipeline.evals.phoenix_client import (
    DatasetNotFoundError,
    ExperimentNotFoundError,
    PhoenixDatasetClient,
    PhoenixDatasetNotConfiguredError,
    PhoenixDatasetUnavailableError,
)


def _resp(status: int, payload: object = None) -> MagicMock:
    r = MagicMock(spec=httpx.Response)
    r.status_code = status
    r.content = b"" if payload is None else b"{}"
    r.text = "" if payload is None else "..."
    if payload is None:
        r.json.side_effect = ValueError("no body")
    else:
        r.json.return_value = payload
    return r


def _client_with_response(resp: MagicMock):
    cm = patch("httpx.Client")
    client_cls = cm.start()
    client = client_cls.return_value.__enter__.return_value
    client.request.return_value = resp
    return cm, client


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestConstructor:
    def test_explicit_base_url_overrides_env(self, monkeypatch):
        monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        client = PhoenixDatasetClient(base_url="http://phoenix.invalid")
        assert client._base_url == "http://phoenix.invalid"

    def test_strips_trailing_slash(self):
        client = PhoenixDatasetClient(base_url="http://phoenix.invalid/")
        assert client._base_url == "http://phoenix.invalid"

    def test_raises_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        with pytest.raises(PhoenixDatasetNotConfiguredError):
            PhoenixDatasetClient()

    def test_explicit_headers_override_env(self, monkeypatch):
        monkeypatch.setenv("PHOENIX_API_KEY", "from-env")
        client = PhoenixDatasetClient(
            base_url="http://x.invalid",
            headers={"X-Test": "explicit"},
        )
        assert client._headers == {"X-Test": "explicit"}


# ---------------------------------------------------------------------------
# Datasets
# ---------------------------------------------------------------------------


class TestDatasetEndpoints:
    def setup_method(self):
        self.client = PhoenixDatasetClient(base_url="http://phoenix.invalid")

    def test_list_datasets(self):
        cm, http = _client_with_response(_resp(200, {"data": [{"id": "d1"}]}))
        try:
            result = self.client.list_datasets(limit=50)
            args, kwargs = http.request.call_args
            assert args[0] == "GET"
            assert args[1] == "http://phoenix.invalid/v1/datasets"
            assert kwargs["params"] == {"limit": 50}
            assert result == {"data": [{"id": "d1"}]}
        finally:
            cm.stop()

    def test_get_dataset_returns_data(self):
        cm, http = _client_with_response(
            _resp(200, {"data": {"id": "d1", "name": "alpha"}}),
        )
        try:
            result = self.client.get_dataset("d1")
            args, _ = http.request.call_args
            assert args[1] == "http://phoenix.invalid/v1/datasets/d1"
            assert result == {"id": "d1", "name": "alpha"}
        finally:
            cm.stop()

    def test_get_dataset_404_raises(self):
        cm, _ = _client_with_response(_resp(404))
        try:
            with pytest.raises(DatasetNotFoundError):
                self.client.get_dataset("missing")
        finally:
            cm.stop()

    def test_delete_dataset(self):
        cm, http = _client_with_response(_resp(204))
        try:
            self.client.delete_dataset("d1")
            args, _ = http.request.call_args
            assert args[0] == "DELETE"
            assert args[1] == "http://phoenix.invalid/v1/datasets/d1"
        finally:
            cm.stop()

    def test_upload_dataset_validates_identifier(self):
        with pytest.raises(ValueError):
            self.client.upload_dataset(
                name="Has Spaces",
                examples=[{"input": {"x": 1}}],
            )

    def test_upload_dataset_payload_shape(self):
        cm, http = _client_with_response(
            _resp(200, {"data": {"dataset_id": "d1"}}),
        )
        try:
            self.client.upload_dataset(
                name="alpha_dataset",
                examples=[
                    {"input": {"text": "a"}, "output": {"label": "x"}},
                    {"input": {"text": "b"}, "metadata": {"evaluators": ["foo"]}},
                ],
                description="desc",
                metadata={"target_type": "step", "target_name": "Classify"},
            )
            args, kwargs = http.request.call_args
            assert args[0] == "POST"
            assert args[1] == "http://phoenix.invalid/v1/datasets/upload"
            body = kwargs["json"]
            assert body["name"] == "alpha_dataset"
            assert body["action"] == "create"
            assert body["inputs"] == [{"text": "a"}, {"text": "b"}]
            assert body["outputs"] == [{"label": "x"}, {}]
            assert body["metadata"] == [{}, {"evaluators": ["foo"]}]
            assert body["description"] == "desc"
            assert body["dataset_metadata"] == {
                "target_type": "step",
                "target_name": "Classify",
            }
        finally:
            cm.stop()


# ---------------------------------------------------------------------------
# Examples
# ---------------------------------------------------------------------------


class TestExampleEndpoints:
    def setup_method(self):
        self.client = PhoenixDatasetClient(base_url="http://phoenix.invalid")

    def test_list_examples(self):
        cm, http = _client_with_response(_resp(200, {"data": []}))
        try:
            self.client.list_examples("d1", version_id="v9")
            args, kwargs = http.request.call_args
            assert args[1] == "http://phoenix.invalid/v1/datasets/d1/examples"
            assert kwargs["params"] == {"version_id": "v9"}
        finally:
            cm.stop()

    def test_add_examples_payload(self):
        cm, http = _client_with_response(_resp(200, {"data": {}}))
        try:
            self.client.add_examples(
                "d1",
                [{"input": {"text": "x"}, "output": {"label": "y"}}],
            )
            args, kwargs = http.request.call_args
            assert args[0] == "POST"
            assert args[1] == "http://phoenix.invalid/v1/datasets/d1/examples"
            assert kwargs["json"] == {
                "inputs": [{"text": "x"}],
                "outputs": [{"label": "y"}],
                "metadata": [{}],
            }
        finally:
            cm.stop()

    def test_delete_example(self):
        cm, http = _client_with_response(_resp(204))
        try:
            self.client.delete_example("d1", "ex42")
            args, _ = http.request.call_args
            assert args[0] == "DELETE"
            assert args[1] == "http://phoenix.invalid/v1/datasets/d1/examples/ex42"
        finally:
            cm.stop()


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------


class TestExperimentEndpoints:
    def setup_method(self):
        self.client = PhoenixDatasetClient(base_url="http://phoenix.invalid")

    def test_create_experiment(self):
        cm, http = _client_with_response(
            _resp(200, {"data": {"id": "exp1"}}),
        )
        try:
            self.client.create_experiment(
                "d1",
                name="baseline",
                description="first run",
                metadata={"variant": {"model": "gpt-5"}},
            )
            args, kwargs = http.request.call_args
            assert args[0] == "POST"
            assert args[1] == "http://phoenix.invalid/v1/datasets/d1/experiments"
            assert kwargs["json"] == {
                "name": "baseline",
                "description": "first run",
                "metadata": {"variant": {"model": "gpt-5"}},
            }
        finally:
            cm.stop()

    def test_get_experiment_404_raises_experiment_not_found(self):
        cm, _ = _client_with_response(_resp(404))
        try:
            with pytest.raises(ExperimentNotFoundError):
                self.client.get_experiment("missing")
        finally:
            cm.stop()

    def test_list_experiments(self):
        cm, http = _client_with_response(_resp(200, {"data": []}))
        try:
            self.client.list_experiments("d1")
            args, _ = http.request.call_args
            assert args[1] == "http://phoenix.invalid/v1/datasets/d1/experiments"
        finally:
            cm.stop()


# ---------------------------------------------------------------------------
# Runs + evaluations
# ---------------------------------------------------------------------------


class TestRunAndEvaluationEndpoints:
    def setup_method(self):
        self.client = PhoenixDatasetClient(base_url="http://phoenix.invalid")

    def test_record_run_payload(self):
        cm, http = _client_with_response(
            _resp(200, {"data": {"id": "r1"}}),
        )
        try:
            self.client.record_run(
                "exp1",
                dataset_example_id="ex42",
                output={"label": "x"},
                start_time="2026-04-29T00:00:00Z",
                end_time="2026-04-29T00:00:01Z",
                trace_id="trace-xyz",
            )
            args, kwargs = http.request.call_args
            assert args[0] == "POST"
            assert args[1] == "http://phoenix.invalid/v1/experiments/exp1/runs"
            body = kwargs["json"]
            assert body["dataset_example_id"] == "ex42"
            assert body["output"] == {"label": "x"}
            assert body["start_time"] == "2026-04-29T00:00:00Z"
            assert body["end_time"] == "2026-04-29T00:00:01Z"
            assert body["trace_id"] == "trace-xyz"
            assert body["repetition_number"] == 1
        finally:
            cm.stop()

    def test_record_run_404_raises_experiment_not_found(self):
        cm, _ = _client_with_response(_resp(404))
        try:
            with pytest.raises(ExperimentNotFoundError):
                self.client.record_run(
                    "missing",
                    dataset_example_id="ex42",
                    output={},
                )
        finally:
            cm.stop()

    def test_attach_evaluation_payload(self):
        cm, http = _client_with_response(_resp(200, {"data": {"id": "e1"}}))
        try:
            self.client.attach_evaluation(
                "exp1",
                "run1",
                name="label_match",
                label="match",
                score=1.0,
                explanation="exact",
            )
            args, kwargs = http.request.call_args
            assert args[0] == "POST"
            assert (
                args[1]
                == "http://phoenix.invalid/v1/experiments/exp1/runs/run1/evaluations"
            )
            assert kwargs["json"] == {
                "name": "label_match",
                "label": "match",
                "score": 1.0,
                "explanation": "exact",
            }
        finally:
            cm.stop()


# ---------------------------------------------------------------------------
# Error surface
# ---------------------------------------------------------------------------


class TestErrorSurface:
    def setup_method(self):
        self.client = PhoenixDatasetClient(base_url="http://phoenix.invalid")

    def test_5xx_raises_unavailable(self):
        cm, _ = _client_with_response(_resp(500, {}))
        try:
            with pytest.raises(PhoenixDatasetUnavailableError):
                self.client.list_datasets()
        finally:
            cm.stop()

    def test_connection_error_raises_unavailable(self):
        cm = patch("httpx.Client")
        client_cls = cm.start()
        client = client_cls.return_value.__enter__.return_value
        client.request.side_effect = httpx.ConnectError("boom")
        try:
            with pytest.raises(PhoenixDatasetUnavailableError):
                self.client.list_datasets()
        finally:
            cm.stop()
