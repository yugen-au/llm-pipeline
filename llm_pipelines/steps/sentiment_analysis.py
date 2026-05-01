"""Sentiment analysis step (pydantic-graph-native node).

Pure contract: declares INPUTS, INSTRUCTIONS, DEFAULT_TOOLS, and a
``prepare()`` method. Wiring (where the inputs come from) lives in
the pipeline's ``Step(SentimentAnalysisStep, inputs_spec=...)`` binding.

INPUTS and INSTRUCTIONS classes live alongside the step class
(same file) — they're 1:1-paired with this step and aren't shared
with any other artifact, so co-locating them keeps ownership
obvious to readers and to the discovery walkers.
"""
from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from llm_pipeline.graph import LLMResultMixin, LLMStepNode
from llm_pipeline.inputs import StepInputs

from llm_pipelines._variables._sentiment_analysis import SentimentAnalysisPrompt

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState

    from llm_pipelines.steps.topic_extraction import TopicExtractionStep


class SentimentAnalysisInputs(StepInputs):
    """Everything SentimentAnalysisStep needs to run."""
    text: str


class SentimentAnalysisInstructions(LLMResultMixin):
    """Structured output for sentiment analysis."""
    sentiment: str = ""
    explanation: str = ""
    example: ClassVar[dict] = {
        "sentiment": "positive",
        "explanation": "The text expresses optimism and satisfaction.",
        "confidence_score": 0.92,
    }


class SentimentAnalysisStep(LLMStepNode):
    """Analyse sentiment of the input text."""

    INPUTS = SentimentAnalysisInputs
    INSTRUCTIONS = SentimentAnalysisInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: SentimentAnalysisInputs) -> list[SentimentAnalysisPrompt]:
        return [SentimentAnalysisPrompt(text=inputs.text)]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> TopicExtractionStep:
        await self._run_llm(ctx)
        from llm_pipelines.steps.topic_extraction import TopicExtractionStep

        return TopicExtractionStep()
