"""Summary step (pydantic-graph-native node).

INPUTS and INSTRUCTIONS classes live alongside the step (same
file) — they're 1:1-paired with this step.
"""
from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from pydantic_graph import End

from llm_pipeline.graph import LLMResultMixin, LLMStepNode
from llm_pipeline.inputs import StepInputs

from llm_pipelines._variables._summary import SummaryPrompt

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState


class SummaryInputs(StepInputs):
    """Everything SummaryStep needs to run."""
    text: str
    sentiment: str
    primary_topic: str


class SummaryInstructions(LLMResultMixin):
    """Structured output for text summarization."""
    summary: str = ""
    example: ClassVar[dict] = {
        "summary": "The text discusses key themes and their implications.",
        "confidence_score": 0.88,
    }


class SummaryStep(LLMStepNode):
    """Produce a summary incorporating sentiment and topic context."""

    INPUTS = SummaryInputs
    INSTRUCTIONS = SummaryInstructions
    DEFAULT_TOOLS: list[type] = []

    def prepare(self, inputs: SummaryInputs) -> list[SummaryPrompt]:
        return [SummaryPrompt(
            text=inputs.text,
            sentiment=inputs.sentiment,
            primary_topic=inputs.primary_topic,
        )]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> End[None]:
        await self._run_llm(ctx)
        return End(None)
