"""Sentiment analysis step."""
from llm_pipeline.step import LLMStep, step_definition

from llm_pipelines.schemas.text_analyzer import (
    SentimentAnalysisContext,
    SentimentAnalysisInstructions,
)


@step_definition(
    instructions=SentimentAnalysisInstructions,
    default_system_key="sentiment_analysis",
    default_user_key="sentiment_analysis",
    context=SentimentAnalysisContext,
)
class SentimentAnalysisStep(LLMStep):
    """Analyze sentiment of the input text."""

    def prepare_calls(self):
        return [{"variables": {"text": self.pipeline.validated_input.text}}]

    def process_instructions(self, instructions):
        return SentimentAnalysisContext(sentiment=instructions[0].sentiment)
