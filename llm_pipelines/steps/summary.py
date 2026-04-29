"""Summary step (pydantic-graph-native node)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import End

from llm_pipeline.graph import FromInput, FromOutput, LLMStepNode

from llm_pipelines.schemas.text_analyzer import (
    SummaryInputs,
    SummaryInstructions,
)
from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
from llm_pipelines.steps.topic_extraction import TopicExtractionStep

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState


class SummaryStep(LLMStepNode):
    """Produce a summary incorporating sentiment and topic context."""

    INPUTS = SummaryInputs
    INSTRUCTIONS = SummaryInstructions
    inputs_spec = SummaryInputs.sources(
        text=FromInput("text"),
        sentiment=FromOutput(SentimentAnalysisStep, field="sentiment"),
        primary_topic=FromOutput(TopicExtractionStep, field="primary_topic"),
    )

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_llm(ctx)
        return End(None)
