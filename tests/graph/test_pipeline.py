"""Compile-time validator coverage for ``llm_pipeline.graph.Pipeline``.

Each test declares a minimal pipeline that violates one rule and
asserts the validator surfaces a clear error at class-definition time.
"""
from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel
from pydantic_graph import End, GraphRunContext
from sqlmodel import Field, SQLModel

from llm_pipeline.graph import (
    ExtractionNode,
    FromInput,
    FromOutput,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineInputData,
    PipelineState,
    ReviewNode,
    StepInputs,
)


# ---------------------------------------------------------------------------
# Shared fixtures: minimal valid building blocks for single-node pipelines
# ---------------------------------------------------------------------------


class SmokeInput(PipelineInputData):
    text: str


class AlphaInputs(StepInputs):
    text: str


class AlphaInstructions(BaseModel):
    label: str = ""


class AlphaStep(LLMStepNode):
    INPUTS = AlphaInputs
    INSTRUCTIONS = AlphaInstructions
    inputs_spec = AlphaInputs.sources(text=FromInput("text"))

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        return End(None)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestPipelineHappyPath:
    """A minimal, valid pipeline compiles + builds a graph."""

    def test_single_step_pipeline_compiles(self):
        class HappyPipeline(Pipeline):
            INPUT_DATA = SmokeInput
            nodes = [AlphaStep]

        assert HappyPipeline.start_node is AlphaStep
        assert HappyPipeline._graph is not None
        assert "AlphaStep" in HappyPipeline._graph.node_defs

    def test_pipeline_name_derives_from_class(self):
        class HelloWorldPipeline(Pipeline):
            INPUT_DATA = SmokeInput
            nodes = [AlphaStep]

        assert HelloWorldPipeline.pipeline_name() == "hello_world"


# ---------------------------------------------------------------------------
# Naming conventions
# ---------------------------------------------------------------------------


class TestNamingConventions:
    def test_pipeline_class_must_end_with_pipeline(self):
        with pytest.raises(ValueError, match="must end with 'Pipeline' suffix"):
            class NotAPipelineSuffix(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [AlphaStep]

    def test_step_must_end_with_step(self):
        class NoSuffixInputs(StepInputs):
            text: str

        class NoSuffixInstructions(BaseModel):
            x: str = ""

        # Class name doesn't end with "Step".
        class BetaButNotS(LLMStepNode):
            INPUTS = NoSuffixInputs
            INSTRUCTIONS = NoSuffixInstructions
            inputs_spec = NoSuffixInputs.sources(text=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        with pytest.raises(ValueError, match="must end with 'Step' suffix"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [BetaButNotS]

    def test_inputs_class_name_must_match_step(self):
        class WrongName(StepInputs):
            text: str

        class GammaInstructions(BaseModel):
            x: str = ""

        class GammaStep(LLMStepNode):
            INPUTS = WrongName
            INSTRUCTIONS = GammaInstructions
            inputs_spec = WrongName.sources(text=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        with pytest.raises(ValueError, match="must be named 'GammaInputs'"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [GammaStep]


# ---------------------------------------------------------------------------
# Source-spec validation
# ---------------------------------------------------------------------------


class TestSourceSpecValidation:
    def test_from_input_unknown_path_raises(self):
        class DeltaInputs(StepInputs):
            text: str

        class DeltaInstructions(BaseModel):
            x: str = ""

        class DeltaStep(LLMStepNode):
            INPUTS = DeltaInputs
            INSTRUCTIONS = DeltaInstructions
            inputs_spec = DeltaInputs.sources(text=FromInput("nope"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        with pytest.raises(ValueError, match="not a field on SmokeInput"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [DeltaStep]

    def test_from_output_unknown_field_raises(self):
        # First step writes a known instructions class.
        class FirstInputs(StepInputs):
            text: str

        class FirstInstructions(BaseModel):
            label: str = ""

        # Second step tries to read FirstInstructions.not_a_field.
        class SecondInputs(StepInputs):
            label: str

        class SecondInstructions(BaseModel):
            x: str = ""

        class FirstStep(LLMStepNode):
            INPUTS = FirstInputs
            INSTRUCTIONS = FirstInstructions
            inputs_spec = FirstInputs.sources(text=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> SecondStep:
                return SecondStep()

        class SecondStep(LLMStepNode):
            INPUTS = SecondInputs
            INSTRUCTIONS = SecondInstructions
            inputs_spec = SecondInputs.sources(
                label=FromOutput(FirstStep, field="not_a_field"),
            )

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        with pytest.raises(ValueError, match="'not_a_field' is not a field"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [FirstStep, SecondStep]

    def test_from_output_to_downstream_step_raises(self):
        # Define the downstream step first so FromOutput(...) can reference it.
        class ZetaInputs(StepInputs):
            label: str

        class ZetaInstructions(BaseModel):
            y: str = ""

        class ZetaStep(LLMStepNode):
            INPUTS = ZetaInputs
            INSTRUCTIONS = ZetaInstructions
            inputs_spec = ZetaInputs.sources(label=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        # Reverse reads from Zeta but flows TO Zeta — the validator
        # should reject because Zeta is downstream, not upstream.
        class ReverseInputs(StepInputs):
            value: str

        class ReverseInstructions(BaseModel):
            x: str = ""

        class ReverseStep(LLMStepNode):
            INPUTS = ReverseInputs
            INSTRUCTIONS = ReverseInstructions
            inputs_spec = ReverseInputs.sources(
                value=FromOutput(ZetaStep, field="y"),
            )

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> ZetaStep:
                return ZetaStep()

        with pytest.raises(ValueError, match="not upstream"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [ReverseStep, ZetaStep]
                start_node = ReverseStep


# ---------------------------------------------------------------------------
# Extraction validation
# ---------------------------------------------------------------------------


class _SmokeWidget(SQLModel, table=True):
    __tablename__ = "test_smoke_widgets"
    __table_args__ = {"extend_existing": True}
    id: int | None = Field(default=None, primary_key=True)
    name: str


class TestExtractionValidation:
    def test_extraction_with_upstream_source_step_compiles(self):
        # Step1 → Extraction1 → End. Extraction reads Step1.label.
        class HappyInputs(StepInputs):
            text: str

        class HappyInstructions(BaseModel):
            label: str = ""

        class HappyStep(LLMStepNode):
            INPUTS = HappyInputs
            INSTRUCTIONS = HappyInstructions
            inputs_spec = HappyInputs.sources(text=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> HappyExtraction:
                return HappyExtraction()

        class FromHappyInputs(StepInputs):
            label: str

        class HappyExtraction(ExtractionNode):
            MODEL = _SmokeWidget
            INPUTS = FromHappyInputs
            source_step = HappyStep
            inputs_spec = FromHappyInputs.sources(
                label=FromOutput(HappyStep, field="label"),
            )

            def extract(self, inputs):
                return [_SmokeWidget(name=inputs.label)]

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        class HappyExtractionPipeline(Pipeline):
            INPUT_DATA = SmokeInput
            nodes = [HappyStep, HappyExtraction]

        assert "HappyExtraction" in HappyExtractionPipeline._graph.node_defs

    def test_extraction_must_end_with_extraction(self):
        class XInputs(StepInputs):
            text: str

        class XInstructions(BaseModel):
            label: str = ""

        class XStep(LLMStepNode):
            INPUTS = XInputs
            INSTRUCTIONS = XInstructions
            inputs_spec = XInputs.sources(text=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> NotExtNode:
                return NotExtNode()

        class FromXInputs(StepInputs):
            label: str

        # Wrong: doesn't end with "Extraction".
        class NotExtNode(ExtractionNode):
            MODEL = _SmokeWidget
            INPUTS = FromXInputs
            source_step = XStep
            inputs_spec = FromXInputs.sources(
                label=FromOutput(XStep, field="label"),
            )

            def extract(self, inputs):
                return []

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        with pytest.raises(ValueError, match="must end with 'Extraction' suffix"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [XStep, NotExtNode]

    def test_extraction_source_step_must_be_upstream(self):
        # Build a pipeline where the extraction's source_step is downstream.
        class DownstreamInputs(StepInputs):
            text: str

        class DownstreamInstructions(BaseModel):
            label: str = ""

        class DownstreamStep(LLMStepNode):
            INPUTS = DownstreamInputs
            INSTRUCTIONS = DownstreamInstructions
            inputs_spec = DownstreamInputs.sources(text=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        class BadFromInputs(StepInputs):
            label: str

        class BadExtraction(ExtractionNode):
            MODEL = _SmokeWidget
            INPUTS = BadFromInputs
            source_step = DownstreamStep
            inputs_spec = BadFromInputs.sources(
                label=FromOutput(DownstreamStep, field="label"),
            )

            def extract(self, inputs):
                return []

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> DownstreamStep:
                return DownstreamStep()

        with pytest.raises(ValueError, match="not upstream"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [BadExtraction, DownstreamStep]
                start_node = BadExtraction


# ---------------------------------------------------------------------------
# Review validation
# ---------------------------------------------------------------------------


class TestReviewValidation:
    def test_review_with_upstream_target_compiles(self):
        class FlowInputs(StepInputs):
            text: str

        class FlowInstructions(BaseModel):
            label: str = ""

        class FlowStep(LLMStepNode):
            INPUTS = FlowInputs
            INSTRUCTIONS = FlowInstructions
            inputs_spec = FlowInputs.sources(text=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> FlowReview:
                return FlowReview()

        class FlowReview(ReviewNode):
            target_step = FlowStep

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        class HappyReviewPipeline(Pipeline):
            INPUT_DATA = SmokeInput
            nodes = [FlowStep, FlowReview]

        assert "FlowReview" in HappyReviewPipeline._graph.node_defs

    def test_review_target_step_must_be_upstream(self):
        class DangleInputs(StepInputs):
            text: str

        class DangleInstructions(BaseModel):
            x: str = ""

        class DangleStep(LLMStepNode):
            INPUTS = DangleInputs
            INSTRUCTIONS = DangleInstructions
            inputs_spec = DangleInputs.sources(text=FromInput("text"))

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> End[None]:
                return End(None)

        class DangleReview(ReviewNode):
            target_step = DangleStep

            async def run(
                self, ctx: GraphRunContext[PipelineState, PipelineDeps],
            ) -> DangleStep:
                return DangleStep()

        with pytest.raises(ValueError, match="not upstream"):
            class BadPipeline(Pipeline):
                INPUT_DATA = SmokeInput
                nodes = [DangleReview, DangleStep]
                start_node = DangleReview
