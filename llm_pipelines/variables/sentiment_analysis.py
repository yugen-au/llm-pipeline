"""PromptVariables for the 'sentiment_analysis' Phoenix prompt."""
from __future__ import annotations

from pydantic import BaseModel, Field

from llm_pipeline.prompts import PromptVariables


class SentimentAnalysisPrompt(PromptVariables):
    """Variables rendered into the 'sentiment_analysis' Phoenix prompt."""

    class system(BaseModel):
        # System message has no variables.
        pass

    class user(BaseModel):
        text: str = Field(description="Input text to analyse for sentiment")
