"""Sentiment analysis step (pydantic-graph-native node).

Pure contract: declares INPUTS, INSTRUCTIONS, DEFAULT_TOOLS, and a
``prepare()`` method. Wiring (where the inputs come from) lives in
the pipeline's ``Step(SentimentAnalysisStep, inputs_spec=...)`` binding.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_pipeline.graph import LLMStepNode

from llm_pipelines.schemas.text_analyzer import (
    SentimentAnalysisInputs,
    SentimentAnalysisInstructions,
)
from llm_pipelines.variables.sentiment_analysis import SentimentAnalysisPrompt

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState

    from llm_pipelines.steps.topic_extraction import TopicExtractionStep


class SentimentAnalysisStep(LLMStepNode):
    """Analyse sentiment of the input text."""

    INPUTS = SentimentAnalysisInputs
    INSTRUCTIONS = SentimentAnalysisInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: SentimentAnalysisInputs) -> list[SentimentAnalysisPrompt]:
        return [
            SentimentAnalysisPrompt(
                system=SentimentAnalysisPrompt.system(),
                user=SentimentAnalysisPrompt.user(text=inputs.text),
            ),
        ]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> TopicExtractionStep:
        await self._run_llm(ctx)
        from llm_pipelines.steps.topic_extraction import TopicExtractionStep

        return TopicExtractionStep()
