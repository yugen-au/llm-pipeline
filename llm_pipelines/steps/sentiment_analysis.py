"""Sentiment analysis step (pydantic-graph-native node).

The next-node return annotation is a forward-reference string so this
module doesn't pull in ``topic_extraction`` (which itself reads
``SentimentAnalysisInstructions`` via ``FromOutput``). pydantic-graph
resolves the string against the namespace of the module that builds
the ``Pipeline`` (``pipelines/text_analyzer.py``), where every node
class is in scope.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_pipeline.graph import FromInput, LLMStepNode

from llm_pipelines.schemas.text_analyzer import (
    SentimentAnalysisInputs,
    SentimentAnalysisInstructions,
)

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState

    from llm_pipelines.steps.topic_extraction import TopicExtractionStep


class SentimentAnalysisStep(LLMStepNode):
    """Analyse sentiment of the input text."""

    INPUTS = SentimentAnalysisInputs
    INSTRUCTIONS = SentimentAnalysisInstructions
    inputs_spec = SentimentAnalysisInputs.sources(
        text=FromInput("text"),
    )

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> TopicExtractionStep:
        await self._run_llm(ctx)
        from llm_pipelines.steps.topic_extraction import TopicExtractionStep

        return TopicExtractionStep()
