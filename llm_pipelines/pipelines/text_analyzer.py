"""TextAnalyzer pipeline: sentiment -> topic extraction -> summary."""
from typing import Any, ClassVar

from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies

from llm_pipelines.schemas.text_analyzer import (
    TextAnalyzerInputData,
    Topic,
)
from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
from llm_pipelines.steps.topic_extraction import TopicExtractionStep
from llm_pipelines.steps.summary import SummaryStep


class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    """Database registry for the TextAnalyzer pipeline."""
    pass


class DefaultStrategy(PipelineStrategy):
    """Single strategy that always applies; runs all 3 steps sequentially."""
    NAME = "default"

    def can_handle(self, context: dict[str, Any]) -> bool:
        return True

    def get_steps(self):
        return [
            SentimentAnalysisStep.create_definition(),
            TopicExtractionStep.create_definition(),
            SummaryStep.create_definition(),
        ]


class TextAnalyzerStrategies(PipelineStrategies, strategies=[DefaultStrategy]):
    """Strategies container for the TextAnalyzer pipeline."""
    pass


class TextAnalyzerPipeline(
    PipelineConfig,
    registry=TextAnalyzerRegistry,
    strategies=TextAnalyzerStrategies,
):
    """Demo pipeline: sentiment -> topic extraction -> summary."""
    INPUT_DATA: ClassVar[type] = TextAnalyzerInputData
