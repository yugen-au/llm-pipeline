"""PromptVariables for the 'sentiment_analysis' Phoenix prompt."""
from __future__ import annotations

from pydantic import Field

from llm_pipeline.prompts import PromptVariables


class SentimentAnalysisPrompt(PromptVariables):
    """Variables rendered into the 'sentiment_analysis' Phoenix prompt."""

    text: str = Field(description="Input text to analyse for sentiment")
