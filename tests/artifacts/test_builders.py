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

import pytest
from pydantic import BaseModel, Field

from llm_pipeline.artifacts.base.builder import (
    build_code_body,
    json_schema_with_refs,
)
from llm_pipeline.artifacts.constants import ConstantBuilder
from llm_pipeline.artifacts.enums import EnumBuilder
from llm_pipeline.artifacts.extractions import ExtractionBuilder
from llm_pipeline.artifacts.reviews import ReviewBuilder
from llm_pipeline.artifacts.schemas import SchemaBuilder
from llm_pipeline.artifacts.steps import StepBuilder
from llm_pipeline.artifacts.tools import ToolBuilder
from llm_pipeline.artifacts.base.kinds import (
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


from llm_pipeline.agent_tool import AgentTool
from llm_pipeline.inputs import StepInputs


class SearchInputs(StepInputs):
    library_id: str = ""


class SearchArgs(BaseModel):
    query: str
    limit: int = 5


class SearchTool(AgentTool):
    """Search the docs index."""

    INPUTS = SearchInputs
    ARGS = SearchArgs

    @classmethod
    def run(cls, inputs, args, ctx):
        return ""


class _BareTool:
    """Stand-in for an AgentTool subclass with no INPUTS/ARGS set —
    exercises the builder's tolerance for missing class attrs."""

    INPUTS = None
    ARGS = None


# ---------------------------------------------------------------------------
# Constants + enums (no cst_analysis)
# ---------------------------------------------------------------------------


class TestBuildConstantSpec:
    def test_int_constant(self):
        from llm_pipeline.constants import Constant

        class MAX_RETRIES(Constant):
            value = 3

        spec = ConstantBuilder(
            name="max_retries", cls=MAX_RETRIES,
            source_path="/x/constants/retries.py",
        ).build()
        assert spec.kind == KIND_CONSTANT
        assert spec.value_type == "int"
        assert spec.value == 3

    def test_dict_constant_serialises(self):
        from llm_pipeline.constants import Constant

        class CONFIG(Constant):
            value = {"a": 1, "b": [1, 2]}

        spec = ConstantBuilder(
            name="config", cls=CONFIG, source_path="/x.py",
        ).build()
        # Round-trip through JSON to confirm serialisability.
        re = type(spec).model_validate(spec.model_dump(mode="json"))
        assert re.value == {"a": 1, "b": [1, 2]}

    def test_init_subclass_rejects_missing_value(self):
        from llm_pipeline.constants import Constant

        with pytest.raises(TypeError, match="value"):
            class _BAD_NO_VALUE(Constant):  # noqa: N801 — match user style
                pass

    def test_init_subclass_rejects_disallowed_value_type(self):
        from llm_pipeline.constants import Constant

        with pytest.raises(TypeError, match="value"):
            class _BAD_TYPE(Constant):  # noqa: N801
                value = object()  # not a primitive


class TestBuildEnumSpec:
    def test_str_enum(self):
        class Sentiment(Enum):
            POSITIVE = "pos"
            NEGATIVE = "neg"

        spec = EnumBuilder(
            name="sentiment", cls=Sentiment, source_path="/x.py",
        ).build()
        assert spec.kind == KIND_ENUM
        assert spec.value_type == "str"
        assert {(m.name, m.value) for m in spec.members} == {
            ("POSITIVE", "pos"), ("NEGATIVE", "neg"),
        }

    def test_int_enum(self):
        class Status(Enum):
            OPEN = 1
            CLOSED = 2

        spec = EnumBuilder(name="status", cls=Status, source_path="/x.py").build()
        assert spec.value_type == "int"

    def test_cls_path_derived_from_class(self):
        class Color(Enum):
            RED = "red"

        spec = EnumBuilder(name="color", cls=Color, source_path="/x.py").build()
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
        spec = SchemaBuilder(
            name="address", cls=Address, source_path="/x.py",
            source_text=source, resolver=_resolver({}),
        ).build()
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
        spec = SchemaBuilder(
            name="foo", cls=_SchemaWithConst, source_path="/x.py",
            source_text=source, resolver=resolver,
        ).build()
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
        spec = StepBuilder(
            name="foo", cls=_StepWithBodies, source_path="/x.py",
            source_text=source, resolver=_resolver({}),
        ).build()
        assert spec.kind == KIND_STEP
        assert spec.inputs is not None
        assert spec.instructions is not None
        # Bodies analysed.
        assert spec.prepare is not None
        assert spec.run is not None
        assert "return []" in spec.prepare.source

    def test_tools_extracted_as_artifact_refs(self):
        spec = StepBuilder(
            name="foo", cls=_StepWithTools, source_path="/x.py",
            source_text="class _StepWithTools: pass",
            resolver=_resolver({}),
        ).build()
        # One ArtifactRef per DEFAULT_TOOLS entry, in source order;
        # source-side name is the tool's Python class name.
        assert [t.name for t in spec.tools] == ["_ToolA", "_ToolB"]
        # Empty resolver → no resolved refs.
        assert all(t.ref is None for t in spec.tools)

    def test_tools_resolve_when_resolver_matches(self):
        module = _ToolA.__module__
        spec = StepBuilder(
            name="foo", cls=_StepWithTools, source_path="/x.py",
            source_text="class _StepWithTools: pass",
            resolver=_resolver({
                (module, "_ToolA"): ("tool", "search"),
                (module, "_ToolB"): ("tool", "summarise"),
            }),
        ).build()
        assert [t.ref.name for t in spec.tools] == ["search", "summarise"]
        assert all(t.ref.kind == "tool" for t in spec.tools)

    def test_missing_inputs_yields_none(self):
        spec = StepBuilder(
            name="foo", cls=_StepEmpty, source_path="/x.py",
            source_text="class _StepEmpty: pass",
            resolver=_resolver({}),
        ).build()
        assert spec.inputs is None
        assert spec.instructions is None


class TestBuildExtractionSpec:
    def test_table_ref_derived_from_model(self):
        spec = ExtractionBuilder(
            name="topic", cls=_ExtractionWithModel, source_path="/x.py",
            source_text="class _ExtractionWithModel: pass",
            resolver=_resolver({}),
        ).build()
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
        spec = ExtractionBuilder(
            name="topic", cls=_ExtractionWithModel, source_path="/x.py",
            source_text="class _ExtractionWithModel: pass",
            resolver=_resolver({(module, "_TopicRow"): ("table", "topic_row")}),
        ).build()
        assert spec.table is not None
        assert spec.table.ref is not None
        assert spec.table.ref.kind == "table"
        assert spec.table.ref.name == "topic_row"

    def test_no_model_yields_none_table(self):
        spec = ExtractionBuilder(
            name="foo", cls=_ExtractionNoModel, source_path="/x.py",
            source_text="class _ExtractionNoModel: pass",
            resolver=_resolver({}),
        ).build()
        assert spec.table is None


class TestBuildReviewSpec:
    def test_webhook_url_captured(self):
        spec = ReviewBuilder(
            name="foo", cls=_ReviewWithWebhook, source_path="/x.py",
            source_text="class _ReviewWithWebhook: pass",
            resolver=_resolver({}),
        ).build()
        assert spec.kind == KIND_REVIEW
        assert spec.webhook_url == "https://hooks.example.com/x"

    def test_no_webhook_yields_none(self):
        spec = ReviewBuilder(
            name="foo", cls=_ReviewNoWebhook, source_path="/x.py",
            source_text="class _ReviewNoWebhook: pass",
            resolver=_resolver({}),
        ).build()
        assert spec.webhook_url is None


class TestBuildToolSpec:
    def test_partial_with_no_inputs_or_args(self):
        spec = ToolBuilder(
            name="bare", cls=_BareTool, source_path="/x.py",
            source_text="class _BareTool: pass",
            resolver=_resolver({}),
        ).build()
        assert spec.kind == KIND_TOOL
        assert spec.inputs is None
        assert spec.args is None
        assert spec.body is None

    def test_reads_inputs_args_from_class(self):
        spec = ToolBuilder(
            name="search", cls=SearchTool, source_path="/x.py",
            source_text="class SearchTool: pass",
            resolver=_resolver({}),
        ).build()
        assert spec.inputs is not None
        assert "library_id" in spec.inputs.json_schema.get("properties", {})
        assert spec.args is not None
        assert "query" in spec.args.json_schema.get("properties", {})


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
