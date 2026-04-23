"""TextAnalyzer extraction: bridges LLM output to DB records."""
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.inputs import StepInputs

from llm_pipelines.schemas.text_analyzer import (
    Topic,
    TopicItem,
)


class TopicExtraction(PipelineExtraction, model=Topic):
    """Bridges TopicItem LLM output to Topic DB records.

    Single pathway: ``FromTopicExtractionInputs``. The strategy wires
    ``topics`` from the TopicExtractionStep output and ``run_id`` from
    the ambient pipeline.
    """

    class FromTopicExtractionInputs(StepInputs):
        topics: list[TopicItem]
        run_id: str

    def from_topic_extraction(
        self, inputs: FromTopicExtractionInputs
    ) -> list[Topic]:
        return [
            Topic(
                name=t.name,
                relevance=t.relevance,
                run_id=inputs.run_id,
            )
            for t in inputs.topics
        ]
