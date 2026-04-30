"""
LLM Pipeline — Declarative LLM pipeline orchestration framework.

Pipelines are now graph objects. Declare them via
``llm_pipeline.graph``::

    from llm_pipeline.graph import (
        ExtractionNode,
        FromInput,
        FromOutput,
        LLMResultMixin,
        LLMStepNode,
        Pipeline,
        PipelineInputData,
        ReviewNode,
        StepInputs,
    )

Observability is provided via OTEL + pydantic-ai instrumentation,
wired by ``llm_pipeline.observability.configure()``.
"""

from llm_pipeline.agent_builders import StepDeps, build_step_agent
from llm_pipeline.agent_registry import (
    AgentSpec,
    clear_agent_registry,
    get_agent_tools,
    get_registered_agents,
    register_agent,
)
from llm_pipeline.consensus import (
    AdaptiveStrategy,
    ConfidenceWeightedStrategy,
    ConsensusResult,
    ConsensusStrategy,
    MajorityVoteStrategy,
    SoftVoteStrategy,
)
from llm_pipeline.db import init_pipeline_db
from llm_pipeline.graph import (
    Computed,
    Extraction,
    ExtractionNode,
    FromInput,
    FromOutput,
    FromPipeline,
    LLMResultMixin,
    LLMStepNode,
    Pipeline,
    PipelineDeps,
    PipelineEnd,
    PipelineInputData,
    PipelineState,
    Review,
    ReviewNode,
    RunOutcome,
    SourcesSpec,
    SqlmodelStatePersistence,
    Step,
    StepInputs,
    resume_pipeline,
    run_pipeline,
    run_pipeline_in_memory,
)
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.prompts.variables import (
    register_auto_generate,
    set_auto_generate_base_path,
)
from llm_pipeline.session import ReadOnlySession
from llm_pipeline.state import (
    DraftPipeline,
    DraftStep,
    PipelineNodeSnapshot,
    PipelineRun,
    PipelineRunInstance,
)
from llm_pipeline.types import ArrayValidationConfig, ValidationContext
from llm_pipeline.validators import (
    DEFAULT_NOT_FOUND_INDICATORS,
    array_length_validator,
    not_found_validator,
)

__version__ = "0.1.0"

__all__ = [
    # Graph base
    "Pipeline",
    "PipelineEnd",
    "PipelineState",
    "PipelineDeps",
    # Node base classes
    "LLMStepNode",
    "ExtractionNode",
    "ReviewNode",
    # Output schema base
    "LLMResultMixin",
    # Inputs + adapter machinery
    "PipelineInputData",
    "StepInputs",
    # Per-node bindings used in Pipeline.nodes
    "Step",
    "Extraction",
    "Review",
    # Source types + spec
    "Computed",
    "FromInput",
    "FromOutput",
    "FromPipeline",
    "SourcesSpec",
    # Runtime
    "run_pipeline",
    "resume_pipeline",
    "run_pipeline_in_memory",
    "RunOutcome",
    "SqlmodelStatePersistence",
    # State tables
    "PipelineNodeSnapshot",
    "PipelineRunInstance",
    "PipelineRun",
    "DraftStep",
    "DraftPipeline",
    # Types
    "ArrayValidationConfig",
    "ValidationContext",
    # DB / session
    "init_pipeline_db",
    "ReadOnlySession",
    # Introspection
    "PipelineIntrospector",
    # Agent registry
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
