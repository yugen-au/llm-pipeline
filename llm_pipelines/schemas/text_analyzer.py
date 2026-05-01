"""TextAnalyzer shared data shapes.

Schemas in this file are GENUINELY shared across multiple
artifacts — anything 1:1-paired with a single owner (a step's
INPUTS / INSTRUCTIONS, the pipeline's INPUT_DATA, an extraction's
MODEL) lives alongside its owner instead.

- ``TopicItem`` is consumed by ``TopicExtractionStep`` (in its
  ``INSTRUCTIONS.topics: list[TopicItem]``) AND by
  ``TopicExtraction`` (its ``FromTopicExtractionInputs.topics``
  pathway field). Two distinct artifacts use it, so it's a
  true shared shape.

DB-backed tables live in ``llm_pipelines/tables/text_analyzer.py``
(SQLModel with ``table=True``).
"""
from pydantic import BaseModel


class TopicItem(BaseModel):
    """LLM output shape for a single extracted topic. Not a DB table.

    Used by ``TopicExtractionStep.INSTRUCTIONS.topics`` and by
    ``TopicExtraction.FromTopicExtractionInputs.topics``.
    """
    name: str
    relevance: float
