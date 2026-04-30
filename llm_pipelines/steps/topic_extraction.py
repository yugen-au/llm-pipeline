"""Topic extraction step (pydantic-graph-native node)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_pipeline.graph import LLMStepNode

from llm_pipelines.schemas.text_analyzer import (
    TopicExtractionInputs,
    TopicExtractionInstructions,
)
from llm_pipelines.variables.topic_extraction import TopicExtractionPrompt

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState

    from llm_pipelines.extractions.text_analyzer import TopicExtraction


class TopicExtractionStep(LLMStepNode):
    """Extract topics from the input text."""

    INPUTS = TopicExtractionInputs
    INSTRUCTIONS = TopicExtractionInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: TopicExtractionInputs) -> list[TopicExtractionPrompt]:
        return [TopicExtractionPrompt(
            text=inputs.text,
            sentiment=inputs.sentiment,
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> TopicExtraction:
        await self._run_llm(ctx)
        from llm_pipelines.extractions.text_analyzer import TopicExtraction

        return TopicExtraction()
