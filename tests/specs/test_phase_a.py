"""Tests for Phase A spec primitives.

Covers the foundational types added in
``llm_pipeline/specs/`` per the per-artifact architecture plan
(``.claude/plans/per-artifact-architecture.md``):

- ``ArtifactSpec`` — common base
- Building blocks: ``SymbolRef``, ``CodeBodySpec``,
  ``JsonSchemaWithRefs``, ``PromptData``
- Kind constants and ``LEVEL_BY_KIND`` mapping

Phase A is pure additions — no behaviour change to existing
pipeline code — so the tests focus on round-trip serialisation,
default values, and the kind-constant invariants.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation
from llm_pipeline.specs import (
    ALL_KINDS,
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_EXTRACTION,
    KIND_PIPELINE,
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TABLE,
    KIND_TOOL,
    LEVEL_BY_KIND,
    ArtifactSpec,
    CodeBodySpec,
    JsonSchemaWithRefs,
    PromptData,
    PromptVariableDefs,
    SymbolRef,
)


# ---------------------------------------------------------------------------
# Kind constants and LEVEL_BY_KIND
# ---------------------------------------------------------------------------


class TestKindConstants:
    def test_all_kinds_listed(self):
        # ALL_KINDS lists every KIND_* constant exactly once.
        expected = {
            KIND_CONSTANT, KIND_ENUM,
            KIND_SCHEMA, KIND_TABLE, KIND_TOOL,
            KIND_STEP, KIND_EXTRACTION, KIND_REVIEW,
            KIND_PIPELINE,
        }
        assert set(ALL_KINDS) == expected
        assert len(ALL_KINDS) == len(expected)  # no duplicates

    def test_kind_values_are_unique_strings(self):
        assert len(set(ALL_KINDS)) == len(ALL_KINDS)

    def test_level_by_kind_covers_every_kind(self):
        assert set(LEVEL_BY_KIND) == set(ALL_KINDS)

    def test_levels_are_correctly_ordered(self):
        # Per the plan: constants=1, enums=2, schemas/tables/tools=3,
        # nodes=4, pipelines=5.
        assert LEVEL_BY_KIND[KIND_CONSTANT] == 1
        assert LEVEL_BY_KIND[KIND_ENUM] == 2
        assert LEVEL_BY_KIND[KIND_SCHEMA] == 3
        assert LEVEL_BY_KIND[KIND_TABLE] == 3
        assert LEVEL_BY_KIND[KIND_TOOL] == 3
        assert LEVEL_BY_KIND[KIND_STEP] == 4
        assert LEVEL_BY_KIND[KIND_EXTRACTION] == 4
        assert LEVEL_BY_KIND[KIND_REVIEW] == 4
        assert LEVEL_BY_KIND[KIND_PIPELINE] == 5

    def test_no_kind_outranks_pipeline(self):
        # Sanity: pipelines are the top level for now. Future
        # additions (e.g. evals) may exceed this — update the test
        # alongside the plan when that lands.
        assert max(LEVEL_BY_KIND.values()) == 5


# ---------------------------------------------------------------------------
# SymbolRef
# ---------------------------------------------------------------------------


class TestSymbolRef:
    def test_minimum_construction(self):
        ref = SymbolRef(symbol="MAX_RETRIES", kind=KIND_CONSTANT, name="max_retries")
        assert ref.symbol == "MAX_RETRIES"
        assert ref.kind == KIND_CONSTANT
        assert ref.name == "max_retries"
        # Position fields default to "not applicable".
        assert ref.line == -1
        assert ref.col_start == 0
        assert ref.col_end == 0

    def test_with_position(self):
        ref = SymbolRef(
            symbol="MAX_RETRIES",
            kind=KIND_CONSTANT,
            name="max_retries",
            line=2, col_start=41, col_end=52,
        )
        assert (ref.line, ref.col_start, ref.col_end) == (2, 41, 52)

    def test_round_trip_json(self):
        ref = SymbolRef(
            symbol="Sentiment", kind=KIND_ENUM, name="sentiment",
            line=0, col_start=8, col_end=17,
        )
        payload = ref.model_dump(mode="json")
        re_ref = SymbolRef.model_validate(payload)
        assert re_ref == ref

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            SymbolRef(  # type: ignore[call-arg]
                symbol="x", kind=KIND_CONSTANT, name="y", unknown_field=1,
            )


# ---------------------------------------------------------------------------
# CodeBodySpec
# ---------------------------------------------------------------------------


class TestCodeBodySpec:
    def test_minimum_construction(self):
        body = CodeBodySpec(source="return None")
        assert body.source == "return None"
        assert body.line_offset_in_file == 0
        assert body.refs == []
        assert body.issues == []

    def test_with_refs(self):
        ref = SymbolRef(symbol="X", kind=KIND_CONSTANT, name="x", line=1, col_start=4, col_end=5)
        body = CodeBodySpec(source="return X", line_offset_in_file=10, refs=[ref])
        assert body.line_offset_in_file == 10
        assert body.refs == [ref]

    def test_round_trip_json_with_refs_and_issues(self):
        ref = SymbolRef(symbol="Y", kind=KIND_ENUM, name="y", line=0, col_start=0, col_end=1)
        issue = ValidationIssue(
            severity="warning", code="unresolved_import",
            message="oops",
            location=ValidationLocation(node="FooStep", field="prepare"),
        )
        body = CodeBodySpec(source="x = 1", refs=[ref], issues=[issue])
        payload = body.model_dump(mode="json")
        re_body = CodeBodySpec.model_validate(payload)
        assert re_body.source == "x = 1"
        assert re_body.refs == [ref]
        assert re_body.issues[0].code == "unresolved_import"


# ---------------------------------------------------------------------------
# JsonSchemaWithRefs
# ---------------------------------------------------------------------------


class TestJsonSchemaWithRefs:
    def test_minimum_construction(self):
        js = JsonSchemaWithRefs(json_schema={"type": "object"})
        assert js.json_schema == {"type": "object"}
        assert js.refs == {}
        assert js.issues == []

    def test_refs_keyed_by_json_pointer(self):
        ref = SymbolRef(symbol="MAX_RETRIES", kind=KIND_CONSTANT, name="max_retries")
        js = JsonSchemaWithRefs(
            json_schema={
                "type": "object",
                "properties": {"retries": {"type": "integer", "default": 3}},
            },
            refs={"/properties/retries/default": [ref]},
        )
        assert "/properties/retries/default" in js.refs
        assert js.refs["/properties/retries/default"][0].name == "max_retries"

    def test_round_trip_json(self):
        ref = SymbolRef(symbol="A", kind=KIND_CONSTANT, name="a")
        js = JsonSchemaWithRefs(
            json_schema={"type": "string", "default": "x"},
            refs={"/default": [ref]},
        )
        payload = js.model_dump(mode="json")
        re_js = JsonSchemaWithRefs.model_validate(payload)
        assert re_js.json_schema == js.json_schema
        assert re_js.refs == js.refs

    def test_field_named_json_schema_not_schema(self):
        # Sanity: ``schema`` shadows BaseModel attribute and is
        # intentionally avoided. This test pins the rename.
        assert "json_schema" in JsonSchemaWithRefs.model_fields
        assert "schema" not in JsonSchemaWithRefs.model_fields


# ---------------------------------------------------------------------------
# PromptData
# ---------------------------------------------------------------------------


class TestPromptData:
    def test_minimum_construction(self):
        pd = PromptData(
            variables=PromptVariableDefs(json_schema={"type": "object"}),
            yaml_path="prompts/foo.yaml",
        )
        assert pd.yaml_path == "prompts/foo.yaml"
        assert pd.variables.auto_vars == {}
        assert pd.variables.auto_vars_refs == {}
        assert pd.system_template is None
        assert pd.user_template is None
        assert pd.model is None

    def test_with_auto_vars_and_refs(self):
        ref = SymbolRef(symbol="Sentiment", kind=KIND_ENUM, name="sentiment")
        pd = PromptData(
            variables=PromptVariableDefs(
                json_schema={"type": "object"},
                auto_vars={"sentiment_options": "enum_names(Sentiment)"},
                auto_vars_refs={"sentiment_options": [ref]},
            ),
            yaml_path="prompts/foo.yaml",
        )
        assert pd.variables.auto_vars["sentiment_options"] == "enum_names(Sentiment)"
        assert pd.variables.auto_vars_refs["sentiment_options"][0].name == "sentiment"

    def test_round_trip_with_phoenix_resolved_fields(self):
        pd = PromptData(
            variables=PromptVariableDefs(json_schema={"type": "object"}),
            yaml_path="prompts/x.yaml",
            system_template="You are a helpful assistant.",
            user_template="Process: {input}",
            model="anthropic:claude-sonnet-4-6",
        )
        payload = pd.model_dump(mode="json")
        re_pd = PromptData.model_validate(payload)
        assert re_pd.system_template == pd.system_template
        assert re_pd.user_template == pd.user_template
        assert re_pd.model == pd.model


# ---------------------------------------------------------------------------
# ArtifactSpec
# ---------------------------------------------------------------------------


class TestArtifactSpec:
    def test_minimum_construction(self):
        art = ArtifactSpec(
            kind=KIND_STEP,
            name="foo",
            cls="my_pkg.FooStep",
            source_path="/path/to/foo_step.py",
        )
        assert art.kind == KIND_STEP
        assert art.name == "foo"
        assert art.cls == "my_pkg.FooStep"
        assert art.source_path == "/path/to/foo_step.py"
        assert art.issues == []

    def test_with_issues(self):
        issue = ValidationIssue(
            severity="error", code="missing_inputs",
            message="INPUTS not set",
            location=ValidationLocation(node="FooStep", field="INPUTS"),
        )
        art = ArtifactSpec(
            kind=KIND_STEP, name="foo", cls="m.FooStep",
            source_path="/x.py", issues=[issue],
        )
        assert art.issues[0].code == "missing_inputs"

    def test_round_trip_json(self):
        issue = ValidationIssue(
            severity="warning", code="auto_vars_field_overlap",
            message="overlap", location=ValidationLocation(),
        )
        art = ArtifactSpec(
            kind=KIND_PIPELINE, name="text_analyzer",
            cls="my_pkg.TextAnalyzerPipeline",
            source_path="/x/y.py",
            issues=[issue],
        )
        payload = art.model_dump(mode="json")
        re_art = ArtifactSpec.model_validate(payload)
        assert re_art.kind == art.kind
        assert re_art.name == art.name
        assert re_art.cls == art.cls
        assert re_art.source_path == art.source_path
        assert re_art.issues[0].code == "auto_vars_field_overlap"

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            ArtifactSpec(  # type: ignore[call-arg]
                kind=KIND_STEP, name="x", cls="m.X",
                source_path="/x.py", unknown_field=1,
            )

    def test_kind_accepts_arbitrary_string_at_base_level(self):
        # Base ``ArtifactSpec`` accepts any string for ``kind`` —
        # per-kind subclasses (added in Phase C) will pin this with
        # ``Literal[KIND_X]``. Verifying no validator on the base.
        art = ArtifactSpec(kind="custom", name="x", cls="m.X", source_path="/x.py")
        assert art.kind == "custom"
