"""Sentiment analysis step with human review and eval evaluators."""
from dataclasses import dataclass
from typing import List

from llm_pipeline.evals.evaluators import FieldMatchEvaluator
from llm_pipeline.review import DisplayField, ReviewData, StepReview
from llm_pipeline.step import LLMStep, step_definition
from llm_pipeline.types import StepCallParams

from llm_pipelines.schemas.text_analyzer import (
    SentimentAnalysisInputs,
    SentimentAnalysisInstructions,
)


@dataclass(repr=False)
class SentimentLabelEvaluator(FieldMatchEvaluator):
    """Check output.sentiment matches expected_output['sentiment']."""

    field_name: str = "sentiment"


class SentimentAnalysisReview(StepReview):
    """Review config for sentiment analysis -- always enabled for demo."""
    pass


@step_definition(
    inputs=SentimentAnalysisInputs,
    instructions=SentimentAnalysisInstructions,
    review=SentimentAnalysisReview,
    evaluators=[SentimentLabelEvaluator],
)
class SentimentAnalysisStep(LLMStep):
    """Analyze sentiment of the input text."""

    def prepare_calls(self) -> List[StepCallParams]:
        return [StepCallParams(variables={"text": self.inputs.text})]

    def prepare_review(self, instructions):
        inst = instructions[0]
        return ReviewData(
            display_data=[
                DisplayField(label="Sentiment", value=inst.sentiment, type="badge"),
                DisplayField(label="Explanation", value=inst.explanation, type="text"),
            ],
            raw_data=inst.model_dump(mode="json"),
        )
