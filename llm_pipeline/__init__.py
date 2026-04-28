"""
LLM Pipeline - Declarative LLM pipeline orchestration framework.

Usage::

    # Core orchestration
    from llm_pipeline import PipelineConfig, LLMStep, LLMResultMixin, step_definition

Observability is provided via Langfuse + pydantic-ai's OTEL
instrumentation, wired by ``llm_pipeline.observability.configure()``.
"""

from llm_pipeline.pipeline import PipelineConfig
from llm_pipeline.step import LLMStep, LLMResultMixin, step_definition
from llm_pipeline.strategy import PipelineStrategy, PipelineStrategies, StepDefinition
from llm_pipeline.consensus import (
    ConsensusStrategy,
    ConsensusResult,
    MajorityVoteStrategy,
    ConfidenceWeightedStrategy,
    AdaptiveStrategy,
    SoftVoteStrategy,
)
from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.extraction import PipelineExtraction
from llm_pipeline.transformation import PipelineTransformation
from llm_pipeline.registry import PipelineDatabaseRegistry
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun, DraftStep, DraftPipeline
from llm_pipeline.types import ArrayValidationConfig, ValidationContext
from llm_pipeline.db import init_pipeline_db
from llm_pipeline.session import ReadOnlySession
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.agent_registry import AgentSpec, register_agent, get_agent_tools, get_registered_agents, clear_agent_registry
from llm_pipeline.agent_builders import StepDeps, build_step_agent
from llm_pipeline.validators import not_found_validator, array_length_validator, DEFAULT_NOT_FOUND_INDICATORS
from llm_pipeline.prompts.variables import (
    PromptVariables,
    register_prompt_variables,
    get_prompt_variables,
    get_all_prompt_variables,
    clear_prompt_variables_registry,
    RegistryVariableResolver,
    register_auto_generate,
    set_auto_generate_base_path,
)

try:
    from llm_pipeline.creator import StepCreatorPipeline
    _has_creator = True
except ImportError:
    _has_creator = False

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
    "PipelineInputData",
    "PipelineExtraction",
    "PipelineTransformation",
    "PipelineDatabaseRegistry",
    # State
    "PipelineStepState",
    "PipelineRunInstance",
    "PipelineRun",
    "DraftStep",
    "DraftPipeline",
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
    "AgentSpec",
    "register_agent",
    "get_agent_tools",
    "get_registered_agents",
    "clear_agent_registry",
    "StepDeps",
    "build_step_agent",
    # Validators
    "not_found_validator",
    "array_length_validator",
    "DEFAULT_NOT_FOUND_INDICATORS",
    # Prompts
    "PromptVariables",
    "register_prompt_variables",
    "get_prompt_variables",
    "get_all_prompt_variables",
    "clear_prompt_variables_registry",
    "RegistryVariableResolver",
    "register_auto_generate",
    "set_auto_generate_base_path",
    # Consensus
    "ConsensusStrategy",
    "ConsensusResult",
    "MajorityVoteStrategy",
    "ConfidenceWeightedStrategy",
    "AdaptiveStrategy",
    "SoftVoteStrategy",
]

if _has_creator:
    __all__ += ["StepCreatorPipeline"]
