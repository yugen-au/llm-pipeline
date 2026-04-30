"""PromptVariables for the 'summary' Phoenix prompt."""
from __future__ import annotations

from pydantic import BaseModel, Field

from llm_pipeline.prompts import PromptVariables


class SummaryPrompt(PromptVariables):
    """Variables rendered into the 'summary' Phoenix prompt."""

    class system(BaseModel):
        # System message has no variables.
        pass

    class user(BaseModel):
        text: str = Field(description="Input text to summarise")
        sentiment: str = Field(
            description="Previously detected sentiment label",
        )
        primary_topic: str = Field(
            description="Primary topic extracted from the text",
        )
