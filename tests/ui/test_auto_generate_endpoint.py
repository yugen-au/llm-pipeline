"""Tests for GET /api/auto-generate endpoint."""
import enum
import pytest
from starlette.testclient import TestClient

from tests.ui.conftest import _make_app
from llm_pipeline.prompts.variables import (
    register_auto_generate,
    clear_auto_generate_registry,
)


class Color(enum.Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"


@pytest.fixture(autouse=True)
def _clean():
    yield
    clear_auto_generate_registry()


@pytest.fixture
def client():
    app = _make_app()
    return TestClient(app)


class TestAutoGenerateEndpoint:
    def test_empty_registry(self, client):
        resp = client.get("/api/auto-generate")
        assert resp.status_code == 200
        assert resp.json() == {"objects": []}

    def test_enum_object(self, client):
        register_auto_generate("Color", Color)
        resp = client.get("/api/auto-generate")
        data = resp.json()
        assert len(data["objects"]) == 1
        obj = data["objects"][0]
        assert obj["name"] == "Color"
        assert obj["kind"] == "enum"
        assert obj["members"] == [
            {"name": "RED", "value": "red"},
            {"name": "GREEN", "value": "green"},
            {"name": "BLUE", "value": "blue"},
        ]

    def test_constant_int(self, client):
        register_auto_generate("MAX_RETRIES", 3)
        resp = client.get("/api/auto-generate")
        obj = resp.json()["objects"][0]
        assert obj["name"] == "MAX_RETRIES"
        assert obj["kind"] == "constant"
        assert obj["value_type"] == "int"
        assert obj["value"] == 3

    def test_constant_str(self, client):
        register_auto_generate("SEPARATOR", "|")
        resp = client.get("/api/auto-generate")
        obj = resp.json()["objects"][0]
        assert obj["kind"] == "constant"
        assert obj["value_type"] == "str"

    def test_mixed_objects(self, client):
        register_auto_generate("Color", Color)
        register_auto_generate("MAX", 10)
        register_auto_generate("SEP", "|")
        resp = client.get("/api/auto-generate")
        objects = resp.json()["objects"]
        assert len(objects) == 3
        names = {o["name"] for o in objects}
        assert names == {"Color", "MAX", "SEP"}
