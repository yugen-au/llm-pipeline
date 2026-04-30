"""Summary step (pydantic-graph-native node)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic_graph import End

from llm_pipeline.graph import LLMStepNode

from llm_pipelines.schemas.text_analyzer import (
    SummaryInputs,
    SummaryInstructions,
)
from llm_pipelines.variables.summary import SummaryPrompt

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState


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
