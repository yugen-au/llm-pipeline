"""TextAnalyzer extraction: bridges LLM output to DB records."""
from llm_pipeline.extraction import PipelineExtraction

from llm_pipelines.schemas.text_analyzer import (
    Topic,
    TopicExtractionInstructions,
)


class TopicExtraction(PipelineExtraction, model=Topic):
    """Bridges TopicItem LLM output to Topic DB records."""

    def default(self, results: list[TopicExtractionInstructions]) -> list[Topic]:
        return [
            Topic(
                name=t.name,
                relevance=t.relevance,
                run_id=self.pipeline.run_id,
            )
            for t in results[0].topics
        ]
