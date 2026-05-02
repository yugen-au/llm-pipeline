"""Round-trip tests for the per-kind ``ArtifactSpec`` subclasses.

Each subclass: minimal construction, JSON round-trip, kind-Literal
pinning, extra-field rejection.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm_pipeline.artifacts import (
    ArtifactRef,
    CodeBodySpec,
    ConstantSpec,
    EnumMemberSpec,
    EnumSpec,
    ExtractionSpec,
    JsonSchemaWithRefs,
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_EXTRACTION,
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TOOL,
    PromptData,
    PromptVariableDefs,
    ReviewSpec,
    SchemaSpec,
    StepSpec,
    SymbolRef,
    ToolSpec,
)


def _round_trip(spec):
    payload = spec.model_dump(mode="json")
    return type(spec).model_validate(payload)


# ---------------------------------------------------------------------------
# ConstantSpec
# ---------------------------------------------------------------------------


class TestConstantSpec:
    def test_minimum_construction(self):
        c = ConstantSpec(
            kind=KIND_CONSTANT,
            name="max_retries",
            cls="pkg.constants.MAX_RETRIES",
            source_path="/x/constants/retries.py",
            value_type="int",
            value=3,
        )
        assert c.kind == KIND_CONSTANT
        assert c.value == 3

    def test_round_trip(self):
        c = ConstantSpec(
            kind=KIND_CONSTANT,
            name="config_dict",
            cls="pkg.constants.CONFIG",
            source_path="/x.py",
            value_type="dict",
            value={"debug": True, "limit": 10},
        )
        assert _round_trip(c) == c

    def test_kind_pinned(self):
        with pytest.raises(ValidationError):
            ConstantSpec(  # type: ignore[arg-type]
                kind="something_else",
                name="x",
                cls="m.X",
                source_path="/x.py",
                value_type="int",
                value=1,
            )


# ---------------------------------------------------------------------------
# EnumSpec
# ---------------------------------------------------------------------------


class TestEnumSpec:
    def test_minimum_construction(self):
        e = EnumSpec(
            kind=KIND_ENUM,
            name="sentiment",
            cls="pkg.enums.Sentiment",
            source_path="/x.py",
            value_type="str",
            members=[
                EnumMemberSpec(name="POSITIVE", value="pos"),
                EnumMemberSpec(name="NEGATIVE", value="neg"),
            ],
        )
        assert e.kind == KIND_ENUM
        assert len(e.members) == 2

    def test_round_trip(self):
        e = EnumSpec(
            kind=KIND_ENUM,
            name="status",
            cls="pkg.enums.Status",
            source_path="/x.py",
            value_type="int",
            members=[EnumMemberSpec(name="OPEN", value=1), EnumMemberSpec(name="CLOSED", value=2)],
        )
        re_e = _round_trip(e)
        assert re_e.members[0].name == "OPEN"
        assert re_e.members[0].value == 1

    def test_empty_members_allowed(self):
        e = EnumSpec(
            kind=KIND_ENUM,
            name="empty",
            cls="m.E",
            source_path="/x.py",
            value_type="str",
            members=[],
        )
        assert e.members == []


# ---------------------------------------------------------------------------
# SchemaSpec
# ---------------------------------------------------------------------------


class TestSchemaSpec:
    def test_minimum_construction(self):
        s = SchemaSpec(
            kind=KIND_SCHEMA,
            name="address",
            cls="pkg.schemas.Address",
            source_path="/x.py",
            definition=JsonSchemaWithRefs(json_schema={"type": "object"}),
        )
        assert s.kind == KIND_SCHEMA
        assert s.definition.json_schema == {"type": "object"}

    def test_field_named_definition_not_schema(self):
        # Pin: ``definition`` rather than ``schema`` to avoid the
        # Pydantic BaseModel attribute-shadowing warning.
        assert "definition" in SchemaSpec.model_fields
        assert "schema" not in SchemaSpec.model_fields

    def test_round_trip_with_refs(self):
        ref = SymbolRef(symbol="X", kind="constant", name="x")
        s = SchemaSpec(
            kind=KIND_SCHEMA, name="x", cls="m.X", source_path="/x.py",
            definition=JsonSchemaWithRefs(
                json_schema={"type": "object", "properties": {"a": {"type": "integer"}}},
                refs={"/properties/a/default": [ref]},
            ),
        )
        re_s = _round_trip(s)
        assert re_s.definition.refs["/properties/a/default"][0].name == "x"


# ---------------------------------------------------------------------------
# ToolSpec
# ---------------------------------------------------------------------------


class TestToolSpec:
    def test_skeleton_defaults(self):
        t = ToolSpec(
            kind=KIND_TOOL, name="search", cls="m.SearchTool", source_path="/x.py",
        )
        assert t.inputs is None
        assert t.args is None
        assert t.body is None

    def test_round_trip_with_inputs(self):
        t = ToolSpec(
            kind=KIND_TOOL, name="search", cls="m.SearchTool", source_path="/x.py",
            inputs=JsonSchemaWithRefs(json_schema={"type": "object"}),
        )
        re_t = _round_trip(t)
        assert re_t.inputs.json_schema == {"type": "object"}


# ---------------------------------------------------------------------------
# StepSpec
# ---------------------------------------------------------------------------


class TestStepSpec:
    def test_minimum_construction(self):
        s = StepSpec(
            kind=KIND_STEP,
            name="sentiment_analysis",
            cls="pkg.steps.SentimentAnalysisStep",
            source_path="/x.py",
        )
        assert s.kind == KIND_STEP
        assert s.tools == []
        # All composite slots default to None.
        assert s.inputs is None
        assert s.instructions is None
        assert s.prepare is None
        assert s.run is None
        assert s.prompt is None

    def test_round_trip_with_full_payload(self):
        s = StepSpec(
            kind=KIND_STEP,
            name="x", cls="m.X", source_path="/x.py",
            inputs=JsonSchemaWithRefs(json_schema={"type": "object"}),
            instructions=JsonSchemaWithRefs(json_schema={"type": "object"}),
            prepare=CodeBodySpec(source="return []"),
            run=CodeBodySpec(source="return None"),
            prompt=PromptData(
                variables=PromptVariableDefs(json_schema={"type": "object"}),
                yaml_path="prompts/x.yaml",
            ),
            tools=[ArtifactRef(name="ToolA"), ArtifactRef(name="ToolB")],
        )
        re_s = _round_trip(s)
        assert [t.name for t in re_s.tools] == ["ToolA", "ToolB"]
        assert re_s.prompt.yaml_path == "prompts/x.yaml"
        assert re_s.prepare.source == "return []"


# ---------------------------------------------------------------------------
# ExtractionSpec
# ---------------------------------------------------------------------------


class TestExtractionSpec:
    def test_minimum_construction(self):
        e = ExtractionSpec(
            kind=KIND_EXTRACTION, name="topic", cls="m.TopicExtraction",
            source_path="/x.py",
        )
        assert e.kind == KIND_EXTRACTION
        assert e.table is None

    def test_round_trip(self):
        e = ExtractionSpec(
            kind=KIND_EXTRACTION, name="topic", cls="m.TopicExtraction",
            source_path="/x.py",
            table=ArtifactRef(name="TopicRow"),
            extract=CodeBodySpec(source="return [TopicRow(...)]"),
        )
        re_e = _round_trip(e)
        assert re_e.table is not None
        assert re_e.table.name == "TopicRow"
        assert "TopicRow" in re_e.extract.source


# ---------------------------------------------------------------------------
# ReviewSpec
# ---------------------------------------------------------------------------


class TestReviewSpec:
    def test_minimum_construction(self):
        r = ReviewSpec(
            kind=KIND_REVIEW, name="approval", cls="m.ApprovalReview",
            source_path="/x.py",
        )
        assert r.kind == KIND_REVIEW
        assert r.webhook_url is None

    def test_round_trip_with_webhook(self):
        r = ReviewSpec(
            kind=KIND_REVIEW, name="approval", cls="m.ApprovalReview",
            source_path="/x.py",
            webhook_url="https://hooks.example.com/x",
        )
        re_r = _round_trip(r)
        assert re_r.webhook_url == "https://hooks.example.com/x"
