"""PromptVariables for the 'topic_extraction' Phoenix prompt."""
from __future__ import annotations

from pydantic import Field

from llm_pipeline.prompts import PromptVariables


class TopicExtractionPrompt(PromptVariables):
    """Variables rendered into the 'topic_extraction' Phoenix prompt."""

    text: str = Field(description="Input text to extract topics from")
    sentiment: str = Field(description="Previously detected sentiment label")
