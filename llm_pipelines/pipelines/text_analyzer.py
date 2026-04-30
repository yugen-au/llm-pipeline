"""TextAnalyzer pipeline (pydantic-graph-native).

Graph: ``SentimentAnalysisStep -> TopicExtractionStep -> TopicExtraction
-> SummaryStep -> End``. Each ``Step``/``Extraction`` wrapper declares
the wiring (``inputs_spec``) for the contained node. The framework's
compile-time validator asserts ``FromOutput(...)`` references resolve,
naming conventions hold, and the graph is acyclic.
"""
from __future__ import annotations

from llm_pipeline.graph import (
    Extraction,
    FromInput,
    FromOutput,
    FromPipeline,
    Pipeline,
    Step,
)

from llm_pipelines.extractions.text_analyzer import (
    FromTopicExtractionInputs,
    TopicExtraction,
)
from llm_pipelines.schemas.text_analyzer import (
    SentimentAnalysisInputs,
    SummaryInputs,
    TextAnalyzerInputData,
    TopicExtractionInputs,
)
from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
from llm_pipelines.steps.summary import SummaryStep
from llm_pipelines.steps.topic_extraction import TopicExtractionStep


class TextAnalyzerPipeline(Pipeline):
    """Demo pipeline: sentiment -> topic extraction -> summary."""

    INPUT_DATA = TextAnalyzerInputData
    nodes = [
        Step(
            SentimentAnalysisStep,
            inputs_spec=SentimentAnalysisInputs.sources(
                text=FromInput("text"),
            ),
        ),
        Step(
            TopicExtractionStep,
            inputs_spec=TopicExtractionInputs.sources(
                text=FromInput("text"),
                sentiment=FromOutput(SentimentAnalysisStep, field="sentiment"),
            ),
        ),
        Extraction(
            TopicExtraction,
            inputs_spec=FromTopicExtractionInputs.sources(
                topics=FromOutput(TopicExtractionStep, field="topics"),
                run_id=FromPipeline("run_id"),
            ),
        ),
        Step(
            SummaryStep,
            inputs_spec=SummaryInputs.sources(
                text=FromInput("text"),
                sentiment=FromOutput(SentimentAnalysisStep, field="sentiment"),
                primary_topic=FromOutput(TopicExtractionStep, field="primary_topic"),
            ),
        ),
    ]
