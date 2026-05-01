"""Topic extraction step (pydantic-graph-native node).

INPUTS and INSTRUCTIONS classes live alongside the step (same
file) — they're 1:1-paired with this step. ``TopicItem`` stays
in ``schemas/`` because it's a genuinely shared shape (used here
in the instructions AND by the downstream extraction's pathway
inputs).
"""
from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from llm_pipeline.graph import LLMResultMixin, LLMStepNode
from llm_pipeline.inputs import StepInputs

from llm_pipelines._variables._topic_extraction import TopicExtractionPrompt
from llm_pipelines.schemas.text_analyzer import TopicItem

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState

    from llm_pipelines.extractions.text_analyzer import TopicExtraction


class TopicExtractionInputs(StepInputs):
    """Everything TopicExtractionStep needs to run."""
    text: str
    sentiment: str


class TopicExtractionInstructions(LLMResultMixin):
    """Structured output for topic extraction."""
    topics: list[TopicItem] = []
    primary_topic: str = ""
    example: ClassVar[dict] = {
        "topics": [
            {"name": "machine learning", "relevance": 0.95},
            {"name": "data processing", "relevance": 0.7},
        ],
        "primary_topic": "machine learning",
        "confidence_score": 0.9,
    }


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
