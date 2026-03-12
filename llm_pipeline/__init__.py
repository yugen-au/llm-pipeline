"""
LLM Pipeline - Declarative LLM pipeline orchestration framework.

Usage::

    # Core orchestration
    from llm_pipeline import PipelineConfig, LLMStep, LLMResultMixin, step_definition
    from llm_pipeline.llm import LLMProvider
    from llm_pipeline.llm.gemini import GeminiProvider  # optional

    # Event infrastructure (top-level)
    from llm_pipeline import PipelineEventEmitter, CompositeEmitter, LoggingEventHandler
    from llm_pipeline import LLMCallResult, PipelineEvent

    # Concrete events (submodule)
    from llm_pipeline.events import PipelineStarted, StepStarted, LLMCallStarting
"""

from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.step import LLMStep, LLMResultMixin, step_definition
from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies, StepDefinition
from llm_pipeline.context import PipelineContext, PipelineInputData
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.transformation import PipelineTransformation
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun
from llm_pipeline.events.models import PipelineEventRecord
from llm_pipeline.events.types import PipelineEvent
from llm_pipeline.events.emitter import PipelineEventEmitter, CompositeEmitter
from llm_pipeline.events.handlers import LoggingEventHandler, InMemoryEventHandler, SQLiteEventHandler, DEFAULT_LEVEL_MAP
from llm_pipeline.llm.result import LLMCallResult
from llm_pipeline.types import ArrayValidationConfig, ValidationContext
from llm_pipeline.db import init_pipeline_db
from llm_pipeline.session import ReadOnlySession
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.agent_builders import StepDeps, build_step_agent

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
    "PipelineInputData",
    "PipelineExtraction",
    "PipelineTransformation",
    "PipelineDatabaseRegistry",
    # State
    "PipelineStepState",
    "PipelineRunInstance",
    "PipelineRun",
    "PipelineEventRecord",
    # Events
    "PipelineEvent",
    "PipelineEventEmitter",
    "CompositeEmitter",
    "LLMCallResult",
    "LoggingEventHandler",
    "InMemoryEventHandler",
    "SQLiteEventHandler",
    "DEFAULT_LEVEL_MAP",
    # Types
    "ArrayValidationConfig",
    "ValidationContext",
    # DB
    "init_pipeline_db",
    # Session
    "ReadOnlySession",
    # Introspection
    "PipelineIntrospector",
    # Agent
    "AgentRegistry",
    "StepDeps",
    "build_step_agent",
]
