"""Summary step."""
from llm_pipeline.step import LLMStep, step_definition

from llm_pipelines.schemas.text_analyzer import (
    SummaryContext,
    SummaryInstructions,
)


@step_definition(
    instructions=SummaryInstructions,
    default_system_key="summary",
    default_user_key="summary",
    context=SummaryContext,
)
class SummaryStep(LLMStep):
    """Produce a summary incorporating sentiment and topic context."""

    def prepare_calls(self):
        return [
            {
                "variables": {
                    "text": self.pipeline.validated_input.text,
                    "sentiment": self.pipeline.context["sentiment"],
                    "primary_topic": self.pipeline.context["primary_topic"],
                }
            }
        ]

    def process_instructions(self, instructions):
        return SummaryContext(summary=instructions[0].summary)
