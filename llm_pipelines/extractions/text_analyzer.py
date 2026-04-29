"""TopicExtraction: bridges TopicExtractionStep output to Topic DB rows.

Sibling node in the pipeline graph (no longer nested under a step's
``Bind``). Reads ``topics`` from ``TopicExtractionStep`` output and
``run_id`` from ambient ``PipelineDeps``; persists ``Topic`` rows.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_pipeline.graph import (
    ExtractionNode,
    FromOutput,
    FromPipeline,
    StepInputs,
)

from llm_pipelines.schemas.text_analyzer import (
    Topic,
    TopicItem,
)
from llm_pipelines.steps.topic_extraction import TopicExtractionStep

if TYPE_CHECKING:
    from pydantic_graph import GraphRunContext

    from llm_pipeline.graph import PipelineDeps, PipelineState

    from llm_pipelines.steps.summary import SummaryStep


class FromTopicExtractionInputs(StepInputs):
    """Pathway inputs for ``TopicExtraction``."""

    topics: list[TopicItem]
    run_id: str


class TopicExtraction(ExtractionNode):
    """Convert ``TopicItem`` outputs from the topic-extraction step into ``Topic`` rows."""

    MODEL = Topic
    INPUTS = FromTopicExtractionInputs
    source_step = TopicExtractionStep
    inputs_spec = FromTopicExtractionInputs.sources(
        topics=FromOutput(TopicExtractionStep, field="topics"),
        run_id=FromPipeline("run_id"),
    )

    def extract(self, inputs: FromTopicExtractionInputs) -> list[Topic]:
        return [
            Topic(name=t.name, relevance=t.relevance, run_id=inputs.run_id)
            for t in inputs.topics
        ]

    async def run(
        self, ctx: GraphRunContext[PipelineState, PipelineDeps],
    ) -> SummaryStep:
        await self._run_extraction(ctx)
        from llm_pipelines.steps.summary import SummaryStep

        return SummaryStep()
