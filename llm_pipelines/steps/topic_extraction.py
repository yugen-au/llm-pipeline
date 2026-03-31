"""Topic extraction step."""
from llm_pipeline.step import LLMStep, step_definition

from llm_pipelines.schemas.text_analyzer import (
    TopicExtractionContext,
    TopicExtractionInstructions,
)
from llm_pipelines.extractions.text_analyzer import TopicExtraction


@step_definition(
    instructions=TopicExtractionInstructions,
    default_system_key="topic_extraction",
    default_user_key="topic_extraction",
    default_extractions=[TopicExtraction],
    context=TopicExtractionContext,
)
class TopicExtractionStep(LLMStep):
    """Extract topics from the input text."""

    def prepare_calls(self):
        return [
            {
                "variables": {
                    "text": self.pipeline.validated_input.text,
                    "sentiment": self.pipeline.context["sentiment"],
                }
            }
        ]

    def process_instructions(self, instructions):
        return TopicExtractionContext(
            primary_topic=instructions[0].primary_topic,
            topics=[t.name for t in instructions[0].topics],
        )
