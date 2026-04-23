"""Summary step."""
from typing import List

from llm_pipeline.step import LLMStep, step_definition
from llm_pipeline.types import StepCallParams

from llm_pipelines.schemas.text_analyzer import (
    SummaryInputs,
    SummaryInstructions,
)


@step_definition(
    inputs=SummaryInputs,
    instructions=SummaryInstructions,
    default_system_key="summary",
    default_user_key="summary",
)
class SummaryStep(LLMStep):
    """Produce a summary incorporating sentiment and topic context."""

    def prepare_calls(self) -> List[StepCallParams]:
        return [
            StepCallParams(
                variables={
                    "text": self.inputs.text,
                    "sentiment": self.inputs.sentiment,
                    "primary_topic": self.inputs.primary_topic,
                }
            )
        ]
