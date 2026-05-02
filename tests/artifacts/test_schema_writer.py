"""Tests for :class:`SchemaWriter` — write / edit / apply."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from llm_pipeline.artifacts.base.blocks import JsonSchemaWithRefs
from llm_pipeline.artifacts.schemas import SchemaSpec, SchemaWriter


def _spec(
    *,
    properties: dict,
    required: list[str] | None = None,
    field_source: dict[str, str] | None = None,
    name: str = "TopicItem",
    description: str = "",
) -> SchemaSpec:
    return SchemaSpec(
        name=name.lower(),
        cls=f"llm_pipelines.schemas.topic.{name}",
        source_path="/tmp/topic.py",
        description=description,
        definition=JsonSchemaWithRefs(
            json_schema={
                "properties": properties,
                "required": required or [],
            },
            field_source=field_source or {},
            description=description,
        ),
    )


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------


class TestWrite:
    def test_basic_class(self):
        spec = _spec(
            properties={
                "name": {"type": "string"},
                "count": {"type": "integer", "default": 0},
            },
            required=["name"],
            field_source={"name": "str", "count": "int"},
        )
        result = SchemaWriter(spec=spec).write()
        assert "from pydantic import BaseModel" in result
        assert "class TopicItem(BaseModel):" in result
        assert "name: str" in result
        assert "count: int = 0" in result

    def test_uses_field_source_for_round_trip(self):
        # field_source preserves user syntax over the JSON-schema fallback.
        spec = _spec(
            properties={
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            field_source={"tags": "list[str]"},
        )
        result = SchemaWriter(spec=spec).write()
        assert "tags: list[str]" in result

    def test_falls_back_to_schema_when_no_field_source(self):
        spec = _spec(
            properties={"flag": {"type": "boolean", "default": False}},
            field_source={},  # no round-trip data
        )
        result = SchemaWriter(spec=spec).write()
        # schema_to_annotation derives ``bool`` from ``{"type": "boolean"}``.
        assert "flag: bool" in result

    def test_includes_class_docstring(self):
        spec = _spec(
            properties={"x": {"type": "string"}},
            required=["x"],
            field_source={"x": "str"},
            description="A demo class.",
        )
        result = SchemaWriter(spec=spec).write()
        assert '"""A demo class."""' in result


# ---------------------------------------------------------------------------
# edit()
# ---------------------------------------------------------------------------


class TestEdit:
    def test_replaces_target_class(self):
        existing = textwrap.dedent('''\
            """Topic module."""
            from pydantic import BaseModel


            class TopicItem(BaseModel):
                """Old docstring."""
                name: str
                confidence: float = 0.0


            class Other(BaseModel):
                a: int = 1
        ''')
        spec = _spec(
            properties={
                "name": {"type": "string"},
                "confidence": {"type": "number", "default": 0.0},
                "tags": {"type": "array", "items": {"type": "string"}, "default": []},
            },
            required=["name"],
            field_source={
                "name": "str",
                "confidence": "float",
                "tags": "list[str]",
            },
        )
        result = SchemaWriter(spec=spec).edit(existing)
        assert "class TopicItem(BaseModel):" in result
        assert "tags: list[str]" in result
        # Other class untouched.
        assert "class Other(BaseModel):" in result
        assert "a: int = 1" in result
        # Module docstring preserved.
        assert '"""Topic module."""' in result

    def test_no_match_leaves_source_unchanged(self):
        existing = textwrap.dedent('''\
            from pydantic import BaseModel

            class Other(BaseModel):
                a: int
        ''')
        spec = _spec(
            properties={"name": {"type": "string"}},
            required=["name"],
            field_source={"name": "str"},
        )
        result = SchemaWriter(spec=spec).edit(existing)
        assert "class Other(BaseModel):" in result
        assert "TopicItem" not in result


# ---------------------------------------------------------------------------
# apply()
# ---------------------------------------------------------------------------


class TestApply:
    def test_writes_to_disk(self, tmp_path: Path):
        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = root / "schemas" / "topic.py"

        spec = SchemaSpec(
            name="topic_item",
            cls="llm_pipelines.schemas.topic.TopicItem",
            source_path=str(target),
            definition=JsonSchemaWithRefs(
                json_schema={
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                },
                field_source={"name": "str"},
            ),
        )
        writer = SchemaWriter(spec=spec)
        wrote = writer.apply(writer.write(), root=root)
        assert wrote is True
        assert "name: str" in target.read_text()

    def test_blocks_writes_outside_root(self, tmp_path: Path):
        from llm_pipeline.codegen.io import CodegenPathError

        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = tmp_path / "elsewhere" / "topic.py"

        spec = SchemaSpec(
            name="topic_item",
            cls="llm_pipelines.schemas.topic.TopicItem",
            source_path=str(target),
            definition=JsonSchemaWithRefs(
                json_schema={"properties": {}, "required": []},
                field_source={},
            ),
        )
        writer = SchemaWriter(spec=spec)
        with pytest.raises(CodegenPathError):
            writer.apply(writer.write(), root=root)
