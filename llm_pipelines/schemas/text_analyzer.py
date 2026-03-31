"""TextAnalyzer data models: input, instructions, contexts, and DB models."""
from typing import ClassVar, Optional

from pydantic import BaseModel
from sqlmodel import SQLModel, Field

from llm_pipeline.context import PipelineContext, PipelineInputData
from llm_pipeline.step import LLMResultMixin


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
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    relevance: float
    run_id: str


# ---------------------------------------------------------------------------
# Instructions
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
