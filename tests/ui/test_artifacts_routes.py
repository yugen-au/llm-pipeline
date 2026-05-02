"""Tests for the generic per-kind artifact routes (Phase D.1).

Boots a real ``create_app`` against the demo convention dir so
the per-kind walkers populate ``app.state.registries`` naturally,
then exercises the routes end-to-end via Starlette's
``TestClient``.

``create_app(demo_mode=True)`` triggers convention discovery
which populates several module-level registries
(``_AUTO_GENERATE_REGISTRY``, ``_PROMPT_VARIABLES_REGISTRY``).
These leak across tests; the autouse cleanup fixture clears
them after each test in this module so the global-state-empty
expectations in other UI test modules aren't violated.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from llm_pipeline.prompts.variables import (
    clear_auto_generate_registry,
    clear_prompt_variables_registry,
)
from llm_pipeline.ui.app import create_app


@pytest.fixture(autouse=True)
def _cleanup_global_registries():
    """Clear discovery-populated globals after each test."""
    yield
    clear_auto_generate_registry()
    clear_prompt_variables_registry()


def _client() -> TestClient:
    app = create_app(db_path=":memory:", demo_mode=True)
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/artifacts/{kind}
# ---------------------------------------------------------------------------


class TestList:
    def test_list_steps_returns_demo_steps(self):
        c = _client()
        r = c.get("/api/artifacts/step")
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "step"
        names = [a["name"] for a in body["artifacts"]]
        assert names == ["sentiment_analysis", "summary", "topic_extraction"]
        assert body["count"] == len(names)

    def test_list_kind_with_no_artifacts_returns_empty(self):
        c = _client()
        # Demo pipeline has no review nodes → registry stays empty.
        r = c.get("/api/artifacts/review")
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "review"
        assert body["count"] == 0
        assert body["artifacts"] == []

    def test_list_unknown_kind_404(self):
        c = _client()
        r = c.get("/api/artifacts/bogus")
        assert r.status_code == 404
        assert "bogus" in r.json()["detail"]

    def test_list_item_carries_validation_summary(self):
        c = _client()
        r = c.get("/api/artifacts/step")
        assert r.status_code == 200
        for item in r.json()["artifacts"]:
            assert "issue_count" in item
            assert "has_errors" in item
            assert isinstance(item["issue_count"], int)
            assert isinstance(item["has_errors"], bool)
            # Demo is clean → no error-severity issues.
            assert item["has_errors"] is False

    def test_list_table_kind(self):
        c = _client()
        r = c.get("/api/artifacts/table")
        assert r.status_code == 200
        body = r.json()
        names = [a["name"] for a in body["artifacts"]]
        assert "topic" in names

    def test_list_schema_kind_only_truly_shared(self):
        # Per-step INPUTS/INSTRUCTIONS now live with their step;
        # only TopicItem (used by both the step's instructions
        # AND the extraction's pathway inputs) is registered as
        # a schema.
        c = _client()
        r = c.get("/api/artifacts/schema")
        assert r.status_code == 200
        names = [a["name"] for a in r.json()["artifacts"]]
        assert "topic_item" in names
        # Step-local classes are NOT here.
        assert "sentiment_analysis_inputs" not in names
        assert "summary_instructions" not in names


# ---------------------------------------------------------------------------
# GET /api/artifacts/{kind}/{name}
# ---------------------------------------------------------------------------


class TestDetail:
    def test_step_detail_payload(self):
        c = _client()
        r = c.get("/api/artifacts/step/sentiment_analysis")
        assert r.status_code == 200
        spec = r.json()
        assert spec["kind"] == "step"
        assert spec["name"] == "sentiment_analysis"
        # Per-kind subclass fields present.
        assert "inputs" in spec
        assert "instructions" in spec
        assert "prepare" in spec
        assert "run" in spec
        # Inputs schema has the demo's expected ``text`` field.
        assert "text" in spec["inputs"]["json_schema"]["properties"]
        # Body source captured.
        assert spec["prepare"] is not None
        assert "SentimentAnalysisPrompt" in spec["prepare"]["source"]

    def test_table_detail_payload(self):
        c = _client()
        r = c.get("/api/artifacts/table/topic")
        assert r.status_code == 200
        spec = r.json()
        assert spec["kind"] == "table"
        assert spec["table_name"] == "demo_topics"
        # JSON schema for the SQLModel.
        assert "properties" in spec["definition"]["json_schema"]

    def test_extraction_detail_payload(self):
        c = _client()
        r = c.get("/api/artifacts/extraction/topic")
        assert r.status_code == 200
        spec = r.json()
        assert spec["kind"] == "extraction"
        # ``table`` is an ArtifactRef carrying the source-side
        # class name (``Topic``) plus a resolved ref pointing at
        # the registered table.
        assert spec["table"] is not None
        assert spec["table"]["name"] == "Topic"
        assert spec["table"]["ref"] is not None
        assert spec["table"]["ref"]["kind"] == "table"
        assert spec["table"]["ref"]["name"] == "topic"
        # extract body captured.
        assert spec["extract"] is not None
        assert "Topic" in spec["extract"]["source"]

    def test_enum_detail_payload(self):
        c = _client()
        r = c.get("/api/artifacts/enum/sentiment")
        assert r.status_code == 200
        spec = r.json()
        assert spec["kind"] == "enum"
        member_names = [m["name"] for m in spec["members"]]
        assert len(member_names) > 0

    def test_detail_unknown_kind_404(self):
        c = _client()
        r = c.get("/api/artifacts/bogus/foo")
        assert r.status_code == 404

    def test_detail_unknown_name_404(self):
        c = _client()
        r = c.get("/api/artifacts/step/missing")
        assert r.status_code == 404
        assert "missing" in r.json()["detail"]

    def test_detail_round_trips_through_pydantic(self):
        # The detail response is the full spec dump; validate it
        # round-trips through the relevant ``ArtifactSpec``
        # subclass — this catches any field that lost its shape
        # crossing the JSON boundary.
        from llm_pipeline.artifacts import StepSpec

        c = _client()
        r = c.get("/api/artifacts/step/sentiment_analysis")
        re_spec = StepSpec.model_validate(r.json())
        assert re_spec.name == "sentiment_analysis"
