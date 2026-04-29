"""Topic extraction step (pydantic-graph-native node)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_pipeline.graph import FromInput, FromOutput, LLMStepNode

from llm_pipelines.schemas.text_analyzer import (
    TopicExtractionInputs,
    TopicExtractionInstructions,
)
from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState

    from llm_pipelines.extractions.text_analyzer import TopicExtraction


class TopicExtractionStep(LLMStepNode):
    """Extract topics from the input text."""

    INPUTS = TopicExtractionInputs
    INSTRUCTIONS = TopicExtractionInstructions
    inputs_spec = TopicExtractionInputs.sources(
        text=FromInput("text"),
        sentiment=FromOutput(SentimentAnalysisStep, field="sentiment"),
    )

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> TopicExtraction:
        await self._run_llm(ctx)
        from llm_pipelines.extractions.text_analyzer import TopicExtraction

        return TopicExtraction()
