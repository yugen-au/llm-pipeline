"""Compile-time validator coverage for ``llm_pipeline.graph.Pipeline``.

Each test declares a minimal pipeline that violates one rule and
asserts the validator surfaces a clear error at class-definition time.

All fixtures (Inputs / Instructions / PromptVariables / Step / Extraction /
Review classes) live at module top level — the strict ``prepare()``
validator at ``LLMStepNode.__init_subclass__`` resolves the full
signature, so referenced types must be in module scope. This mirrors
how real step files are authored.
"""
from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel, Field
from pydantic_graph import End, GraphRunContext
from sqlmodel import Field as SQLField, SQLModel

from llm_pipeline.graph import (
    Extraction,
    ExtractionNode,
    FromInput,
    FromOutput,
    LLMResultMixin,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    Review,
    ReviewNode,
    Step,
    StepInputs,
)
from llm_pipeline.prompts import PromptVariables


# ---------------------------------------------------------------------------
# Shared input + happy-path step
# ---------------------------------------------------------------------------


class SmokeInput(PipelineInputData):
    text: str


class AlphaInputs(StepInputs):
    text: str


class AlphaInstructions(LLMResultMixin):
    label: str = ""


class AlphaPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class AlphaStep(LLMStepNode):
    INPUTS = AlphaInputs
    INSTRUCTIONS = AlphaInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: AlphaInputs) -> list[AlphaPrompt]:
        return [AlphaPrompt(
            system=AlphaPrompt.system(),
            user=AlphaPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


def _alpha_step_binding() -> Step:
    return Step(AlphaStep, inputs_spec=AlphaInputs.sources(text=FromInput("text")))


# ---------------------------------------------------------------------------
# Fixtures: step missing the "Step" suffix
# ---------------------------------------------------------------------------


class NoSuffixInputs(StepInputs):
    text: str


class NoSuffixInstructions(LLMResultMixin):
    x: str = ""


class NoSuffixPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class BetaButNotS(LLMStepNode):
    INPUTS = NoSuffixInputs
    INSTRUCTIONS = NoSuffixInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: NoSuffixInputs) -> list[NoSuffixPrompt]:
        return [NoSuffixPrompt(
            system=NoSuffixPrompt.system(),
            user=NoSuffixPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# ---------------------------------------------------------------------------
# Fixtures: inputs class name doesn't match step
# ---------------------------------------------------------------------------


class WrongName(StepInputs):
    text: str


class GammaInstructions(LLMResultMixin):
    x: str = ""


class GammaPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class GammaStep(LLMStepNode):
    INPUTS = WrongName
    INSTRUCTIONS = GammaInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: WrongName) -> list[GammaPrompt]:
        return [GammaPrompt(
            system=GammaPrompt.system(),
            user=GammaPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# ---------------------------------------------------------------------------
# Fixtures: FromInput unknown path
# ---------------------------------------------------------------------------


class DeltaInputs(StepInputs):
    text: str


class DeltaInstructions(LLMResultMixin):
    x: str = ""


class DeltaPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class DeltaStep(LLMStepNode):
    INPUTS = DeltaInputs
    INSTRUCTIONS = DeltaInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: DeltaInputs) -> list[DeltaPrompt]:
        return [DeltaPrompt(
            system=DeltaPrompt.system(),
            user=DeltaPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# ---------------------------------------------------------------------------
# Fixtures: FromOutput unknown field
# ---------------------------------------------------------------------------


class FirstInputs(StepInputs):
    text: str


class FirstInstructions(LLMResultMixin):
    label: str = ""


class FirstPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class SecondInputs(StepInputs):
    label: str


class SecondInstructions(LLMResultMixin):
    x: str = ""


class SecondPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        label: str = Field(description="label")


class FirstStep(LLMStepNode):
    INPUTS = FirstInputs
    INSTRUCTIONS = FirstInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: FirstInputs) -> list[FirstPrompt]:
        return [FirstPrompt(
            system=FirstPrompt.system(),
            user=FirstPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> SecondStep:
        return SecondStep()


class SecondStep(LLMStepNode):
    INPUTS = SecondInputs
    INSTRUCTIONS = SecondInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: SecondInputs) -> list[SecondPrompt]:
        return [SecondPrompt(
            system=SecondPrompt.system(),
            user=SecondPrompt.user(label=inputs.label),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# ---------------------------------------------------------------------------
# Fixtures: FromOutput pointing at a downstream step (cycle/order check)
# ---------------------------------------------------------------------------


class ZetaInputs(StepInputs):
    label: str


class ZetaInstructions(LLMResultMixin):
    y: str = ""


class ZetaPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        label: str = Field(description="label")


class ZetaStep(LLMStepNode):
    INPUTS = ZetaInputs
    INSTRUCTIONS = ZetaInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: ZetaInputs) -> list[ZetaPrompt]:
        return [ZetaPrompt(
            system=ZetaPrompt.system(),
            user=ZetaPrompt.user(label=inputs.label),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


class ReverseInputs(StepInputs):
    value: str


class ReverseInstructions(LLMResultMixin):
    x: str = ""


class ReversePrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        value: str = Field(description="value")


class ReverseStep(LLMStepNode):
    INPUTS = ReverseInputs
    INSTRUCTIONS = ReverseInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: ReverseInputs) -> list[ReversePrompt]:
        return [ReversePrompt(
            system=ReversePrompt.system(),
            user=ReversePrompt.user(value=inputs.value),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> ZetaStep:
        return ZetaStep()


# ---------------------------------------------------------------------------
# Fixtures: extraction with upstream source (happy path)
# ---------------------------------------------------------------------------


class _SmokeWidget(SQLModel, table=True):
    __tablename__ = "test_smoke_widgets"
    __table_args__ = {"extend_existing": True}
    id: int | None = SQLField(default=None, primary_key=True)
    name: str


class HappyInputs(StepInputs):
    text: str


class HappyInstructions(LLMResultMixin):
    label: str = ""


class HappyPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class HappyStep(LLMStepNode):
    INPUTS = HappyInputs
    INSTRUCTIONS = HappyInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: HappyInputs) -> list[HappyPrompt]:
        return [HappyPrompt(
            system=HappyPrompt.system(),
            user=HappyPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> HappyExtraction:
        return HappyExtraction()


class FromHappyInputs(StepInputs):
    label: str


class HappyExtraction(ExtractionNode):
    MODEL = _SmokeWidget
    INPUTS = FromHappyInputs

    def extract(self, inputs: FromHappyInputs) -> list[_SmokeWidget]:
        return [_SmokeWidget(name=inputs.label)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# ---------------------------------------------------------------------------
# Fixtures: extraction class missing the "Extraction" suffix
# ---------------------------------------------------------------------------


class XInputs(StepInputs):
    text: str


class XInstructions(LLMResultMixin):
    label: str = ""


class XPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class XStep(LLMStepNode):
    INPUTS = XInputs
    INSTRUCTIONS = XInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: XInputs) -> list[XPrompt]:
        return [XPrompt(
            system=XPrompt.system(),
            user=XPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> NotExtNode:
        return NotExtNode()


class FromXInputs(StepInputs):
    label: str


class NotExtNode(ExtractionNode):
    """Wrong: doesn't end with 'Extraction'."""

    MODEL = _SmokeWidget
    INPUTS = FromXInputs

    def extract(self, inputs: FromXInputs) -> list[_SmokeWidget]:
        return []

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# ---------------------------------------------------------------------------
# Fixtures: extraction reads a downstream step (rejected by upstream check)
# ---------------------------------------------------------------------------


class DownstreamInputs(StepInputs):
    text: str


class DownstreamInstructions(LLMResultMixin):
    label: str = ""


class DownstreamPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class DownstreamStep(LLMStepNode):
    INPUTS = DownstreamInputs
    INSTRUCTIONS = DownstreamInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: DownstreamInputs) -> list[DownstreamPrompt]:
        return [DownstreamPrompt(
            system=DownstreamPrompt.system(),
            user=DownstreamPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


class BadFromInputs(StepInputs):
    label: str


class BadExtraction(ExtractionNode):
    MODEL = _SmokeWidget
    INPUTS = BadFromInputs

    def extract(self, inputs: BadFromInputs) -> list[_SmokeWidget]:
        return []

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> DownstreamStep:
        return DownstreamStep()


# ---------------------------------------------------------------------------
# Fixtures: review with an upstream input (happy path)
# ---------------------------------------------------------------------------


class _ReviewerResponse(BaseModel):
    approved: bool = True


class FlowInputs(StepInputs):
    text: str


class FlowInstructions(LLMResultMixin):
    label: str = ""


class FlowPrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class FlowStep(LLMStepNode):
    INPUTS = FlowInputs
    INSTRUCTIONS = FlowInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: FlowInputs) -> list[FlowPrompt]:
        return [FlowPrompt(
            system=FlowPrompt.system(),
            user=FlowPrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> FlowReview:
        return FlowReview()


class FlowReviewInputs(StepInputs):
    label: str


class FlowReview(ReviewNode):
    INPUTS = FlowReviewInputs
    OUTPUT = _ReviewerResponse

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# ---------------------------------------------------------------------------
# Fixtures: review reads a downstream step (rejected by upstream check)
# ---------------------------------------------------------------------------


class DangleInputs(StepInputs):
    text: str


class DangleInstructions(LLMResultMixin):
    x: str = ""


class DanglePrompt(PromptVariables):
    class system(BaseModel):
        pass

    class user(BaseModel):
        text: str = Field(description="text")


class DangleStep(LLMStepNode):
    INPUTS = DangleInputs
    INSTRUCTIONS = DangleInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: DangleInputs) -> list[DanglePrompt]:
        return [DanglePrompt(
            system=DanglePrompt.system(),
            user=DanglePrompt.user(text=inputs.text),
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


class DangleReviewInputs(StepInputs):
    x: str


class DangleReview(ReviewNode):
    INPUTS = DangleReviewInputs
    OUTPUT = _ReviewerResponse

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> DangleStep:
        return DangleStep()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineHappyPath:
    """A minimal, valid pipeline compiles + builds a graph."""

    def test_single_step_pipeline_compiles(self):
        class HappyPipeline(Pipeline):
            INPUT_DATA = SmokeInput
            nodes = [_alpha_step_binding()]

        assert HappyPipeline.start_node is AlphaStep
        assert HappyPipeline._graph is not None
        assert "AlphaStep" in HappyPipeline._graph.node_defs

    def test_pipeline_name_derives_from_class(self):
        class HelloWorldPipeline(Pipeline):
            INPUT_DATA = SmokeInput
            nodes = [_alpha_step_binding()]

        assert HelloWorldPipeline.pipeline_name() == "hello_world"


class TestNamingConventions:
    def test_pipeline_class_must_end_with_pipeline(self):
        with pytest.raises(ValueError, match="must end with 'Pipeline' suffix"):
            class NotAPipelineSuffix(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [_alpha_step_binding()]

    def test_step_must_end_with_step(self):
        with pytest.raises(ValueError, match="must end with 'Step' suffix"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [Step(
                    BetaButNotS,
                    inputs_spec=NoSuffixInputs.sources(text=FromInput("text")),
                )]

    def test_inputs_class_name_must_match_step(self):
        with pytest.raises(ValueError, match="must be named 'GammaInputs'"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [Step(
                    GammaStep,
                    inputs_spec=WrongName.sources(text=FromInput("text")),
                )]


class TestSourceSpecValidation:
    def test_from_input_unknown_path_raises(self):
        with pytest.raises(ValueError, match="not a field on SmokeInput"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [Step(
                    DeltaStep,
                    inputs_spec=DeltaInputs.sources(text=FromInput("nope")),
                )]

    def test_from_output_unknown_field_raises(self):
        with pytest.raises(ValueError, match="'not_a_field' is not a field"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [
                    Step(FirstStep, inputs_spec=FirstInputs.sources(
                        text=FromInput("text"),
                    )),
                    Step(SecondStep, inputs_spec=SecondInputs.sources(
                        label=FromOutput(FirstStep, field="not_a_field"),
                    )),
                ]

    def test_from_output_to_downstream_step_raises(self):
        with pytest.raises(ValueError, match="not upstream"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [
                    Step(ReverseStep, inputs_spec=ReverseInputs.sources(
                        value=FromOutput(ZetaStep, field="y"),
                    )),
                    Step(ZetaStep, inputs_spec=ZetaInputs.sources(
                        label=FromInput("text"),
                    )),
                ]
                start_node = ReverseStep


class TestExtractionValidation:
    def test_extraction_with_upstream_source_compiles(self):
        class HappyExtractionPipeline(Pipeline):
            INPUT_DATA = SmokeInput
            nodes = [
                Step(HappyStep, inputs_spec=HappyInputs.sources(
                    text=FromInput("text"),
                )),
                Extraction(HappyExtraction, inputs_spec=FromHappyInputs.sources(
                    label=FromOutput(HappyStep, field="label"),
                )),
            ]

        assert "HappyExtraction" in HappyExtractionPipeline._graph.node_defs

    def test_extraction_must_end_with_extraction(self):
        with pytest.raises(ValueError, match="must end with 'Extraction' suffix"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [
                    Step(XStep, inputs_spec=XInputs.sources(
                        text=FromInput("text"),
                    )),
                    Extraction(NotExtNode, inputs_spec=FromXInputs.sources(
                        label=FromOutput(XStep, field="label"),
                    )),
                ]

    def test_extraction_reading_downstream_step_raises(self):
        with pytest.raises(ValueError, match="not upstream"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [
                    Extraction(BadExtraction, inputs_spec=BadFromInputs.sources(
                        label=FromOutput(DownstreamStep, field="label"),
                    )),
                    Step(DownstreamStep, inputs_spec=DownstreamInputs.sources(
                        text=FromInput("text"),
                    )),
                ]
                start_node = BadExtraction


class TestReviewValidation:
    def test_review_with_upstream_input_compiles(self):
        class HappyReviewPipeline(Pipeline):
            INPUT_DATA = SmokeInput
            nodes = [
                Step(FlowStep, inputs_spec=FlowInputs.sources(
                    text=FromInput("text"),
                )),
                Review(FlowReview, inputs_spec=FlowReviewInputs.sources(
                    label=FromOutput(FlowStep, field="label"),
                )),
            ]

        assert "FlowReview" in HappyReviewPipeline._graph.node_defs

    def test_review_reading_downstream_step_raises(self):
        with pytest.raises(ValueError, match="not upstream"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [
                    Review(DangleReview, inputs_spec=DangleReviewInputs.sources(
                        x=FromOutput(DangleStep, field="x"),
                    )),
                    Step(DangleStep, inputs_spec=DangleInputs.sources(
                        text=FromInput("text"),
                    )),
                ]
                start_node = DangleReview
