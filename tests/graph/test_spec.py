"""Tests for ``Pipeline.inspect()`` + ``PipelineSpec`` builder."""
from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_graph import End, GraphRunContext
from sqlmodel import Field as SQLField, SQLModel

from llm_pipeline.graph import (
    EdgeSpec,
    Extraction,
    ExtractionNode,
    FromInput,
    FromOutput,
    FromPipeline,
    LLMResultMixin,
    LLMStepNode,
    NodeSpec,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineSpec,
    PipelineState,
    Step,
    StepInputs,
)
from llm_pipeline.prompts import PromptVariables


# ---------------------------------------------------------------------------
# Module-level fixtures (strict prepare validator requires module scope)
# ---------------------------------------------------------------------------


class _SpecInput(PipelineInputData):
    text: str


class _SpecAInputs(StepInputs):
    text: str


class _SpecAInstructions(LLMResultMixin):
    label: str = ""


class _SpecAPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class _SpecRow(SQLModel, table=True):
    __tablename__ = "test_spec_rows"
    __table_args__ = {"extend_existing": True}
    id: int | None = SQLField(default=None, primary_key=True)
    name: str


class _FromSpecAInputs(StepInputs):
    label: str
    run_id: str


class _SpecAStep(LLMStepNode):
    """Step → Extraction. Flows into _SpecAExtraction."""

    INPUTS = _SpecAInputs
    INSTRUCTIONS = _SpecAInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _SpecAInputs) -> list[_SpecAPrompt]:
        return [_SpecAPrompt(
            system=_SpecAPrompt.system(),
            user=_SpecAPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> _SpecAExtraction:
        await self._run_llm(ctx)
        return _SpecAExtraction()


class _SpecAExtraction(ExtractionNode):
    """Extraction → SpecBStep. Persists row + flows to summary step."""

    MODEL = _SpecRow
    INPUTS = _FromSpecAInputs

    def extract(self, inputs: _FromSpecAInputs) -> list[_SpecRow]:
        return [_SpecRow(name=inputs.label)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> _SpecBStep:
        await self._run_extraction(ctx)
        return _SpecBStep()


class _SpecBInputs(StepInputs):
    label: str


class _SpecBInstructions(LLMResultMixin):
    summary: str = ""


class _SpecBPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        label: str = Field(description="label")


class _SpecBStep(LLMStepNode):
    """Step → End."""

    INPUTS = _SpecBInputs
    INSTRUCTIONS = _SpecBInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: _SpecBInputs) -> list[_SpecBPrompt]:
        return [_SpecBPrompt(
            system=_SpecBPrompt.system(),
            user=_SpecBPrompt.user(label=inputs.label),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_llm(ctx)
        return End(None)


class _SpecPipeline(Pipeline):
    """SpecAStep → SpecAExtraction → SpecBStep → End."""

    INPUT_DATA = _SpecInput
    nodes = [
        Step(_SpecAStep, inputs_spec=_SpecAInputs.sources(
            text=FromInput("text"),
        )),
        Extraction(_SpecAExtraction, inputs_spec=_FromSpecAInputs.sources(
            label=FromOutput(_SpecAStep, field="label"),
            run_id=FromPipeline("run_id"),
        )),
        Step(_SpecBStep, inputs_spec=_SpecBInputs.sources(
            label=FromOutput(_SpecAStep, field="label"),
        )),
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineInspect:
    def test_returns_pipeline_spec(self):
        spec = _SpecPipeline.inspect()
        assert isinstance(spec, PipelineSpec)

    def test_pipeline_metadata(self):
        spec = _SpecPipeline.inspect()
        assert spec.name == "_spec"
        assert spec.cls.endswith("_SpecPipeline")
        assert spec.start_node == "_SpecAStep"

    def test_input_data_schema_present(self):
        spec = _SpecPipeline.inspect()
        assert spec.input_data_schema is not None
        assert "text" in spec.input_data_schema.get("properties", {})


class TestNodeSpecs:
    def test_node_count_matches_bindings(self):
        spec = _SpecPipeline.inspect()
        assert len(spec.nodes) == 3
        assert {n.kind for n in spec.nodes} == {"step", "extraction"}

    def test_step_node_spec(self):
        spec = _SpecPipeline.inspect()
        node = next(n for n in spec.nodes if n.cls.endswith("_SpecAStep"))
        assert node.kind == "step"
        assert node.name == "_spec_a"
        assert "text" in node.inputs_schema.get("properties", {})
        assert "label" in node.output_schema.get("properties", {})
        assert node.prompt is not None
        assert node.prompt.name == "_spec_a"
        assert node.prompt.prompt_variables_cls.endswith("_SpecAPrompt")
        # Phoenix-aware fields placeholder until discovery-time validator
        assert node.prompt.system_template is None
        assert node.prompt.user_template is None
        assert node.prompt.model is None

    def test_step_node_prompt_variable_definitions(self):
        spec = _SpecPipeline.inspect()
        node = next(n for n in spec.nodes if n.cls.endswith("_SpecAStep"))
        assert node.prompt is not None
        # System has no fields; user has 'text'.
        assert node.prompt.system_variable_definitions.get("properties", {}) == {}
        user_props = node.prompt.user_variable_definitions.get("properties", {})
        assert "text" in user_props

    def test_step_node_response_format_from_instructions(self):
        spec = _SpecPipeline.inspect()
        node = next(n for n in spec.nodes if n.cls.endswith("_SpecAStep"))
        assert node.prompt is not None
        # response_format mirrors INSTRUCTIONS.model_json_schema().
        assert "label" in node.prompt.response_format.get("properties", {})

    def test_extraction_node_spec(self):
        spec = _SpecPipeline.inspect()
        node = next(n for n in spec.nodes if n.kind == "extraction")
        assert node.name == "_spec_a"
        assert node.cls.endswith("_SpecAExtraction")
        assert "label" in node.inputs_schema.get("properties", {})
        assert node.prompt is None  # only steps have prompts


class TestWiringSpecs:
    def test_from_input_serialised(self):
        spec = _SpecPipeline.inspect()
        node = next(n for n in spec.nodes if n.cls.endswith("_SpecAStep"))
        text_source = node.wiring.field_sources["text"]
        assert text_source.kind == "from_input"
        assert text_source.path == "text"

    def test_from_output_serialised(self):
        spec = _SpecPipeline.inspect()
        node = next(n for n in spec.nodes if n.cls.endswith("_SpecBStep"))
        label_source = node.wiring.field_sources["label"]
        assert label_source.kind == "from_output"
        assert label_source.step_cls == "_SpecAStep"
        assert label_source.field == "label"

    def test_from_pipeline_serialised(self):
        spec = _SpecPipeline.inspect()
        ext_node = next(n for n in spec.nodes if n.kind == "extraction")
        run_id_source = ext_node.wiring.field_sources["run_id"]
        assert run_id_source.kind == "from_pipeline"
        assert run_id_source.attr == "run_id"

    def test_inputs_cls_qualified(self):
        spec = _SpecPipeline.inspect()
        node = next(n for n in spec.nodes if n.cls.endswith("_SpecAStep"))
        assert node.wiring.inputs_cls.endswith("_SpecAInputs")


class TestEdges:
    def test_step_to_extraction_edge(self):
        spec = _SpecPipeline.inspect()
        edges = {(e.from_node, e.to_node) for e in spec.edges}
        assert ("_SpecAStep", "_SpecAExtraction") in edges

    def test_extraction_to_step_edge(self):
        spec = _SpecPipeline.inspect()
        edges = {(e.from_node, e.to_node) for e in spec.edges}
        assert ("_SpecAExtraction", "_SpecBStep") in edges

    def test_terminal_step_has_end_edge(self):
        spec = _SpecPipeline.inspect()
        edges = {(e.from_node, e.to_node) for e in spec.edges}
        assert ("_SpecBStep", "End") in edges


class TestSpecCachedAtInitSubclass:
    def test_inspect_returns_same_instance(self):
        spec_a = _SpecPipeline.inspect()
        spec_b = _SpecPipeline.inspect()
        assert spec_a is spec_b

    def test_serialisable_to_json(self):
        spec = _SpecPipeline.inspect()
        payload = spec.model_dump(mode="json")
        assert isinstance(payload, dict)
        assert payload["name"] == "_spec"
        assert isinstance(payload["nodes"], list)

        # Round-trip back through Pydantic.
        re_spec = PipelineSpec.model_validate(payload)
        assert re_spec.name == spec.name
        assert len(re_spec.nodes) == len(spec.nodes)
