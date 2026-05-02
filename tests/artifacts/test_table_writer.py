"""Tests for :class:`TableWriter` — write / edit / apply."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from llm_pipeline.artifacts.base.blocks import JsonSchemaWithRefs
from llm_pipeline.artifacts.tables import TableSpec, TableWriter


def _spec(
    *,
    properties: dict | None = None,
    required: list[str] | None = None,
    field_source: dict[str, str] | None = None,
    name: str = "Topic",
    table_name: str = "topic",
) -> TableSpec:
    return TableSpec(
        name=name.lower(),
        cls=f"llm_pipelines.tables.topic.{name}",
        source_path="/tmp/topic.py",
        definition=JsonSchemaWithRefs(
            json_schema={
                "properties": properties or {},
                "required": required or [],
            },
            field_source=field_source or {},
        ),
        table_name=table_name,
        indices=[],
    )


# ---------------------------------------------------------------------------
# write()
# ---------------------------------------------------------------------------


class TestWrite:
    def test_basic_table(self):
        spec = _spec(
            properties={
                "id": {"type": "integer"},
                "name": {"type": "string"},
            },
            required=["name"],
            field_source={"id": "int | None", "name": "str"},
        )
        result = TableWriter(spec=spec).write()
        assert "from sqlmodel import SQLModel" in result
        assert "class Topic(SQLModel, table=True):" in result
        assert "id: int | None" in result
        assert "name: str" in result
        assert "__tablename__ = 'topic'" in result

    def test_output_parses_as_valid_python(self):
        import libcst as cst

        spec = _spec(
            properties={"id": {"type": "integer"}},
            field_source={"id": "int"},
        )
        result = TableWriter(spec=spec).write()
        # Should parse without raising.
        cst.parse_module(result)


# ---------------------------------------------------------------------------
# edit()
# ---------------------------------------------------------------------------


_EXISTING = textwrap.dedent('''\
    """Topic table."""
    from sqlmodel import Field, SQLModel


    class Topic(SQLModel, table=True):
        """Old docstring."""
        id: int | None = Field(default=None, primary_key=True)
        name: str
''')


class TestEdit:
    def test_replaces_target_class(self):
        spec = _spec(
            properties={
                "id": {"type": "integer"},
                "name": {"type": "string"},
                "score": {"type": "number", "default": 0.0},
            },
            required=["name"],
            field_source={
                "id": "int | None",
                "name": "str",
                "score": "float",
            },
        )
        result = TableWriter(spec=spec).edit(_EXISTING)
        assert "class Topic(SQLModel, table=True):" in result
        assert "score: float = 0.0" in result
        # Module docstring preserved.
        assert '"""Topic table."""' in result

    def test_no_match_leaves_source_unchanged(self):
        spec = _spec(
            properties={"id": {"type": "integer"}},
            field_source={"id": "int"},
            name="DoesNotExist",
        )
        result = TableWriter(spec=spec).edit(_EXISTING)
        assert "DoesNotExist" not in result
        # Original Topic class survives verbatim.
        assert "primary_key=True" in result


# ---------------------------------------------------------------------------
# apply()
# ---------------------------------------------------------------------------


class TestApply:
    def test_writes_to_disk(self, tmp_path: Path):
        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = root / "tables" / "topic.py"

        spec = TableSpec(
            name="topic",
            cls="llm_pipelines.tables.topic.Topic",
            source_path=str(target),
            definition=JsonSchemaWithRefs(
                json_schema={
                    "properties": {"id": {"type": "integer"}},
                    "required": [],
                },
                field_source={"id": "int"},
            ),
            table_name="topic",
            indices=[],
        )
        writer = TableWriter(spec=spec)
        wrote = writer.apply(writer.write(), root=root)
        assert wrote is True
        assert "table=True" in target.read_text()

    def test_blocks_writes_outside_root(self, tmp_path: Path):
        from llm_pipeline.codegen.io import CodegenPathError

        root = tmp_path / "llm_pipelines"
        root.mkdir()
        target = tmp_path / "elsewhere" / "topic.py"

        spec = TableSpec(
            name="topic",
            cls="llm_pipelines.tables.topic.Topic",
            source_path=str(target),
            definition=JsonSchemaWithRefs(
                json_schema={"properties": {}, "required": []},
                field_source={},
            ),
            table_name="topic",
            indices=[],
        )
        writer = TableWriter(spec=spec)
        with pytest.raises(CodegenPathError):
            writer.apply(writer.write(), root=root)
