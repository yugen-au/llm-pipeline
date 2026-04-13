"""Sentiment analysis step with human review."""
from llm_pipeline.step import LLMStep, step_definition
from llm_pipeline.review import StepReview, ReviewData, DisplayField

from llm_pipelines.schemas.text_analyzer import (
    SentimentAnalysisContext,
    SentimentAnalysisInstructions,
)


class SentimentAnalysisReview(StepReview):
    """Review config for sentiment analysis — always enabled for demo."""
    pass


@step_definition(
    instructions=SentimentAnalysisInstructions,
    default_system_key="sentiment_analysis",
    default_user_key="sentiment_analysis",
    context=SentimentAnalysisContext,
    review=SentimentAnalysisReview,
)
class SentimentAnalysisStep(LLMStep):
    """Analyze sentiment of the input text."""

    def prepare_calls(self):
        return [{"variables": {"text": self.pipeline.validated_input.text}}]

    def process_instructions(self, instructions):
        return SentimentAnalysisContext(sentiment=instructions[0].sentiment)

    def prepare_review(self, instructions):
        inst = instructions[0]
        return ReviewData(
            display_data=[
                DisplayField(label="Sentiment", value=inst.sentiment, type="badge"),
                DisplayField(label="Explanation", value=inst.explanation, type="text"),
            ],
            raw_data=inst.model_dump(mode="json"),
        )
