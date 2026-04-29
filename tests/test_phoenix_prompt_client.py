"""Tests for the Phoenix prompts REST client.

These tests mock ``httpx.Client`` and assert the URL / method / payload
shapes for each operation match the Phoenix OpenAPI spec. They never
hit a live Phoenix instance.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from llm_pipeline.prompts.phoenix_client import (
    PhoenixNotConfiguredError,
    PhoenixPromptClient,
    PhoenixUnavailableError,
    PromptNotFoundError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resp(status: int, payload: object = None) -> MagicMock:
    """Build a MagicMock spec'd to httpx.Response."""
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
    """Patch ``httpx.Client`` so any call to ``client.request(...)``
    returns ``resp``. Returns the patcher and the inner mock client so
    tests can inspect call arguments."""
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
        client = PhoenixPromptClient(base_url="http://phoenix.invalid")
        assert client._base_url == "http://phoenix.invalid"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("PHOENIX_BASE_URL", "http://from-env.invalid/")
        client = PhoenixPromptClient()
        # Trailing slash stripped.
        assert client._base_url == "http://from-env.invalid"

    def test_raises_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("PHOENIX_BASE_URL", raising=False)
        monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
        with pytest.raises(PhoenixNotConfiguredError):
            PhoenixPromptClient()

    def test_explicit_headers_used(self, monkeypatch):
        monkeypatch.setenv("PHOENIX_API_KEY", "from-env")
        client = PhoenixPromptClient(
            base_url="http://x.invalid",
            headers={"X-Test": "explicit"},
        )
        assert client._headers == {"X-Test": "explicit"}


# ---------------------------------------------------------------------------
# Read endpoints
# ---------------------------------------------------------------------------


class TestReadEndpoints:
    def setup_method(self):
        self.client = PhoenixPromptClient(
            base_url="http://phoenix.invalid",
            headers={"api_key": "k"},
        )

    def test_get_by_tag_url_and_returns_data(self):
        cm, http = _client_with_response(
            _resp(200, {"data": {"id": "v1", "model_name": "gpt-4"}}),
        )
        try:
            version = self.client.get_by_tag("widget_detection", "production")
        finally:
            cm.stop()

        http.request.assert_called_once()
        method, url = http.request.call_args.args
        assert method == "GET"
        assert url == "http://phoenix.invalid/v1/prompts/widget_detection/tags/production"
        assert version == {"id": "v1", "model_name": "gpt-4"}

    def test_get_latest_url_and_returns_data(self):
        cm, http = _client_with_response(_resp(200, {"data": {"id": "v9"}}))
        try:
            version = self.client.get_latest("alpha_step")
        finally:
            cm.stop()

        method, url = http.request.call_args.args
        assert method == "GET"
        assert url == "http://phoenix.invalid/v1/prompts/alpha_step/latest"
        assert version == {"id": "v9"}

    def test_list_prompts_passes_pagination(self):
        cm, http = _client_with_response(
            _resp(200, {"data": [{"id": "p1"}], "next_cursor": "abc"}),
        )
        try:
            page = self.client.list_prompts(limit=50, cursor="prev")
        finally:
            cm.stop()

        kwargs = http.request.call_args.kwargs
        assert kwargs["params"] == {"limit": 50, "cursor": "prev"}
        assert page["next_cursor"] == "abc"
        assert page["data"] == [{"id": "p1"}]

    def test_list_versions_url(self):
        cm, http = _client_with_response(
            _resp(200, {"data": [], "next_cursor": None}),
        )
        try:
            self.client.list_versions("alpha_step", limit=20)
        finally:
            cm.stop()
        method, url = http.request.call_args.args
        assert method == "GET"
        assert url == "http://phoenix.invalid/v1/prompts/alpha_step/versions"
        assert http.request.call_args.kwargs["params"] == {"limit": 20}

    def test_get_version_url(self):
        cm, http = _client_with_response(_resp(200, {"data": {"id": "vid"}}))
        try:
            self.client.get_version("vid")
        finally:
            cm.stop()
        method, url = http.request.call_args.args
        assert method == "GET"
        assert url == "http://phoenix.invalid/v1/prompt_versions/vid"


# ---------------------------------------------------------------------------
# Write endpoints
# ---------------------------------------------------------------------------


class TestWriteEndpoints:
    def setup_method(self):
        self.client = PhoenixPromptClient(base_url="http://phoenix.invalid")

    def test_create_posts_prompt_and_version(self):
        cm, http = _client_with_response(
            _resp(200, {"data": {"id": "v_new"}}),
        )
        try:
            new = self.client.create(
                prompt={"name": "alpha_step", "metadata": {"foo": "bar"}},
                version={
                    "model_provider": "OPENAI",
                    "model_name": "gpt-4o-mini",
                    "template": {
                        "type": "chat",
                        "messages": [
                            {"role": "system", "content": "be helpful"},
                            {"role": "user", "content": "{q}"},
                        ],
                    },
                    "template_type": "CHAT",
                    "template_format": "F_STRING",
                    "invocation_parameters": {"type": "openai", "openai": {}},
                },
            )
        finally:
            cm.stop()

        method, url = http.request.call_args.args
        json_body = http.request.call_args.kwargs["json"]
        assert method == "POST"
        assert url == "http://phoenix.invalid/v1/prompts"
        assert json_body["prompt"]["name"] == "alpha_step"
        assert json_body["prompt"]["metadata"] == {"foo": "bar"}
        assert json_body["version"]["template_type"] == "CHAT"
        assert new == {"id": "v_new"}

    def test_create_rejects_invalid_identifier(self):
        # Phoenix identifiers don't allow dots — a key like
        # "widget_detection.system_instruction" must be reduced before
        # being passed to the client.
        with pytest.raises(ValueError, match="not a valid identifier"):
            self.client.create(
                prompt={"name": "widget_detection.system_instruction"},
                version={},
            )

    def test_delete_url(self):
        cm, http = _client_with_response(_resp(204))
        try:
            self.client.delete("alpha_step")
        finally:
            cm.stop()
        method, url = http.request.call_args.args
        assert method == "DELETE"
        assert url == "http://phoenix.invalid/v1/prompts/alpha_step"

    def test_add_tag_posts_payload(self):
        cm, http = _client_with_response(_resp(200, {"data": {"id": "t1"}}))
        try:
            self.client.add_tag("vid", "production", description="released")
        finally:
            cm.stop()

        method, url = http.request.call_args.args
        body = http.request.call_args.kwargs["json"]
        assert method == "POST"
        assert url == "http://phoenix.invalid/v1/prompt_versions/vid/tags"
        assert body == {"name": "production", "description": "released"}

    def test_delete_tag_url(self):
        cm, http = _client_with_response(_resp(204))
        try:
            self.client.delete_tag("vid", "production")
        finally:
            cm.stop()
        method, url = http.request.call_args.args
        assert method == "DELETE"
        assert url == "http://phoenix.invalid/v1/prompt_versions/vid/tags/production"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    def setup_method(self):
        self.client = PhoenixPromptClient(base_url="http://phoenix.invalid")

    def test_404_raises_prompt_not_found(self):
        cm, _ = _client_with_response(_resp(404))
        try:
            with pytest.raises(PromptNotFoundError):
                self.client.get_latest("missing_step")
        finally:
            cm.stop()

    def test_500_raises_unavailable(self):
        cm, _ = _client_with_response(_resp(500))
        try:
            with pytest.raises(PhoenixUnavailableError):
                self.client.get_latest("alpha_step")
        finally:
            cm.stop()

    def test_connect_error_raises_unavailable(self):
        cm = patch("httpx.Client")
        client_cls = cm.start()
        try:
            client = client_cls.return_value.__enter__.return_value
            client.request.side_effect = httpx.ConnectError("refused")
            with pytest.raises(PhoenixUnavailableError):
                self.client.get_latest("alpha_step")
        finally:
            cm.stop()
