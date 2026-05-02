"""Tests for the per-kind spec builders.

End-to-end with real Pydantic classes + the real
:mod:`llm_pipeline.cst_analysis` analyser. The resolver hook is
faked so we can pin which (module_path, symbol) pairs map to
which (kind, name) without standing up the full registry layer
(that's Phase C.2).
"""
from __future__ import annotations

import textwrap
from enum import Enum

from pydantic import BaseModel, Field

from llm_pipeline.specs.builders import (
    build_code_body,
    build_constant_spec,
    build_enum_spec,
    build_extraction_spec,
    build_review_spec,
    build_schema_spec,
    build_step_spec,
    build_tool_spec,
    json_schema_with_refs,
)
from llm_pipeline.specs.kinds import (
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_EXTRACTION,
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TOOL,
)


def _resolver(table: dict[tuple[str, str], tuple[str, str]]):
    def hook(module_path: str, symbol: str) -> tuple[str, str] | None:
        return table.get((module_path, symbol))
    return hook


# ---------------------------------------------------------------------------
# Module-level fixtures
#
# The cst_analysis layer matches classes by ``__qualname__`` (e.g.
# ``Outer.Inner``). Classes defined inside test methods get dotted
# qualnames like ``TestX.test_y.<locals>.Foo`` — which won't match
# synthetic source strings declaring ``class Foo:`` at module level.
# Defining fixtures at module scope keeps qualnames as simple names.
# ---------------------------------------------------------------------------


class _SchemaWithConst(BaseModel):
    retries: int = 3


class _StepInputs(BaseModel):
    text: str


class _StepInstructions(BaseModel):
    label: str


class _ToolA:
    name = "search"


class _ToolB:
    name = "summarise"


class _StepWithBodies:
    INPUTS = _StepInputs
    INSTRUCTIONS = _StepInstructions
    DEFAULT_TOOLS: list = []

    def prepare(self, inputs):  # type: ignore[no-untyped-def]
        return []

    def run(self, ctx):  # type: ignore[no-untyped-def]
        return None


class _StepWithTools:
    INPUTS = None
    INSTRUCTIONS = None
    DEFAULT_TOOLS = [_ToolA, _ToolB]


class _StepEmpty:
    INPUTS = None
    INSTRUCTIONS = None
    DEFAULT_TOOLS: list = []


class _TopicRow:
    """SQLModel-style placeholder for extraction MODEL tests."""


class _ExtractionWithModel:
    INPUTS = None
    MODEL = _TopicRow


class _ExtractionNoModel:
    INPUTS = None
    MODEL = None


class _ReviewWithWebhook:
    INPUTS = None
    OUTPUT = None
    webhook_url = "https://hooks.example.com/x"


class _ReviewNoWebhook:
    INPUTS = None
    OUTPUT = None
    webhook_url = None


class _ToolInputs(BaseModel):
    query: str


class _SearchTool:
    pass


# ---------------------------------------------------------------------------
# Constants + enums (no cst_analysis)
# ---------------------------------------------------------------------------


class TestBuildConstantSpec:
    def test_int_constant(self):
        spec = build_constant_spec(
            name="max_retries", value=3,
            cls_path="pkg.constants.retries.MAX_RETRIES",
            source_path="/x/constants/retries.py",
        )
        assert spec.kind == KIND_CONSTANT
        assert spec.value_type == "int"
        assert spec.value == 3

    def test_dict_constant_serialises(self):
        spec = build_constant_spec(
            name="config", value={"a": 1, "b": [1, 2]},
            cls_path="pkg.constants.CONFIG",
            source_path="/x.py",
        )
        # Round-trip through JSON to confirm serialisability.
        re = type(spec).model_validate(spec.model_dump(mode="json"))
        assert re.value == {"a": 1, "b": [1, 2]}


class TestBuildEnumSpec:
    def test_str_enum(self):
        class Sentiment(Enum):
            POSITIVE = "pos"
            NEGATIVE = "neg"

        spec = build_enum_spec(
            name="sentiment", enum_cls=Sentiment, source_path="/x.py",
        )
        assert spec.kind == KIND_ENUM
        assert spec.value_type == "str"
        assert {(m.name, m.value) for m in spec.members} == {
            ("POSITIVE", "pos"), ("NEGATIVE", "neg"),
        }

    def test_int_enum(self):
        class Status(Enum):
            OPEN = 1
            CLOSED = 2

        spec = build_enum_spec(name="status", enum_cls=Status, source_path="/x.py")
        assert spec.value_type == "int"

    def test_cls_path_derived_from_class(self):
        class Color(Enum):
            RED = "red"

        spec = build_enum_spec(name="color", enum_cls=Color, source_path="/x.py")
        # Module + qualname.
        assert spec.cls.endswith(".Color")


# ---------------------------------------------------------------------------
# Schemas (Pydantic introspection + cst_analysis)
# ---------------------------------------------------------------------------


class TestBuildSchemaSpec:
    def test_basic_schema(self):
        class Address(BaseModel):
            street: str
            zipcode: int = 1000

        source = textwrap.dedent("""
            from pydantic import BaseModel

            class Address(BaseModel):
                street: str
                zipcode: int = 1000
        """)
        spec = build_schema_spec(
            name="address", cls=Address, source_path="/x.py",
            source_text=source, resolver=_resolver({}),
        )
        assert spec.kind == KIND_SCHEMA
        # Pydantic JSON schema present.
        assert "properties" in spec.definition.json_schema
        # No refs because resolver returned nothing.
        assert spec.definition.refs == {}

    def test_schema_with_constant_reference(self):
        # Source string declares the same class name as the
        # module-level ``_SchemaWithConst`` fixture so qualname matches.
        source = textwrap.dedent("""
            from pkg.constants import MAX_RETRIES
            from pydantic import BaseModel

            class _SchemaWithConst(BaseModel):
                retries: int = MAX_RETRIES
        """)
        resolver = _resolver({
            ("pkg.constants", "MAX_RETRIES"): ("constant", "max_retries"),
        })
        spec = build_schema_spec(
            name="foo", cls=_SchemaWithConst, source_path="/x.py",
            source_text=source, resolver=resolver,
        )
        assert "/properties/retries/default" in spec.definition.refs


# ---------------------------------------------------------------------------
# Step / Extraction / Review builders (cst_analysis-aware)
# ---------------------------------------------------------------------------


class TestBuildStepSpec:
    def test_minimal_step(self):
        # Source string mirrors the module-level fixtures so all
        # qualnames match what cst_analysis sees.
        source = textwrap.dedent("""
            from pydantic import BaseModel

            class _StepInputs(BaseModel):
                text: str

            class _StepInstructions(BaseModel):
                label: str

            class _StepWithBodies:
                INPUTS = _StepInputs
                INSTRUCTIONS = _StepInstructions
                DEFAULT_TOOLS: list = []

                def prepare(self, inputs):
                    return []

                def run(self, ctx):
                    return None
        """)
        spec = build_step_spec(
            name="foo", cls=_StepWithBodies, source_path="/x.py",
            source_text=source, resolver=_resolver({}),
        )
        assert spec.kind == KIND_STEP
        assert spec.inputs is not None
        assert spec.instructions is not None
        # Bodies analysed.
        assert spec.prepare is not None
        assert spec.run is not None
        assert "return []" in spec.prepare.source

    def test_tool_names_extracted(self):
        spec = build_step_spec(
            name="foo", cls=_StepWithTools, source_path="/x.py",
            source_text="class _StepWithTools: pass",
            resolver=_resolver({}),
        )
        assert spec.tool_names == ["search", "summarise"]

    def test_missing_inputs_yields_none(self):
        spec = build_step_spec(
            name="foo", cls=_StepEmpty, source_path="/x.py",
            source_text="class _StepEmpty: pass",
            resolver=_resolver({}),
        )
        assert spec.inputs is None
        assert spec.instructions is None


class TestBuildExtractionSpec:
    def test_table_ref_derived_from_model(self):
        spec = build_extraction_spec(
            name="topic", cls=_ExtractionWithModel, source_path="/x.py",
            source_text="class _ExtractionWithModel: pass",
            resolver=_resolver({}),
        )
        assert spec.kind == KIND_EXTRACTION
        # ``table`` is an ArtifactRef carrying the source-side
        # Python class name; ``ref`` stays None when the resolver
        # doesn't match (this test passes an empty resolver).
        assert spec.table is not None
        assert spec.table.name == "_TopicRow"
        assert spec.table.ref is None

    def test_table_resolves_when_resolver_matches(self):
        # Resolver maps the MODEL class to a registered table.
        module = _ExtractionWithModel.MODEL.__module__
        spec = build_extraction_spec(
            name="topic", cls=_ExtractionWithModel, source_path="/x.py",
            source_text="class _ExtractionWithModel: pass",
            resolver=_resolver({(module, "_TopicRow"): ("table", "topic_row")}),
        )
        assert spec.table is not None
        assert spec.table.ref is not None
        assert spec.table.ref.kind == "table"
        assert spec.table.ref.name == "topic_row"

    def test_no_model_yields_none_table(self):
        spec = build_extraction_spec(
            name="foo", cls=_ExtractionNoModel, source_path="/x.py",
            source_text="class _ExtractionNoModel: pass",
            resolver=_resolver({}),
        )
        assert spec.table is None


class TestBuildReviewSpec:
    def test_webhook_url_captured(self):
        spec = build_review_spec(
            name="foo", cls=_ReviewWithWebhook, source_path="/x.py",
            source_text="class _ReviewWithWebhook: pass",
            resolver=_resolver({}),
        )
        assert spec.kind == KIND_REVIEW
        assert spec.webhook_url == "https://hooks.example.com/x"

    def test_no_webhook_yields_none(self):
        spec = build_review_spec(
            name="foo", cls=_ReviewNoWebhook, source_path="/x.py",
            source_text="class _ReviewNoWebhook: pass",
            resolver=_resolver({}),
        )
        assert spec.webhook_url is None


class TestBuildToolSpec:
    def test_skeleton_with_no_extras(self):
        spec = build_tool_spec(
            name="search", cls=_SearchTool, source_path="/x.py",
            source_text="class _SearchTool: pass",
            resolver=_resolver({}),
        )
        assert spec.kind == KIND_TOOL
        assert spec.inputs is None
        assert spec.args is None
        assert spec.body is None

    def test_with_inputs_class(self):
        spec = build_tool_spec(
            name="search", cls=_SearchTool, source_path="/x.py",
            source_text="class _SearchTool: pass",
            resolver=_resolver({}),
            inputs_cls=_ToolInputs,
        )
        assert spec.inputs is not None
        assert "query" in spec.inputs.json_schema.get("properties", {})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestJsonSchemaWithRefs:
    def test_returns_none_for_none_cls(self):
        assert json_schema_with_refs(
            cls=None, source_text="", resolver=_resolver({}),
        ) is None

    def test_handles_missing_class_in_source(self):
        # ``_SchemaWithConst`` exists at runtime as a module-level
        # fixture, but isn't in the source string we pass —
        # analyze_class_fields raises AnalysisError; builder
        # tolerates that and returns the schema with empty refs.
        result = json_schema_with_refs(
            cls=_SchemaWithConst, source_text="# unrelated",
            resolver=_resolver({}),
        )
        assert result is not None
        assert result.refs == {}


class TestBuildCodeBody:
    def test_returns_none_when_function_missing(self):
        # Function not in source -> None (caller should treat as
        # "no body to render" rather than an error).
        result = build_code_body(
            function_qualname="missing",
            source_text="def other(): pass\n",
            resolver=_resolver({}),
        )
        assert result is None
