"""PromptVariables for the 'summary' Phoenix prompt."""
from __future__ import annotations

from pydantic import Field

from llm_pipeline.prompts import PromptVariables


class SummaryPrompt(PromptVariables):
    """Variables rendered into the 'summary' Phoenix prompt."""

    text: str = Field(description="Input text to summarise")
    sentiment: str = Field(description="Previously detected sentiment label")
    primary_topic: str = Field(description="Primary topic extracted from the text")
