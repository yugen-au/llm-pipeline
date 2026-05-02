"""Tests for the Phoenix schema-sync at step registration."""
from __future__ import annotations

from typing import Any, ClassVar, Dict, List
from unittest.mock import MagicMock

import pytest
from pydantic import BaseModel

from llm_pipeline.prompts.phoenix_client import (
    PhoenixPromptClient,
    PromptNotFoundError,
)
from llm_pipeline.prompts.registration import (
    _callable_to_phoenix,
    _compose_updated_version,
    derive_response_format,
    derive_tools,
    _equivalent,
    sync_step_to_phoenix,
)


# ---------------------------------------------------------------------------
# Fixtures: a minimal step-class double
# ---------------------------------------------------------------------------


class WidgetInstructions(BaseModel):
    """Output schema for the widget step."""
    count: int
    label: str


class WidgetInputs(BaseModel):
    data: str
    threshold: int = 0


def _step_double(*, instructions=None, inputs=None, agent=None, default_tools=None):
    cls = type(
        "WidgetDetectionStep",
        (),
        {
            "INSTRUCTIONS": instructions,
            "INPUTS": inputs,
            "AGENT": agent,
            "DEFAULT_TOOLS": default_tools or [],
        },
    )
    return cls


# ---------------------------------------------------------------------------
# Schema derivation
# ---------------------------------------------------------------------------


class TestDeriveResponseFormat:
    def test_returns_phoenix_json_schema_payload(self):
        rf = derive_response_format(WidgetInstructions)
        assert rf is not None
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == "WidgetInstructions"
        assert rf["json_schema"]["schema"]["properties"]["count"]["type"] == "integer"
        assert rf["json_schema"]["description"] == "Output schema for the widget step."

    def test_returns_none_for_missing_instructions(self):
        assert derive_response_format(None) is None


class TestDeriveTools:
    def test_returns_none_when_no_tools_configured(self):
        step = _step_double(instructions=WidgetInstructions, inputs=WidgetInputs)
        assert derive_tools(step) is None

    def test_agent_tool_subclass_uses_args_schema(self):
        from llm_pipeline.agent_tool import AgentTool
        from llm_pipeline.inputs import StepInputs

        class FetchDocsTool(AgentTool):
            """Look up framework docs."""

            class Inputs(StepInputs):
                session_token: str = ""

            class Args(BaseModel):
                query: str
                limit: int = 5

            @classmethod
            def run(cls, inputs, args, ctx):
                return {}

        step = _step_double(
            instructions=WidgetInstructions, inputs=WidgetInputs,
            default_tools=[FetchDocsTool],
        )
        tools = derive_tools(step)
        assert tools is not None
        assert tools["type"] == "tools"
        assert len(tools["tools"]) == 1
        entry = tools["tools"][0]
        assert entry["type"] == "function"
        assert entry["function"]["name"] == "fetch_docs_tool"
        assert "Look up framework docs." in entry["function"]["description"]
        assert (
            entry["function"]["parameters"]["properties"]["query"]["type"] == "string"
        )
        assert (
            entry["function"]["parameters"]["properties"]["limit"]["default"] == 5
        )

    def test_legacy_register_agent_callables_get_inferred_schema(self, monkeypatch):
        async def search_docs(query: str, limit: int = 10) -> str:
            """Search the docs index."""
            return ""

        # Stub the registry lookup so we don't pollute the global.
        monkeypatch.setattr(
            "llm_pipeline.agent_registry.get_agent_tools",
            lambda name: [search_docs] if name == "code_gen" else [],
        )

        step = _step_double(
            instructions=WidgetInstructions, inputs=WidgetInputs, agent="code_gen",
        )
        tools = derive_tools(step)
        assert tools is not None
        entry = tools["tools"][0]
        assert entry["function"]["name"] == "search_docs"
        params = entry["function"]["parameters"]
        assert params["properties"]["query"]["type"] == "string"
        assert params["properties"]["limit"]["default"] == 10

    def test_callable_without_annotations_falls_back_to_string(self):
        def loose(thing, count=1):  # no annotations
            """."""
            return None

        entry = _callable_to_phoenix(loose)
        params = entry["function"]["parameters"]
        # ``thing`` -> defaulted to str; ``count`` -> int from default.
        assert params["properties"]["thing"]["type"] == "string"


# ---------------------------------------------------------------------------
# Payload composition + equivalence
# ---------------------------------------------------------------------------


class TestComposeUpdatedVersion:
    def test_preserves_template_and_invocation_params(self):
        existing = {
            "id": "v_old",
            "model_provider": "OPENAI",
            "model_name": "gpt-4o-mini",
            "template": {"type": "chat", "messages": [{"role": "user", "content": "Hi"}]},
            "template_type": "CHAT",
            "template_format": "F_STRING",
            "invocation_parameters": {"type": "openai", "openai": {}},
            "tools": None,
            "response_format": None,
        }
        rf = {"type": "json_schema", "json_schema": {"name": "X", "schema": {}}}
        new = _compose_updated_version(existing, response_format=rf, tools=None)
        # Existing model + template are passed through unchanged.
        assert new["model_name"] == "gpt-4o-mini"
        assert new["template"] == existing["template"]
        # New schema is slotted in.
        assert new["response_format"] == rf
        # ``id`` is not carried over to the new version payload.
        assert "id" not in new


class TestEquivalent:
    def test_equal_when_response_format_and_tools_match(self):
        existing = {"response_format": {"x": 1}, "tools": None}
        proposed = {"response_format": {"x": 1}, "tools": None}
        assert _equivalent(existing, proposed)

    def test_unequal_when_response_format_differs(self):
        assert not _equivalent(
            {"response_format": {"x": 1}, "tools": None},
            {"response_format": {"x": 2}, "tools": None},
        )


# ---------------------------------------------------------------------------
# sync_step_to_phoenix end-to-end (against a fake client)
# ---------------------------------------------------------------------------


class _FakeClient:
    def __init__(self, latest=None, raise_not_found=False):
        self.latest = latest
        self.raise_not_found = raise_not_found
        self.created_payloads: List[Dict[str, Any]] = []
        self.tags_added: List[tuple[str, str]] = []

    def get_latest(self, name):
        if self.raise_not_found:
            raise PromptNotFoundError(name)
        return self.latest

    def create(self, *, prompt, version):
        self.created_payloads.append({"prompt": prompt, "version": version})
        return {"id": "v_new", **version}

    def add_tag(self, version_id, tag, *, description=None):
        self.tags_added.append((version_id, tag))


class TestSyncStepToPhoenix:
    def setup_method(self):
        self.step_cls = _step_double(
            instructions=WidgetInstructions, inputs=WidgetInputs,
        )

    def test_missing_prompt_returns_missing_without_writing(self):
        client = _FakeClient(raise_not_found=True)
        outcome = sync_step_to_phoenix(
            self.step_cls, prompt_name="widget_detection", client=client,
        )
        assert outcome == "missing"
        assert client.created_payloads == []

    def test_no_change_returns_skipped(self):
        # Existing already carries the same response_format we'd derive.
        rf = derive_response_format(WidgetInstructions)
        existing = {
            "id": "v_old",
            "model_provider": "OPENAI",
            "model_name": "gpt-4o-mini",
            "template": {"type": "chat", "messages": []},
            "template_type": "CHAT",
            "template_format": "F_STRING",
            "invocation_parameters": {"type": "openai", "openai": {}},
            "response_format": rf,
            "tools": None,
        }
        client = _FakeClient(latest=existing)
        outcome = sync_step_to_phoenix(
            self.step_cls, prompt_name="widget_detection", client=client,
        )
        assert outcome == "skipped"
        assert client.created_payloads == []

    def test_drift_triggers_create_and_tag(self):
        existing = {
            "id": "v_old",
            "model_provider": "OPENAI",
            "model_name": "gpt-4o-mini",
            "template": {"type": "chat", "messages": []},
            "template_type": "CHAT",
            "template_format": "F_STRING",
            "invocation_parameters": {"type": "openai", "openai": {}},
            "response_format": None,  # drift: code says we now have a JSON schema
            "tools": None,
        }
        client = _FakeClient(latest=existing)
        outcome = sync_step_to_phoenix(
            self.step_cls, prompt_name="widget_detection", client=client,
        )
        assert outcome == "updated"
        assert len(client.created_payloads) == 1
        payload = client.created_payloads[0]
        assert payload["prompt"] == {"name": "widget_detection"}
        assert payload["version"]["response_format"]["type"] == "json_schema"
        # Tag attached to the new version.
        assert client.tags_added == [("v_new", "production")]
