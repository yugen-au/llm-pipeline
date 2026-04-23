"""Topic extraction step."""
from typing import List

from llm_pipeline.step import LLMStep, step_definition
from llm_pipeline.types import StepCallParams

from llm_pipelines.schemas.text_analyzer import (
    TopicExtractionInputs,
    TopicExtractionInstructions,
)


@step_definition(
    inputs=TopicExtractionInputs,
    instructions=TopicExtractionInstructions,
    default_system_key="topic_extraction",
    default_user_key="topic_extraction",
)
class TopicExtractionStep(LLMStep):
    """Extract topics from the input text."""

    def prepare_calls(self) -> List[StepCallParams]:
        return [
            StepCallParams(
                variables={
                    "text": self.inputs.text,
                    "sentiment": self.inputs.sentiment,
                }
            )
        ]
