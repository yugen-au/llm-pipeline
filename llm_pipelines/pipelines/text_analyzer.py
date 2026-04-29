"""TextAnalyzer pipeline (pydantic-graph-native).

Graph: ``SentimentAnalysisStep -> TopicExtractionStep -> TopicExtraction
-> SummaryStep -> End``. Each node declares its own ``inputs_spec`` and
``run()`` return annotation; the framework's compile-time validator
asserts ``FromOutput(...)`` references resolve, naming conventions
hold, and the graph is acyclic.
"""
from __future__ import annotations

from llm_pipeline.graph import Pipeline

from llm_pipelines.extractions.text_analyzer import TopicExtraction
from llm_pipelines.schemas.text_analyzer import TextAnalyzerInputData
from llm_pipelines.steps.sentiment_analysis import SentimentAnalysisStep
from llm_pipelines.steps.summary import SummaryStep
from llm_pipelines.steps.topic_extraction import TopicExtractionStep


class TextAnalyzerPipeline(Pipeline):
    """Demo pipeline: sentiment -> topic extraction -> summary."""

    INPUT_DATA = TextAnalyzerInputData
    nodes = [
        SentimentAnalysisStep,
        TopicExtractionStep,
        TopicExtraction,
        SummaryStep,
    ]
    # start_node defaults to nodes[0] (SentimentAnalysisStep).
