"""Endpoint tests for /api/prompts — Phase D (Phoenix passthrough).

The routes now proxy Phoenix's REST API; these tests inject an
in-memory ``_FakePhoenixClient`` on the FastAPI app so we never touch
a live Phoenix instance.
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
    """Mirror of ``PhoenixPromptClient``'s public surface.

    Stores prompt records (name + metadata + description) and keeps an
    ordered list of versions per name so create/list/get_latest behave
    like the real backend.
    """

    def __init__(self) -> None:
        # name -> {"name", "metadata", "description"}
        self.records: Dict[str, Dict[str, Any]] = {}
        # name -> [version_dict, ...] with the last entry being latest
        self.versions: Dict[str, List[Dict[str, Any]]] = {}
        self.tags: List[tuple[str, str]] = []
        self._next_id = 0

    # ----- helpers used only by tests --------------------------------------

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
        record = {"name": name, "metadata": metadata}
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

    # ----- PhoenixPromptClient public surface ------------------------------

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
                **({"description": prompt["description"]} if "description" in prompt else {}),
            }
        # Phoenix only stores prompt-level metadata on first create;
        # mimic that exactly.
        new_v = self._make_version(version["template"]["messages"])
        # Carry over any extra version fields from the request so the
        # route's response shape matches what would come back live.
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
    """App + injected fake Phoenix client."""
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

    def test_lists_every_role_per_prompt(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts")
        assert resp.status_code == 200
        body = resp.json()
        # KEY_CLASSIFY -> 2 rows (system + user); KEY_EXTRACT -> 1 row.
        assert body["total"] == 3
        keys = {(item["prompt_key"], item["prompt_type"]) for item in body["items"]}
        assert keys == {
            (KEY_CLASSIFY, "system"),
            (KEY_CLASSIFY, "user"),
            (KEY_EXTRACT, "system"),
        }

    def test_category_filter(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"category": "logistics"})
        body = resp.json()
        assert body["total"] == 2
        assert {item["prompt_key"] for item in body["items"]} == {KEY_CLASSIFY}

    def test_step_name_filter(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"step_name": "classify"})
        body = resp.json()
        assert body["total"] == 2

    def test_prompt_type_filter(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"prompt_type": "system"})
        body = resp.json()
        assert body["total"] == 2
        assert all(item["prompt_type"] == "system" for item in body["items"])

    def test_is_active_false_returns_empty(self, seeded_client):
        # Phoenix has no soft-delete; ``is_active=false`` is meaningless
        # against a live backend, so the endpoint reports nothing.
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"is_active": "false"})
        body = resp.json()
        assert body["total"] == 0

    def test_required_variables_extracted_from_content(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"prompt_type": "system"})
        body = resp.json()
        classify = next(
            i for i in body["items"]
            if i["prompt_key"] == KEY_CLASSIFY
        )
        assert classify["required_variables"] == ["role", "input"]

    def test_pagination_limit(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"limit": 1})
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["total"] == 3

    def test_pagination_offset(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"offset": 1})
        body = resp.json()
        assert len(body["items"]) == 2

    def test_no_match_returns_empty(self, seeded_client):
        client, _ = seeded_client
        resp = client.get("/api/prompts", params={"category": "nonexistent"})
        body = resp.json()
        assert body["total"] == 0


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


class TestGetPrompt:
    def test_404_for_unknown_key(self, empty_client):
        resp = empty_client.get("/api/prompts/no_such_key")
        assert resp.status_code == 404

    def test_returns_grouped_variants(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(f"/api/prompts/{KEY_CLASSIFY}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["prompt_key"] == KEY_CLASSIFY
        assert len(body["variants"]) == 2
        types = {v["prompt_type"] for v in body["variants"]}
        assert types == {"system", "user"}

    def test_legacy_split_key_still_resolves(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(f"/api/prompts/{KEY_CLASSIFY}.system_instruction")
        assert resp.status_code == 200
        body = resp.json()
        # The bare name is what comes back, regardless of how the
        # caller spelled the key.
        assert body["prompt_key"] == KEY_CLASSIFY

    def test_single_variant_key(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(f"/api/prompts/{KEY_EXTRACT}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["variants"]) == 1


# ---------------------------------------------------------------------------
# Create / Update / Delete
# ---------------------------------------------------------------------------


class TestCreatePrompt:
    def test_creates_fresh_prompt(self, empty_client):
        resp = empty_client.post("/api/prompts", json={
            "prompt_key": "fresh_prompt",
            "prompt_type": "system",
            "content": "You are helpful.",
        })
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["prompt_key"] == "fresh_prompt"
        assert body["prompt_type"] == "system"
        assert body["content"] == "You are helpful."

    def test_extending_existing_prompt_with_new_role(self, seeded_client):
        client, _ = seeded_client
        # KEY_EXTRACT only has a system message; add a user message.
        resp = client.post("/api/prompts", json={
            "prompt_key": KEY_EXTRACT,
            "prompt_type": "user",
            "content": "Input: {data}",
        })
        assert resp.status_code == 201, resp.text
        # Detail should now show two variants.
        detail = client.get(f"/api/prompts/{KEY_EXTRACT}").json()
        assert {v["prompt_type"] for v in detail["variants"]} == {"system", "user"}

    def test_writes_variable_definitions_to_metadata(self, empty_client, fake_phoenix_app):
        _, fake = fake_phoenix_app
        resp = empty_client.post("/api/prompts", json={
            "prompt_key": "with_vars",
            "prompt_type": "system",
            "content": "Hi {name}.",
            "variable_definitions": {"name": {"type": "str", "description": "user name"}},
        })
        assert resp.status_code == 201, resp.text
        # Phoenix-side: metadata carries variable_definitions.
        record = fake.records["with_vars"]
        assert record["metadata"]["variable_definitions"] == {
            "name": {"type": "str", "description": "user name"}
        }

    def test_tags_new_version_production(self, empty_client, fake_phoenix_app):
        _, fake = fake_phoenix_app
        empty_client.post("/api/prompts", json={
            "prompt_key": "tagged_prompt",
            "prompt_type": "system",
            "content": "X",
        })
        assert fake.tags
        last_version_id, tag = fake.tags[-1]
        assert tag == "production"


class TestUpdatePrompt:
    def test_404_when_prompt_missing(self, empty_client):
        resp = empty_client.put(
            "/api/prompts/missing/system",
            json={"content": "new"},
        )
        assert resp.status_code == 404

    def test_replaces_role_content_and_keeps_other_role(self, seeded_client):
        client, _ = seeded_client
        resp = client.put(
            f"/api/prompts/{KEY_CLASSIFY}/system",
            json={"content": "NEW SYSTEM"},
        )
        assert resp.status_code == 200, resp.text
        # Detail: system updated, user untouched.
        detail = client.get(f"/api/prompts/{KEY_CLASSIFY}").json()
        sys_v = next(v for v in detail["variants"] if v["prompt_type"] == "system")
        usr_v = next(v for v in detail["variants"] if v["prompt_type"] == "user")
        assert sys_v["content"] == "NEW SYSTEM"
        assert usr_v["content"] == "Item: {item}"

    def test_legacy_split_key_routes_to_phoenix_name(self, seeded_client):
        client, _ = seeded_client
        # Frontend passing the legacy key still works: the route
        # strips the suffix and updates the right Phoenix prompt.
        resp = client.put(
            f"/api/prompts/{KEY_CLASSIFY}.system_instruction/system",
            json={"content": "LEGACY SAVE"},
        )
        assert resp.status_code == 200
        detail = client.get(f"/api/prompts/{KEY_CLASSIFY}").json()
        sys_v = next(v for v in detail["variants"] if v["prompt_type"] == "system")
        assert sys_v["content"] == "LEGACY SAVE"


class TestDeletePrompt:
    def test_deletes_whole_phoenix_prompt(self, seeded_client):
        client, fake = seeded_client
        resp = client.delete(f"/api/prompts/{KEY_CLASSIFY}/system")
        assert resp.status_code == 200
        assert KEY_CLASSIFY not in fake.records

    def test_404_when_prompt_missing(self, empty_client):
        resp = empty_client.delete("/api/prompts/missing/system")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Historical version + variables
# ---------------------------------------------------------------------------


class TestHistoricalPrompt:
    def test_resolves_phoenix_version_id(self, seeded_client):
        client, fake = seeded_client
        # Push a new version we can target by id.
        new_v = fake.create(
            prompt={"name": KEY_CLASSIFY, "metadata": {}},
            version={
                "model_provider": "OPENAI",
                "model_name": "gpt-4o-mini",
                "template": {
                    "type": "chat",
                    "messages": [
                        {"role": "system", "content": "FROZEN SYS"},
                        {"role": "user", "content": "FROZEN USR"},
                    ],
                },
                "template_type": "CHAT",
                "template_format": "F_STRING",
                "invocation_parameters": {"type": "openai", "openai": {}},
            },
        )
        resp = client.get(
            f"/api/prompts/{KEY_CLASSIFY}/system/versions/{new_v['id']}"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["content"] == "FROZEN SYS"
        assert body["is_latest"] is True

    def test_legacy_semver_falls_back_to_latest(self, seeded_client):
        client, _ = seeded_client
        resp = client.get(
            f"/api/prompts/{KEY_CLASSIFY}/system/versions/1.0"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["is_latest"] is True


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
            resp = client.get("/api/prompts/vars_demo/system/variables")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        names = [f["name"] for f in body["fields"]]
        assert "topic" in names
        topic = next(f for f in body["fields"] if f["name"] == "topic")
        assert topic["type"] == "str"
        assert topic["source"] == "db"
