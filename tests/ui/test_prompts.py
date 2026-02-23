"""Endpoint tests for /api/prompts routes."""
import pytest
from sqlmodel import Session
from starlette.testclient import TestClient

from tests.ui.conftest import _make_app
from llm_pipeline.db.prompt import Prompt


KEY_CLASSIFY = "classify_shipment"
KEY_EXTRACT = "extract_fields"


@pytest.fixture
def seeded_prompts_client():
    app = _make_app()
    engine = app.state.engine

    with Session(engine) as session:
        session.add(Prompt(
            prompt_key=KEY_CLASSIFY,
            prompt_type="system",
            category="logistics",
            step_name="classify",
            content="You are {role}. Classify {input}.",
            required_variables=["role", "input"],
            is_active=True,
            prompt_name="Classify System",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key=KEY_CLASSIFY,
            prompt_type="user",
            category="logistics",
            step_name="classify",
            content="Item: {item}",
            required_variables=["item"],
            is_active=True,
            prompt_name="Classify User",
            version="1.0",
        ))
        session.add(Prompt(
            prompt_key=KEY_EXTRACT,
            prompt_type="system",
            category="extraction",
            step_name="extract",
            content="Extract data.",
            required_variables=None,
            is_active=False,
            prompt_name="Extract System",
            version="2.0",
        ))
        session.commit()

    with TestClient(app) as client:
        yield client


class TestListPrompts:
    def test_empty_db_returns_200_empty(self, app_client):
        resp = app_client.get("/api/prompts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_returns_active_by_default(self, seeded_prompts_client):
        resp = seeded_prompts_client.get("/api/prompts")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert all(item["is_active"] is True for item in body["items"])

    def test_category_filter(self, seeded_prompts_client):
        resp = seeded_prompts_client.get("/api/prompts", params={"category": "logistics"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert all(item["category"] == "logistics" for item in body["items"])

    def test_step_name_filter(self, seeded_prompts_client):
        resp = seeded_prompts_client.get("/api/prompts", params={"step_name": "classify"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2

    def test_prompt_type_filter(self, seeded_prompts_client):
        # KEY_CLASSIFY system is active; KEY_EXTRACT system is inactive (excluded by default is_active=True)
        resp = seeded_prompts_client.get("/api/prompts", params={"prompt_type": "system"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["prompt_type"] == "system"

    def test_is_active_false_returns_inactive(self, seeded_prompts_client):
        resp = seeded_prompts_client.get("/api/prompts", params={"is_active": "false"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 1
        assert body["items"][0]["prompt_key"] == KEY_EXTRACT

    def test_required_variables_fallback(self, seeded_prompts_client):
        # KEY_EXTRACT has required_variables=None; "Extract data." has no {var} patterns
        resp = seeded_prompts_client.get("/api/prompts", params={"is_active": "false"})
        body = resp.json()
        assert body["items"][0]["required_variables"] == []

    def test_pagination_limit(self, seeded_prompts_client):
        resp = seeded_prompts_client.get("/api/prompts", params={"limit": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1
        assert body["total"] == 2

    def test_pagination_offset(self, seeded_prompts_client):
        resp = seeded_prompts_client.get("/api/prompts", params={"offset": 1})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["items"]) == 1

    def test_combined_category_step_filter(self, seeded_prompts_client):
        resp = seeded_prompts_client.get(
            "/api/prompts", params={"category": "logistics", "step_name": "classify"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2

    def test_no_match_returns_empty(self, seeded_prompts_client):
        resp = seeded_prompts_client.get("/api/prompts", params={"category": "nonexistent"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 0
        assert body["items"] == []


class TestGetPrompt:
    def test_404_for_unknown_key(self, app_client):
        resp = app_client.get("/api/prompts/no_such_key")
        assert resp.status_code == 404

    def test_returns_grouped_variants(self, seeded_prompts_client):
        resp = seeded_prompts_client.get(f"/api/prompts/{KEY_CLASSIFY}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["prompt_key"] == KEY_CLASSIFY
        assert len(body["variants"]) == 2

    def test_variants_contain_prompt_type_field(self, seeded_prompts_client):
        resp = seeded_prompts_client.get(f"/api/prompts/{KEY_CLASSIFY}")
        body = resp.json()
        prompt_types = {v["prompt_type"] for v in body["variants"]}
        assert prompt_types == {"system", "user"}

    def test_single_variant_key(self, seeded_prompts_client):
        # KEY_EXTRACT has one row (inactive); detail endpoint ignores is_active
        resp = seeded_prompts_client.get(f"/api/prompts/{KEY_EXTRACT}")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["variants"]) == 1

    def test_required_variables_populated(self, seeded_prompts_client):
        resp = seeded_prompts_client.get(f"/api/prompts/{KEY_CLASSIFY}")
        body = resp.json()
        system_variant = next(v for v in body["variants"] if v["prompt_type"] == "system")
        assert system_variant["required_variables"] == ["role", "input"]

    def test_required_variables_fallback_in_detail(self, seeded_prompts_client):
        # KEY_EXTRACT has required_variables=None; "Extract data." has no {var} patterns
        resp = seeded_prompts_client.get(f"/api/prompts/{KEY_EXTRACT}")
        body = resp.json()
        assert body["variants"][0]["required_variables"] == []
