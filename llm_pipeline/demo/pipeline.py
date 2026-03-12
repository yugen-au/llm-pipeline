"""
TextAnalyzer pipeline data models, registry, and pipeline configuration.

Contains the core data structures for the TextAnalyzer demo:
- TextAnalyzerInputData: validated pipeline input
- TopicItem: LLM output shape for topics (Pydantic model, not a DB table)
- Topic: persisted topic record (SQLModel table)
- TextAnalyzerRegistry: database registry declaring managed models
"""
from typing import Optional

from pydantic import BaseModel
from sqlmodel import SQLModel, Field

from llm_pipeline.context import PipelineInputData
from llm_pipeline.registry import PipelineDatabaseRegistry


class TextAnalyzerInputData(PipelineInputData):
    """Input data for the TextAnalyzer pipeline."""

    text: str


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


class TextAnalyzerRegistry(PipelineDatabaseRegistry, models=[Topic]):
    """Database registry for the TextAnalyzer pipeline."""

    pass
