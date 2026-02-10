"""
LLM Pipeline - Declarative LLM pipeline orchestration framework.

Usage:
    from llm_pipeline import PipelineConfig, LLMStep, LLMResultMixin, step_definition
    from llm_pipeline.llm import LLMProvider
    from llm_pipeline.llm.gemini import GeminiProvider  # optional
"""

from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.step import LLMStep, LLMResultMixin, step_definition
from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies, StepDefinition
from llm_pipeline.context import PipelineContext
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.transformation import PipelineTransformation
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.state import PipelineStepState, PipelineRunInstance
from llm_pipeline.types import ArrayValidationConfig, ValidationContext
from llm_pipeline.db import init_pipeline_db
from llm_pipeline.session import ReadOnlySession

__version__ = "0.1.0"

__all__ = [
    # Core
    "PipelineConfig",
    "LLMStep",
    "LLMResultMixin",
    "step_definition",
    # Strategy
    "PipelineStrategy",
    "PipelineStrategies",
    "StepDefinition",
    # Data handling
    "PipelineContext",
    "PipelineExtraction",
    "PipelineTransformation",
    "PipelineDatabaseRegistry",
    # State
    "PipelineStepState",
    "PipelineRunInstance",
    # Types
    "ArrayValidationConfig",
    "ValidationContext",
    # DB
    "init_pipeline_db",
    # Session
    "ReadOnlySession",
]
