"""Endpoint tests for /api/prompts (Phoenix passthrough).

The routes proxy Phoenix's REST API; these tests inject an in-memory
``_FakePhoenixClient`` so we never touch a live Phoenix instance.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest
from starlette.testclient import TestClient

from llm_pipeline.prompts.phoenix_client import PromptNotFoundError
from tests.ui.conftest import _make_app


KEY_CLASSIFY = "classify_shipment"
KEY_EXTRACT = "extract_fields"


# ---------------------------------------------------------------------------
# In-memory Phoenix client double
# ---------------------------------------------------------------------------


class _FakePhoenixClient:
    """Mirror of ``PhoenixPromptClient``'s public surface."""

    def __init__(self) -> None:
        self.records: Dict[str, Dict[str, Any]] = {}
        self.versions: Dict[str, List[Dict[str, Any]]] = {}
        self.tags: List[tuple[str, str]] = []
        self._next_id = 0

    def seed(
        self,
        name: str,
        *,
        system: Optional[str] = None,
        user: Optional[str] = None,
        category: Optional[str] = None,
        step_name: Optional[str] = None,
        variable_definitions: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> None:
        metadata: Dict[str, Any] = {"managed_by": "llm-pipeline"}
        if category is not None:
            metadata["category"] = category
        if step_name is not None:
            metadata["step_name"] = step_name
        if variable_definitions is not None:
            metadata["variable_definitions"] = variable_definitions
        record: Dict[str, Any] = {"name": name, "metadata": metadata}
        if description is not None:
            record["description"] = description
        self.records[name] = record

        messages: List[Dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        if user is not None:
            messages.append({"role": "user", "content": user})
        self.versions.setdefault(name, []).append(self._make_version(messages))

    def _make_version(
        self, messages: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        self._next_id += 1
        return {
            "id": f"v_{self._next_id:03d}",
            "model_provider": "OPENAI",
            "model_name": "gpt-4o-mini",
            "template": {"type": "chat", "messages": messages},
            "template_type": "CHAT",
            "template_format": "F_STRING",
            "invocation_parameters": {"type": "openai", "openai": {}},
        }

    def list_prompts(self, *, limit: int = 100, cursor: Optional[str] = None):
        del limit, cursor
        return {"data": list(self.records.values()), "next_cursor": None}

    def get_latest(self, name: str) -> Dict[str, Any]:
        if name not in self.versions or not self.versions[name]:
            raise PromptNotFoundError(name)
        return self.versions[name][-1]

    def get_by_tag(self, name: str, tag: str) -> Dict[str, Any]:
        del tag
        return self.get_latest(name)

    def get_version(self, version_id: str) -> Dict[str, Any]:
        for versions in self.versions.values():
            for v in versions:
                if v["id"] == version_id:
                    return v
        raise PromptNotFoundError(version_id)

    def create(self, *, prompt: Dict[str, Any], version: Dict[str, Any]):
        name = prompt["name"]
        if name not in self.records:
            self.records[name] = {
                "name": name,
                "metadata": prompt.get("metadata") or {},
                **(
                    {"description": prompt["description"]}
                    if "description" in prompt
                    else {}
                ),
            }
        # Phoenix only stores prompt-level metadata on first create.
        new_v = self._make_version(version["template"]["messages"])
        for k in ("description", "response_format", "tools"):
            if k in version:
                new_v[k] = version[k]
        self.versions.setdefault(name, []).append(new_v)
        return new_v

    def add_tag(self, version_id: str, tag_name: str, *, description=None):
        del description
        self.tags.append((version_id, tag_name))

    def delete(self, name: str) -> None:
        if name not in self.records:
            raise PromptNotFoundError(name)
        self.records.pop(name)
        self.versions.pop(name, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_phoenix_app():
    app = _make_app()
    fake = _FakePhoenixClient()
    app.state._phoenix_prompt_client = fake
    return app, fake


@pytest.fixture
def empty_client(fake_phoenix_app):
    app, _fake = fake_phoenix_app
    with TestClient(app) as client:
        yield client


@pytest.fixture
def seeded_client(fake_phoenix_app):
    app, fake = fake_phoenix_app
    fake.seed(
        KEY_CLASSIFY,
        system="You are {role}. Classify {input}.",
        user="Item: {item}",
        category="logistics",
        step_name="classify",
    )
    fake.seed(
        KEY_EXTRACT,
        system="Extract data.",
        category="extraction",
        step_name="extract",
    )
    with TestClient(app) as client:
        yield client, fake


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


class TestListPrompts:
    def test_empty_returns_200_empty(self, empty_client):
        resp = empty_client.get("/api/prompts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_one_row_per_prompt(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        names = {item["name"] for item in body["items"]}
        assert names == {KEY_CLASSIFY, KEY_EXTRACT}

    def test_classify_carries_both_messages(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts")
        body = resp.json()
        classify = next(p for p in body["items"] if p["name"] == KEY_CLASSIFY)
        roles = {m["role"] for m in classify["messages"]}
        assert roles == {"system", "user"}

    def test_category_filter(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"category": "logistics"})
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["name"] == KEY_CLASSIFY

    def test_step_name_filter(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"step_name": "classify"})
        body = resp.json()
        assert body["total"] == 1

    def test_pagination_limit(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"limit": 1})
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["total"] == 2

    def test_no_match_returns_empty(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"category": "nonexistent"})
        body = resp.json()
        assert body["total"] == 0


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


class TestGetPrompt:
    def test_404_for_unknown_name(self, empty_client):
        resp = empty_client.get("/api/prompts/no_such_prompt")
        assert resp.status_code == 404

    def test_returns_messages_array(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(f"/api/prompts/{KEY_CLASSIFY}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == KEY_CLASSIFY
        assert len(body["messages"]) == 2
        roles = {m["role"] for m in body["messages"]}
        assert roles == {"system", "user"}

    def test_metadata_surfaced(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(f"/api/prompts/{KEY_CLASSIFY}")
        body = resp.json()
        assert body["metadata"]["category"] == "logistics"
        assert body["metadata"]["step_name"] == "classify"

    def test_single_message_prompt(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(f"/api/prompts/{KEY_EXTRACT}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "system"


# ---------------------------------------------------------------------------
# Create / Update / Delete
# ---------------------------------------------------------------------------


class TestCreatePrompt:
    def test_creates_fresh_prompt_with_both_messages(self, empty_client):
        resp = empty_client.post(
            "/api/prompts",
            json={
                "name": "fresh_prompt",
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Q: {q}"},
                ],
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "fresh_prompt"
        assert len(body["messages"]) == 2

    def test_writes_variable_definitions_to_metadata(
        self, empty_client, fake_phoenix_app,
    ):
        _, fake = fake_phoenix_app
        resp = empty_client.post(
            "/api/prompts",
            json={
                "name": "with_vars",
                "messages": [
                    {"role": "system", "content": "Hi {name}."},
                ],
                "metadata": {
                    "variable_definitions": {
                        "name": {"type": "str", "description": "user name"},
                    },
                },
            },
        )
        assert resp.status_code == 201, resp.text
        record = fake.records["with_vars"]
        assert record["metadata"]["variable_definitions"] == {
            "name": {"type": "str", "description": "user name"},
        }

    def test_tags_new_version_production(self, empty_client, fake_phoenix_app):
        _, fake = fake_phoenix_app
        empty_client.post(
            "/api/prompts",
            json={
                "name": "tagged_prompt",
                "messages": [{"role": "system", "content": "X"}],
            },
        )
        assert fake.tags
        _, tag = fake.tags[-1]
        assert tag == "production"


class TestUpdatePrompt:
    def test_404_when_prompt_missing(self, empty_client):
        resp = empty_client.put(
            "/api/prompts/missing",
            json={
                "name": "missing",
                "messages": [{"role": "system", "content": "x"}],
            },
        )
        assert resp.status_code == 404

    def test_replaces_messages_array_atomically(self, seeded_client):
        client, _ = seeded_client
        resp = client.put(
            f"/api/prompts/{KEY_CLASSIFY}",
            json={
                "name": KEY_CLASSIFY,
                "messages": [
                    {"role": "system", "content": "NEW SYSTEM"},
                    {"role": "user", "content": "NEW USER"},
                ],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        contents = {m["role"]: m["content"] for m in body["messages"]}
        assert contents == {"system": "NEW SYSTEM", "user": "NEW USER"}


class TestDeletePrompt:
    def test_deletes_whole_phoenix_prompt(self, seeded_client):
        client, fake = seeded_client
        resp = client.delete(f"/api/prompts/{KEY_CLASSIFY}")
        assert resp.status_code == 204
        assert KEY_CLASSIFY not in fake.records

    def test_404_when_prompt_missing(self, empty_client):
        resp = empty_client.delete("/api/prompts/missing")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Variables
# ---------------------------------------------------------------------------


class TestPromptVariables:
    def test_returns_metadata_variable_definitions(self, fake_phoenix_app):
        app, fake = fake_phoenix_app
        fake.seed(
            "vars_demo",
            system="Hi {topic}.",
            variable_definitions={
                "topic": {"type": "str", "description": "what to talk about"},
            },
        )
        with TestClient(app) as client:
            resp = client.get("/api/prompts/vars_demo/variables")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        names = [f["name"] for f in body["fields"]]
        assert "topic" in names
        topic = next(f for f in body["fields"] if f["name"] == "topic")
        assert topic["type"] == "str"
        assert topic["source"] == "db"
