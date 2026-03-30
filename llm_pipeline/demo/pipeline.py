"""
TextAnalyzer pipeline data models, registry, and pipeline configuration.

Contains the core data structures for the TextAnalyzer demo:
- TextAnalyzerInputData: validated pipeline input
- TopicItem: LLM output shape for topics (Pydantic model, not a DB table)
- Topic: persisted topic record (SQLModel table)
- TextAnalyzerRegistry: database registry declaring managed models
- Instructions, Context, and Extraction classes for 3 pipeline steps
- Step definitions: SentimentAnalysis, TopicExtraction, Summary
- DefaultStrategy, TextAnalyzerStrategies
- TextAnalyzerPipeline: fully wired PipelineConfig subclass
"""
from typing import Any, ClassVar, Optional

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import SQLModel, Field

from llm_pipeline.context import PipelineContext, PipelineInputData
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.step import LLMResultMixin, LLMStep, step_definition
from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies


# ---------------------------------------------------------------------------
# Input data
# ---------------------------------------------------------------------------

class TextAnalyzerInputData(PipelineInputData):
    """Input data for the TextAnalyzer pipeline."""

    text: str


# ---------------------------------------------------------------------------
# LLM output shapes / DB models
# ---------------------------------------------------------------------------

class TopicItem(BaseModel):
    """LLM output shape for a single extracted topic. Not a DB table."""

    name: str
    relevance: float


class Topic(SQLModel, table=True):
    """Persisted topic record extracted by the topic extraction step."""

    __tablename__ = "demo_topics"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    relevance: float
    run_id: str


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    """Database registry for the TextAnalyzer pipeline."""

    pass


# ---------------------------------------------------------------------------
# Instructions (must precede step definitions due to @step_definition)
# ---------------------------------------------------------------------------

class SentimentAnalysisInstructions(LLMResultMixin):
    """Structured output for sentiment analysis."""

    sentiment: str = ""
    explanation: str = ""

    example: ClassVar[dict] = {
        "sentiment": "positive",
        "explanation": "The text expresses optimism and satisfaction.",
        "confidence_score": 0.92,
    }


class TopicExtractionInstructions(LLMResultMixin):
    """Structured output for topic extraction."""

    topics: list[TopicItem] = []
    primary_topic: str = ""

    example: ClassVar[dict] = {
        "topics": [
            {"name": "machine learning", "relevance": 0.95},
            {"name": "data processing", "relevance": 0.7},
        ],
        "primary_topic": "machine learning",
        "confidence_score": 0.9,
    }


class SummaryInstructions(LLMResultMixin):
    """Structured output for text summarization."""

    summary: str = ""

    example: ClassVar[dict] = {
        "summary": "The text discusses key themes and their implications.",
        "confidence_score": 0.88,
    }


# ---------------------------------------------------------------------------
# Context classes
# ---------------------------------------------------------------------------

class SentimentAnalysisContext(PipelineContext):
    """Context produced by the sentiment analysis step."""

    sentiment: str


class TopicExtractionContext(PipelineContext):
    """Context produced by the topic extraction step."""

    primary_topic: str
    topics: list[str]


class SummaryContext(PipelineContext):
    """Context produced by the summary step."""

    summary: str


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

class TopicExtraction(PipelineExtraction, model=Topic):
    """Bridges TopicItem LLM output to Topic DB records."""

    def default(self, results: list[TopicExtractionInstructions]) -> list[Topic]:
        """Convert TopicExtractionInstructions into Topic instances."""
        return [
            Topic(
                name=t.name,
                relevance=t.relevance,
                run_id=self.pipeline.run_id,
            )
            for t in results[0].topics
        ]


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

@step_definition(
    instructions=SentimentAnalysisInstructions,
    default_system_key="sentiment_analysis",
    default_user_key="sentiment_analysis",
    context=SentimentAnalysisContext,
)
class SentimentAnalysisStep(LLMStep):
    """Analyze sentiment of the input text."""

    def prepare_calls(self):
        return [{"variables": {"text": self.pipeline.validated_input.text}}]

    def process_instructions(self, instructions):
        return SentimentAnalysisContext(sentiment=instructions[0].sentiment)


@step_definition(
    instructions=TopicExtractionInstructions,
    default_system_key="topic_extraction",
    default_user_key="topic_extraction",
    default_extractions=[TopicExtraction],
    context=TopicExtractionContext,
)
class TopicExtractionStep(LLMStep):
    """Extract topics from the input text."""

    def prepare_calls(self):
        return [
            {
                "variables": {
                    "text": self.pipeline.validated_input.text,
                    "sentiment": self.pipeline.context["sentiment"],
                }
            }
        ]

    def process_instructions(self, instructions):
        return TopicExtractionContext(
            primary_topic=instructions[0].primary_topic,
            topics=[t.name for t in instructions[0].topics],
        )


@step_definition(
    instructions=SummaryInstructions,
    default_system_key="summary",
    default_user_key="summary",
    context=SummaryContext,
)
class SummaryStep(LLMStep):
    """Produce a summary incorporating sentiment and topic context."""

    def prepare_calls(self):
        return [
            {
                "variables": {
                    "text": self.pipeline.validated_input.text,
                    "sentiment": self.pipeline.context["sentiment"],
                    "primary_topic": self.pipeline.context["primary_topic"],
                }
            }
        ]

    def process_instructions(self, instructions):
        return SummaryContext(summary=instructions[0].summary)


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class DefaultStrategy(PipelineStrategy):
    """Single strategy that always applies; runs all 3 steps sequentially."""

    # Redundant: auto-generated from class name "Default" -> "default".
    # Kept explicit for demo clarity.
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


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class TextAnalyzerPipeline(
    PipelineConfig,
    registry=TextAnalyzerRegistry,
    strategies=TextAnalyzerStrategies,
):
    """Demo pipeline: sentiment -> topic extraction -> summary."""

    INPUT_DATA: ClassVar[type] = TextAnalyzerInputData

    @classmethod
    def seed_prompts(cls, engine: Engine) -> None:
        """Create demo_topics table and seed prompts idempotently."""
        from llm_pipeline.demo.prompts import seed_prompts

        seed_prompts(cls, engine)
