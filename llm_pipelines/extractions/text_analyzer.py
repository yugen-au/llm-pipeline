"""TopicExtraction: bridges TopicExtractionStep output to Topic DB rows.

Pure contract — declares INPUTS and MODEL only. Wiring (which step's
output feeds the topics, where run_id comes from) lives on the
pipeline's ``Extraction(TopicExtraction, inputs_spec=...)`` binding.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_pipeline.graph import ExtractionNode, StepInputs

from llm_pipelines.schemas.text_analyzer import TopicItem
from llm_pipelines.tables.text_analyzer import Topic

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
