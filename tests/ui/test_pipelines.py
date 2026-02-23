"""Endpoint tests for /api/pipelines routes."""
import pytest
from unittest.mock import patch
from starlette.testclient import TestClient

from tests.ui.conftest import _make_app
from llm_pipeline.introspection import PipelineIntrospector
from tests.test_introspection import (
    WidgetPipeline,
    ScanPipeline,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_introspector_cache():
    """Clear PipelineIntrospector._cache before and after each test."""
    PipelineIntrospector._cache.clear()
    yield
    PipelineIntrospector._cache.clear()


@pytest.fixture
def introspection_client(pipeline_cls_map):
    app = _make_app()
    app.state.introspection_registry = pipeline_cls_map
    with TestClient(app) as client:
        yield client


@pytest.fixture
def empty_introspection_client():
    app = _make_app()
    app.state.introspection_registry = {}
    with TestClient(app) as client:
        yield client


@pytest.fixture
def populated_introspection_client():
    app = _make_app()
    app.state.introspection_registry = {
        "widget": WidgetPipeline,
        "scan": ScanPipeline,
    }
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# Tests: GET /api/pipelines
# ---------------------------------------------------------------------------

class TestListPipelines:
    def test_list_empty_registry_returns_200_empty_list(self, empty_introspection_client):
        resp = empty_introspection_client.get("/api/pipelines")
        assert resp.status_code == 200
        body = resp.json()
        assert body == {"pipelines": []}

    def test_list_populated_returns_all_pipelines_alphabetically(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines")
        assert resp.status_code == 200
        body = resp.json()
        names = [p["name"] for p in body["pipelines"]]
        assert names == sorted(names)
        assert len(names) == 2

    def test_list_all_count_fields_non_null_for_valid_pipeline(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines")
        body = resp.json()
        for item in body["pipelines"]:
            assert item["strategy_count"] is not None
            assert item["step_count"] is not None
            assert item["registry_model_count"] is not None

    def test_list_item_has_expected_fields(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines")
        body = resp.json()
        expected_keys = {"name", "strategy_count", "step_count",
                         "has_input_schema", "registry_model_count", "error"}
        for item in body["pipelines"]:
            assert expected_keys.issubset(item.keys())

    def test_list_no_error_flag_for_valid_pipelines(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines")
        body = resp.json()
        for item in body["pipelines"]:
            assert item["error"] is None

    def test_list_errored_pipeline_included_with_error_flag(self):
        """Pipeline whose introspection raises appears in list with error != null, counts null."""
        app = _make_app()
        app.state.introspection_registry = {"exploding": WidgetPipeline}

        orig_get_metadata = PipelineIntrospector.get_metadata

        def _raise_once(self):
            if self._pipeline_cls is WidgetPipeline:
                raise RuntimeError("forced introspection failure")
            return orig_get_metadata(self)

        with patch.object(PipelineIntrospector, "get_metadata", _raise_once):
            with TestClient(app) as client:
                resp = client.get("/api/pipelines")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["pipelines"]) == 1
        item = body["pipelines"][0]
        assert item["name"] == "exploding"
        assert item["error"] is not None
        assert "forced introspection failure" in item["error"]
        assert item["strategy_count"] is None
        assert item["step_count"] is None
        assert item["registry_model_count"] is None

    def test_list_mixed_valid_and_errored_pipelines(self):
        """Valid pipelines appear correctly even when another pipeline errors."""
        app = _make_app()
        app.state.introspection_registry = {
            "scan": ScanPipeline,
            "exploding": WidgetPipeline,
        }

        orig_get_metadata = PipelineIntrospector.get_metadata

        def _raise_for_widget(self):
            if self._pipeline_cls is WidgetPipeline:
                raise RuntimeError("boom")
            return orig_get_metadata(self)

        with patch.object(PipelineIntrospector, "get_metadata", _raise_for_widget):
            with TestClient(app) as client:
                resp = client.get("/api/pipelines")

        assert resp.status_code == 200
        body = resp.json()
        assert len(body["pipelines"]) == 2

        names = [p["name"] for p in body["pipelines"]]
        assert names == sorted(names)

        scan_item = next(p for p in body["pipelines"] if p["name"] == "scan")
        assert scan_item["error"] is None
        assert scan_item["strategy_count"] is not None

        exploding_item = next(p for p in body["pipelines"] if p["name"] == "exploding")
        assert exploding_item["error"] is not None

    def test_list_no_introspection_registry_returns_empty(self):
        """app.state without introspection_registry attribute returns empty list."""
        app = _make_app()
        # Do not set introspection_registry -- it defaults to {} via getattr fallback
        with TestClient(app) as client:
            resp = client.get("/api/pipelines")
        assert resp.status_code == 200
        assert resp.json() == {"pipelines": []}

    def test_list_has_input_schema_true_for_pipeline_with_instructions(self, populated_introspection_client):
        """WidgetPipeline and ScanPipeline both have instructions classes, so has_input_schema=True."""
        resp = populated_introspection_client.get("/api/pipelines")
        body = resp.json()
        for item in body["pipelines"]:
            assert item["has_input_schema"] is True


# ---------------------------------------------------------------------------
# Tests: GET /api/pipelines/{name}
# ---------------------------------------------------------------------------

class TestGetPipeline:
    def test_detail_unknown_name_returns_404(self, empty_introspection_client):
        resp = empty_introspection_client.get("/api/pipelines/no_such_pipeline")
        assert resp.status_code == 404

    def test_detail_404_detail_message_contains_name(self, empty_introspection_client):
        resp = empty_introspection_client.get("/api/pipelines/missing")
        body = resp.json()
        assert "missing" in body["detail"]

    def test_detail_known_pipeline_returns_200(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines/widget")
        assert resp.status_code == 200

    def test_detail_known_pipeline_returns_metadata(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines/widget")
        body = resp.json()
        for key in ("pipeline_name", "strategies", "execution_order", "registry_models"):
            assert key in body, f"missing key: {key}"

    def test_detail_pipeline_name_matches_introspector(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines/widget")
        body = resp.json()
        expected = PipelineIntrospector(WidgetPipeline).get_metadata()["pipeline_name"]
        assert body["pipeline_name"] == expected

    def test_detail_response_shape_matches_introspector_output(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines/scan")
        body = resp.json()

        expected = PipelineIntrospector(ScanPipeline).get_metadata()

        assert body["pipeline_name"] == expected["pipeline_name"]
        assert len(body["strategies"]) == len(expected["strategies"])
        assert body["execution_order"] == expected["execution_order"]
        assert body["registry_models"] == expected["registry_models"]

    def test_detail_strategies_list_non_empty(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines/widget")
        body = resp.json()
        assert len(body["strategies"]) > 0

    def test_detail_strategy_has_required_fields(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines/widget")
        body = resp.json()
        strategy = body["strategies"][0]
        for key in ("name", "display_name", "class_name", "steps"):
            assert key in strategy, f"strategy missing key: {key}"

    def test_detail_execution_order_is_list_of_strings(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines/scan")
        body = resp.json()
        assert isinstance(body["execution_order"], list)
        for item in body["execution_order"]:
            assert isinstance(item, str)

    def test_detail_registry_models_is_list(self, populated_introspection_client):
        resp = populated_introspection_client.get("/api/pipelines/scan")
        body = resp.json()
        assert isinstance(body["registry_models"], list)
