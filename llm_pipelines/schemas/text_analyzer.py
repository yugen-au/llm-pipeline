"""TextAnalyzer data models: input, instructions, step inputs, DB models."""
from typing import ClassVar, Optional

from pydantic import BaseModel
from sqlmodel import SQLModel, Field

from llm_pipeline.context import PipelineInputData
from llm_pipeline.inputs import StepInputs
from llm_pipeline.step import LLMResultMixin


# ---------------------------------------------------------------------------
# Pipeline input data
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
# Instructions (LLM output contracts)
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
# Step inputs (declared contracts for each step)
# ---------------------------------------------------------------------------

class SentimentAnalysisInputs(StepInputs):
    """Everything SentimentAnalysisStep needs to run."""
    text: str


class TopicExtractionInputs(StepInputs):
    """Everything TopicExtractionStep needs to run."""
    text: str
    sentiment: str


class SummaryInputs(StepInputs):
    """Everything SummaryStep needs to run."""
    text: str
    sentiment: str
    primary_topic: str
