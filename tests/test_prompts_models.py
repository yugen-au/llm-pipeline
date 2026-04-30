"""Tests for ``llm_pipeline.prompts.models``.

Covers the canonical ``Prompt`` round-trip + the pydantic-ai ↔ Phoenix
model-string mapping helpers.
"""
from __future__ import annotations

import pytest

from llm_pipeline.prompts.models import (
    ModelStringError,
    Prompt,
    PromptMessage,
    PromptMetadata,
    pai_model_to_phoenix,
    phoenix_model_to_pai,
    phoenix_to_prompt,
    prompt_to_phoenix_payloads,
)


class TestPaiModelToPhoenix:
    def test_openai_round_trip(self):
        assert pai_model_to_phoenix("openai:gpt-5") == ("OPENAI", "gpt-5")

    def test_anthropic_round_trip(self):
        assert pai_model_to_phoenix("anthropic:claude-3-5-sonnet-latest") == (
            "ANTHROPIC", "claude-3-5-sonnet-latest",
        )

    def test_google_gla_maps_to_gemini(self):
        assert pai_model_to_phoenix("google-gla:gemini-2.0-flash") == (
            "GEMINI", "gemini-2.0-flash",
        )

    def test_google_vertex_also_maps_to_gemini(self):
        assert pai_model_to_phoenix("google-vertex:gemini-pro") == (
            "GEMINI", "gemini-pro",
        )

    def test_unknown_provider_falls_back_to_uppercase(self):
        assert pai_model_to_phoenix("foo:bar") == ("FOO", "bar")

    def test_missing_colon_raises(self):
        with pytest.raises(ModelStringError):
            pai_model_to_phoenix("just-a-name")

    def test_empty_provider_raises(self):
        with pytest.raises(ModelStringError):
            pai_model_to_phoenix(":gpt-5")

    def test_empty_name_raises(self):
        with pytest.raises(ModelStringError):
            pai_model_to_phoenix("openai:")


class TestPhoenixModelToPai:
    def test_openai_round_trip(self):
        assert phoenix_model_to_pai("OPENAI", "gpt-5") == "openai:gpt-5"

    def test_gemini_normalises_to_google_gla(self):
        assert phoenix_model_to_pai("GEMINI", "gemini-2.0-flash") == (
            "google-gla:gemini-2.0-flash"
        )

    def test_unknown_provider_falls_back_to_lowercase(self):
        assert phoenix_model_to_pai("XAI", "grok-3") == "xai:grok-3"

    def test_missing_provider_returns_none(self):
        assert phoenix_model_to_pai(None, "gpt-5") is None
        assert phoenix_model_to_pai("", "gpt-5") is None

    def test_missing_name_returns_none(self):
        assert phoenix_model_to_pai("OPENAI", None) is None
        assert phoenix_model_to_pai("OPENAI", "") is None


class TestPromptModelRoundTrip:
    def _prompt(self, model: str | None = "openai:gpt-5") -> Prompt:
        return Prompt(
            name="test_prompt",
            metadata=PromptMetadata(category="t"),
            messages=[
                PromptMessage(role="system", content="s"),
                PromptMessage(role="user", content="u"),
            ],
            model=model,
        )

    def test_phoenix_payload_carries_model(self):
        prompt = self._prompt()
        _, version_data = prompt_to_phoenix_payloads(prompt)
        assert version_data["model_provider"] == "OPENAI"
        assert version_data["model_name"] == "gpt-5"

    def test_phoenix_to_prompt_extracts_model(self):
        record = {"name": "test_prompt", "metadata": {}}
        version = {
            "id": "v1",
            "template": {
                "type": "chat",
                "messages": [
                    {"role": "system", "content": "s"},
                    {"role": "user", "content": "u"},
                ],
            },
            "model_provider": "OPENAI",
            "model_name": "gpt-5",
        }
        result = phoenix_to_prompt(record, version)
        assert result.model == "openai:gpt-5"

    def test_round_trip_preserves_model(self):
        original = self._prompt(model="anthropic:claude-3-5-sonnet-latest")
        prompt_data, version_data = prompt_to_phoenix_payloads(original)
        record = {"name": prompt_data["name"], "metadata": prompt_data["metadata"]}
        roundtripped = phoenix_to_prompt(record, version_data)
        assert roundtripped.model == "anthropic:claude-3-5-sonnet-latest"

    def test_round_trip_gemini_normalises_back_to_google_gla(self):
        # User authors google-gla; goes to GEMINI on Phoenix; reads back as
        # google-gla (not google-vertex). This is intentional asymmetry.
        original = self._prompt(model="google-vertex:gemini-pro")
        prompt_data, version_data = prompt_to_phoenix_payloads(original)
        record = {"name": prompt_data["name"], "metadata": prompt_data["metadata"]}
        roundtripped = phoenix_to_prompt(record, version_data)
        assert roundtripped.model == "google-gla:gemini-pro"

    def test_missing_payload_model_falls_back_to_base(self):
        prompt_no_model = self._prompt(model=None)
        base = {"model_provider": "OPENAI", "model_name": "gpt-4o-mini"}
        _, version_data = prompt_to_phoenix_payloads(
            prompt_no_model, base_version=base,
        )
        assert version_data["model_provider"] == "OPENAI"
        assert version_data["model_name"] == "gpt-4o-mini"

    def test_missing_payload_model_and_no_base_uses_last_resort_default(self):
        prompt_no_model = self._prompt(model=None)
        _, version_data = prompt_to_phoenix_payloads(prompt_no_model)
        assert version_data["model_provider"] == "OPENAI"
        assert version_data["model_name"] == "gpt-4o-mini"
