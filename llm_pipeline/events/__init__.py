"""Pipeline event system - typed, immutable event dataclasses and emitters.

Re-exports all event types, base classes, category constants, and helpers
from :mod:`llm_pipeline.events.types`, plus :class:`LLMCallResult` from
:mod:`llm_pipeline.llm.result`, and :class:`PipelineEventEmitter` /
:class:`CompositeEmitter` from :mod:`llm_pipeline.events.emitter`.

Usage::

    from llm_pipeline.events import PipelineStarted, StepCompleted, LLMCallResult
    from llm_pipeline.events import CATEGORY_LLM_CALL, resolve_event
    from llm_pipeline.events import PipelineEventEmitter, CompositeEmitter
"""

from llm_pipeline.events.types import (
    # Base classes
    PipelineEvent,
    StepScopedEvent,
    # Category constants
    CATEGORY_CACHE,
    CATEGORY_CONSENSUS,
    CATEGORY_EXTRACTION,
    CATEGORY_INSTRUCTIONS_CONTEXT,
    CATEGORY_LLM_CALL,
    CATEGORY_PIPELINE_LIFECYCLE,
    CATEGORY_STATE,
    CATEGORY_STEP_LIFECYCLE,
    CATEGORY_TRANSFORMATION,
    # Helpers
    _EVENT_REGISTRY,
    _derive_event_type,
    # Pipeline Lifecycle
    PipelineCompleted,
    PipelineError,
    PipelineStarted,
    # Step Lifecycle
    StepCompleted,
    StepSelected,
    StepSelecting,
    StepSkipped,
    StepStarted,
    # Cache
    CacheHit,
    CacheLookup,
    CacheMiss,
    CacheReconstruction,
    # LLM Call
    LLMCallCompleted,
    LLMCallFailed,
    LLMCallPrepared,
    LLMCallRateLimited,
    LLMCallRetry,
    LLMCallStarting,
    # Consensus
    ConsensusAttempt,
    ConsensusFailed,
    ConsensusReached,
    ConsensusStarted,
    # Instructions & Context
    ContextUpdated,
    InstructionsLogged,
    InstructionsStored,
    # Transformation
    TransformationCompleted,
    TransformationStarting,
    # Extraction
    ExtractionCompleted,
    ExtractionError,
    ExtractionStarting,
    # State
    StateSaved,
)
from llm_pipeline.events.emitter import CompositeEmitter, PipelineEventEmitter
from llm_pipeline.llm.result import LLMCallResult

# Convenience alias for resolve_event on PipelineEvent
resolve_event = PipelineEvent.resolve_event

__all__ = [
    # Base Classes
    "PipelineEvent",
    "StepScopedEvent",
    # Emitters
    "PipelineEventEmitter",
    "CompositeEmitter",
    # LLM Results
    "LLMCallResult",
    # Category Constants
    "CATEGORY_PIPELINE_LIFECYCLE",
    "CATEGORY_STEP_LIFECYCLE",
    "CATEGORY_CACHE",
    "CATEGORY_LLM_CALL",
    "CATEGORY_CONSENSUS",
    "CATEGORY_INSTRUCTIONS_CONTEXT",
    "CATEGORY_TRANSFORMATION",
    "CATEGORY_EXTRACTION",
    "CATEGORY_STATE",
    # Helpers (public only; _EVENT_REGISTRY and _derive_event_type are internal)
    "resolve_event",
    # Pipeline Lifecycle
    "PipelineStarted",
    "PipelineCompleted",
    "PipelineError",
    # Step Lifecycle
    "StepSelecting",
    "StepSelected",
    "StepSkipped",
    "StepStarted",
    "StepCompleted",
    # Cache
    "CacheLookup",
    "CacheHit",
    "CacheMiss",
    "CacheReconstruction",
    # LLM Call
    "LLMCallPrepared",
    "LLMCallStarting",
    "LLMCallCompleted",
    "LLMCallRetry",
    "LLMCallFailed",
    "LLMCallRateLimited",
    # Consensus
    "ConsensusStarted",
    "ConsensusAttempt",
    "ConsensusReached",
    "ConsensusFailed",
    # Instructions & Context
    "InstructionsStored",
    "InstructionsLogged",
    "ContextUpdated",
    # Transformation
    "TransformationStarting",
    "TransformationCompleted",
    # Extraction
    "ExtractionStarting",
    "ExtractionCompleted",
    "ExtractionError",
    # State
    "StateSaved",
]
