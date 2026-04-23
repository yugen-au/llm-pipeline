"""TextAnalyzer pipeline: sentiment -> topic extraction -> summary."""
from typing import Any, List

from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.strategy import PipelineStrategies, PipelineStrategy
from llm_pipeline.wiring import Bind, FromInput, FromOutput, FromPipeline

from llm_pipelines.extractions.text_analyzer import TopicExtraction
from llm_pipelines.schemas.text_analyzer import (
    SentimentAnalysisInputs,
    SummaryInputs,
    TextAnalyzerInputData,
    Topic,
    TopicExtractionInputs,
)
from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
from llm_pipelines.steps.summary import SummaryStep
from llm_pipelines.steps.topic_extraction import TopicExtractionStep


class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    """Database registry for the TextAnalyzer pipeline."""
    pass


class DefaultStrategy(PipelineStrategy):
    """Single strategy that always applies; runs all 3 steps sequentially."""
    NAME = "default"

    def can_handle(self, context: dict[str, Any]) -> bool:
        return True

    def get_bindings(self) -> List[Bind]:
        return [
            Bind(
                step=SentimentAnalysisStep,
                inputs=SentimentAnalysisInputs.sources(
                    text=FromInput("text"),
                ),
            ),
            Bind(
                step=TopicExtractionStep,
                inputs=TopicExtractionInputs.sources(
                    text=FromInput("text"),
                    sentiment=FromOutput(
                        SentimentAnalysisStep, field="sentiment"
                    ),
                ),
                extractions=[
                    Bind(
                        extraction=TopicExtraction,
                        inputs=TopicExtraction.FromTopicExtractionInputs.sources(
                            topics=FromOutput(
                                TopicExtractionStep, field="topics"
                            ),
                            run_id=FromPipeline("run_id"),
                        ),
                    ),
                ],
            ),
            Bind(
                step=SummaryStep,
                inputs=SummaryInputs.sources(
                    text=FromInput("text"),
                    sentiment=FromOutput(
                        SentimentAnalysisStep, field="sentiment"
                    ),
                    primary_topic=FromOutput(
                        TopicExtractionStep, field="primary_topic"
                    ),
                ),
            ),
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
    INPUT_DATA = TextAnalyzerInputData
