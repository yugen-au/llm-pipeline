"""
Pipeline wiring for the meta-pipeline step generator.

Declares StepCreatorInputData, StepCreatorRegistry,
DefaultCreatorStrategy, StepCreatorStrategies, and StepCreatorPipeline --
the fully wired PipelineConfig subclass for the creator pipeline.
"""
from typing import Any, ClassVar

from sqlalchemy import Engine

from llm_pipeline.agent_registry import register_agent
from llm_pipeline.context import PipelineInputData
from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies

from .context7 import query_framework_docs, resolve_library_id
from .models import GenerationRecord


# ---------------------------------------------------------------------------
# Input data
# ---------------------------------------------------------------------------


class StepCreatorInputData(PipelineInputData):
    """Input data for the StepCreator pipeline."""

    description: str
    target_pipeline: str | None = None
    include_extraction: bool = True
    include_transformation: bool = False


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class StepCreatorRegistry(PipelineDatabaseRegistry, models=[GenerationRecord]):
    """Database registry for the StepCreator pipeline."""

    pass


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


_ctx7_tools = [query_framework_docs, resolve_library_id]

register_agent("code_gen", tools=_ctx7_tools)
register_agent("prompt_gen", tools=_ctx7_tools)


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


class DefaultCreatorStrategy(PipelineStrategy):
    """Single strategy that always applies; runs all 4 creator steps sequentially."""

    def can_handle(self, context: dict[str, Any]) -> bool:
        return True

    def get_steps(self):
        # Inline imports to avoid circular dependency with steps.py
        from llm_pipeline.creator.steps import (
            CodeGenerationStep,
            CodeValidationStep,
            PromptGenerationStep,
            RequirementsAnalysisStep,
        )

        return [
            RequirementsAnalysisStep.create_definition(),
            CodeGenerationStep.create_definition(),
            PromptGenerationStep.create_definition(),
            CodeValidationStep.create_definition(),
        ]


class StepCreatorStrategies(PipelineStrategies, strategies=[DefaultCreatorStrategy]):
    """Strategies container for the StepCreator pipeline."""

    pass


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class StepCreatorPipeline(
    PipelineConfig,
    registry=StepCreatorRegistry,
    strategies=StepCreatorStrategies,
):
    """Meta-pipeline: generates scaffold code for new pipeline steps from descriptions."""

    INPUT_DATA: ClassVar[type] = StepCreatorInputData

    @classmethod
    def _seed_prompts(cls, engine: Engine) -> None:
        """Internal. Use POST /api/prompts for custom pipelines."""
        from llm_pipeline.creator.prompts import _seed_prompts

        _seed_prompts(cls, engine)


__all__ = [
    "StepCreatorInputData",
    "StepCreatorRegistry",
    "DefaultCreatorStrategy",
    "StepCreatorStrategies",
    "StepCreatorPipeline",
]
