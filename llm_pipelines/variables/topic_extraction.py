"""PromptVariables for the 'topic_extraction' Phoenix prompt."""
from __future__ import annotations

from pydantic import BaseModel, Field

from llm_pipeline.prompts import PromptVariables


class TopicExtractionPrompt(PromptVariables):
    """Variables rendered into the 'topic_extraction' Phoenix prompt."""

    class system(BaseModel):
        # System message has no variables.
        pass

    class user(BaseModel):
        text: str = Field(description="Input text to extract topics from")
        sentiment: str = Field(
            description="Previously detected sentiment label",
        )
