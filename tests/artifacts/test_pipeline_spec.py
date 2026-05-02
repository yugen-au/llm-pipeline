"""Tests for :class:`PipelineSpec` and ``build_pipeline_spec``.

Covers the per-artifact translation of a Pipeline's legacy
``cls._spec`` into the new :class:`llm_pipeline.artifacts.PipelineSpec`.
The runtime introspection happens at ``Pipeline.__init_subclass__``
time (the legacy validator); this builder transforms that into
the new shape and the walker registers it.
"""
from __future__ import annotations

from typing import ClassVar

from pydantic_graph import End, GraphRunContext
from sqlmodel import Field as SQLField, SQLModel

from llm_pipeline.cst_analysis import ResolverHook
from llm_pipeline.graph import (
    Extraction,
    ExtractionNode,
    FromInput,
    FromOutput,
    FromPipeline,
    LLMResultMixin,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    Step,
    StepInputs,
)
from llm_pipeline.prompts import PromptVariables
from llm_pipeline.artifacts import (
    KIND_PIPELINE,
    NodeBindingSpec,
    PipelineSpec,
)
from llm_pipeline.artifacts.builders import PipelineBuilder


def _resolver_noop(_module: str, _symbol: str) -> tuple[str, str] | None:
    return None


# ---------------------------------------------------------------------------
# Fixture pipeline (module-scope so __init_subclass__ runs once)
# ---------------------------------------------------------------------------


class _FixtureInputData(PipelineInputData):
    text: str


class _FixtureRow(SQLModel, table=True):
    __tablename__ = "test_pipeline_spec_rows"
    __table_args__ = {"extend_existing": True}
    id: int | None = SQLField(default=None, primary_key=True)
    label: str
    run_id: str


class _ClassifyInputs(StepInputs):
    text: str


class _ClassifyInstructions(LLMResultMixin):
    label: str = ""
    example: ClassVar[dict] = {"label": "x", "confidence_score": 0.5}


class _ClassifyPrompt(PromptVariables):
    text: str  # missing description — produces a capture (irrelevant here)


class _ClassifyStep(LLMStepNode):
    INPUTS = _ClassifyInputs
    INSTRUCTIONS = _ClassifyInstructions

    def prepare(self, inputs: _ClassifyInputs) -> list[_ClassifyPrompt]:
        return [_ClassifyPrompt(text=inputs.text)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> "_ClassifyExtraction":
        await self._run_llm(ctx)
        return _ClassifyExtraction()


class _FromClassifyInputs(StepInputs):
    label: str
    run_id: str


class _ClassifyExtraction(ExtractionNode):
    MODEL = _FixtureRow
    INPUTS = _FromClassifyInputs

    def extract(self, inputs: _FromClassifyInputs) -> list[_FixtureRow]:
        return [_FixtureRow(label=inputs.label, run_id=inputs.run_id)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_extraction(ctx)
        return End(None)


class _FixturePipeline(Pipeline):
    INPUT_DATA = _FixtureInputData
    nodes = [
        Step(
            _ClassifyStep,
            inputs_spec=_ClassifyInputs.sources(text=FromInput("text")),
        ),
        Extraction(
            _ClassifyExtraction,
            inputs_spec=_FromClassifyInputs.sources(
                label=FromOutput(_ClassifyStep, field="label"),
                run_id=FromPipeline("run_id"),
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# build_pipeline_spec
# ---------------------------------------------------------------------------


class TestBuildPipelineSpec:
    def test_kind_and_identity(self):
        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=_resolver_noop,
        ).build()
        assert isinstance(spec, PipelineSpec)
        assert spec.kind == KIND_PIPELINE
        assert spec.name == "fixture"
        assert spec.cls.endswith("_FixturePipeline")
        assert spec.source_path == "/tmp/fixture.py"

    def test_input_data_is_artifact_field(self):
        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=_resolver_noop,
        ).build()
        assert spec.input_data is not None
        # It's a JsonSchemaWithRefs ArtifactField (routable target)
        assert hasattr(spec.input_data, "json_schema")
        assert hasattr(spec.input_data, "issues")
        assert "text" in spec.input_data.json_schema.get("properties", {})

    def test_node_bindings_one_per_pipeline_node(self):
        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=_resolver_noop,
        ).build()
        assert len(spec.nodes) == 2
        # Order matches Pipeline.nodes declaration order.
        assert spec.nodes[0].binding_kind == "step"
        assert spec.nodes[1].binding_kind == "extraction"

    def test_node_binding_carries_registry_key_name(self):
        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=_resolver_noop,
        ).build()
        # Snake-case derivation, suffix-stripped — matches what
        # walk_steps / walk_extractions registers under.
        names = [nb.node_name for nb in spec.nodes]
        assert names == ["_classify", "_classify"]

    def test_node_binding_wiring_preserved(self):
        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=_resolver_noop,
        ).build()
        # Step's wiring: text from FromInput
        step_wiring = spec.nodes[0].wiring
        assert "text" in step_wiring.field_sources
        assert step_wiring.field_sources["text"].kind == "from_input"
        assert step_wiring.field_sources["text"].path == "text"

        # Extraction's wiring: label from FromOutput, run_id from FromPipeline
        ex_wiring = spec.nodes[1].wiring
        assert ex_wiring.field_sources["label"].kind == "from_output"
        assert ex_wiring.field_sources["label"].step_cls == "_ClassifyStep"
        assert ex_wiring.field_sources["label"].field == "label"
        assert ex_wiring.field_sources["run_id"].kind == "from_pipeline"
        assert ex_wiring.field_sources["run_id"].attr == "run_id"

    def test_edges_and_start_node(self):
        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=_resolver_noop,
        ).build()
        edge_pairs = {(e.from_node, e.to_node) for e in spec.edges}
        assert ("_ClassifyStep", "_ClassifyExtraction") in edge_pairs
        assert ("_ClassifyExtraction", "End") in edge_pairs
        # ``start_node`` is now an ArtifactRef carrying the source-side
        # Python class name. ``ref`` is None here because the test
        # uses the no-op resolver.
        assert spec.start_node is not None
        assert spec.start_node.name == "_ClassifyStep"
        assert spec.start_node.ref is None

    def test_start_node_resolves_when_resolver_matches(self):
        module = _ClassifyStep.__module__

        def resolver(m: str, s: str) -> tuple[str, str] | None:
            if m == module and s == "_ClassifyStep":
                return ("step", "_classify")
            return None

        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=resolver,
        ).build()
        assert spec.start_node is not None
        assert spec.start_node.ref is not None
        assert spec.start_node.ref.kind == "step"
        assert spec.start_node.ref.name == "_classify"

    def test_node_binding_is_artifact_field(self):
        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=_resolver_noop,
        ).build()
        # Each NodeBindingSpec carries its own issues slot
        # (binding-wrapper issues land here via _init_post_errors).
        for nb in spec.nodes:
            assert isinstance(nb, NodeBindingSpec)
            assert hasattr(nb, "issues")

    def test_round_trip_serialisation(self):
        spec = PipelineBuilder(
            name="fixture",
            cls=_FixturePipeline,
            source_path="/tmp/fixture.py",
            source_text="",
            resolver=_resolver_noop,
        ).build()
        payload = spec.model_dump(mode="json")
        re_spec = PipelineSpec.model_validate(payload)
        assert re_spec.name == spec.name
        assert len(re_spec.nodes) == len(spec.nodes)
        assert re_spec.start_node is not None
        assert re_spec.start_node.name == spec.start_node.name


# ---------------------------------------------------------------------------
# Walker integration
# ---------------------------------------------------------------------------


class TestWalkPipelinesPopulatesRegistry:
    def test_demo_pipeline_registers(self):
        from sqlalchemy import create_engine

        from llm_pipeline.discovery import (
            discover_from_convention,
            init_empty_registries,
        )

        engine = create_engine("sqlite:///:memory:")
        registries = init_empty_registries()
        discover_from_convention(
            engine, default_model=None, registries=registries,
        )
        # Demo's TextAnalyzerPipeline ends up under 'text_analyzer'.
        assert "text_analyzer" in registries[KIND_PIPELINE]
        reg = registries[KIND_PIPELINE]["text_analyzer"]
        assert isinstance(reg.spec, PipelineSpec)
        assert reg.obj is not None  # the Pipeline class
        assert len(reg.spec.nodes) == 4
        binding_kinds = [nb.binding_kind for nb in reg.spec.nodes]
        assert binding_kinds == ["step", "step", "extraction", "step"]
