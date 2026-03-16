"""Pipeline event type definitions with automatic registration.

Event dataclasses use frozen=True (immutability) and slots=True (memory).
Subclasses auto-register via __init_subclass__ with derived event_type strings.

Event fields containing mutable containers (dict, list) must not be mutated
after creation. This is a convention, not enforced at runtime.

Note: This module intentionally does NOT use ``from __future__ import annotations``
because ``slots=True`` creates a new class object that breaks the implicit
``__class__`` cell used by zero-arg ``super()`` in ``__init_subclass__``.
Type annotations use runtime-available forms instead.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, ClassVar


from llm_pipeline.state import utc_now


# -- Category constants -------------------------------------------------------

CATEGORY_PIPELINE_LIFECYCLE = "pipeline_lifecycle"
CATEGORY_STEP_LIFECYCLE = "step_lifecycle"
CATEGORY_CACHE = "cache"
CATEGORY_LLM_CALL = "llm_call"
CATEGORY_CONSENSUS = "consensus"
CATEGORY_INSTRUCTIONS_CONTEXT = "instructions_context"
CATEGORY_TRANSFORMATION = "transformation"
CATEGORY_EXTRACTION = "extraction"
CATEGORY_STATE = "state"
CATEGORY_TOOL_CALL = "tool_call"


# -- Registry & helpers -------------------------------------------------------

_EVENT_REGISTRY: dict[str, "type[PipelineEvent]"] = {}


def _derive_event_type(name: str) -> str:
    """Convert CamelCase class name to snake_case event type.

    Uses the two-pass regex from strategy.py:189-190 to correctly handle
    consecutive uppercase runs (e.g. LLMCallStarting -> llm_call_starting).
    """
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


# -- Base event ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PipelineEvent:
    """Base class for all pipeline events.

    Provides automatic event_type derivation, registry population,
    and serialization (to_dict / to_json).

    Subclasses must NOT override __init_subclass__ without calling super().

    Event fields containing mutable containers (dict, list) must not be
    mutated after creation. This is a convention enforced by review, not
    at runtime. Frozen dataclasses prevent reassignment of the field itself
    but not mutation of the container's contents.
    """

    # init=True fields first (dataclass ordering)
    run_id: str
    pipeline_name: str
    timestamp: datetime = field(default_factory=utc_now)

    # Derived at class definition, set in __post_init__
    event_type: str = field(init=False)

    # Class-level: not per-instance
    _EVENT_REGISTRY: ClassVar[dict[str, "type[PipelineEvent]"]] = _EVENT_REGISTRY

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Register subclass in _EVENT_REGISTRY with derived event_type.

        Uses explicit super(PipelineEvent, cls) because slots=True replaces
        the class object, breaking the implicit __class__ cell that zero-arg
        super() relies on.

        Skips registration for:
        - Classes with names starting with underscore (private bases)
        - Classes with ``_skip_registry = True`` (public intermediate bases)
        """
        # Explicit form required: slots=True breaks zero-arg super()
        super(PipelineEvent, cls).__init_subclass__(**kwargs)
        # Skip registration for intermediate bases
        if cls.__name__.startswith("_"):
            return
        if "_skip_registry" in cls.__dict__:
            return
        derived = _derive_event_type(cls.__name__)
        _EVENT_REGISTRY[derived] = cls
        # Store on class for __post_init__ to read
        cls._derived_event_type = derived  # type: ignore[attr-defined]

    def __post_init__(self) -> None:
        # Bypass frozen restriction to set init=False field
        object.__setattr__(self, "event_type", self._derived_event_type)  # type: ignore[attr-defined]

    # -- Serialization ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize event to dict, converting datetimes to ISO strings."""
        d = asdict(self)
        for key, val in d.items():
            if isinstance(val, datetime):
                d[key] = val.isoformat()
        return d

    def to_json(self) -> str:
        """Serialize event to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def resolve_event(
        cls, event_type: str, data: dict[str, Any]
    ) -> "PipelineEvent":
        """Reconstruct an event from its event_type and serialized data.

        Handles datetime deserialization for known datetime fields
        (timestamp, cached_at).
        """
        event_cls = _EVENT_REGISTRY.get(event_type)
        if event_cls is None:
            raise ValueError(f"Unknown event_type: {event_type!r}")
        # Deserialize known datetime fields
        dt_fields = ("timestamp", "cached_at")
        cleaned = dict(data)
        cleaned.pop("event_type", None)  # derived, not an init param
        for f in dt_fields:
            if f in cleaned and isinstance(cleaned[f], str):
                cleaned[f] = datetime.fromisoformat(cleaned[f])
        return event_cls(**cleaned)


# -- Step-scoped intermediate --------------------------------------------------


@dataclass(frozen=True, slots=True)
class StepScopedEvent(PipelineEvent):
    """Intermediate base for events occurring within (or selecting) a step.

    ``step_name`` is ``str | None`` rather than ``str`` to accommodate
    events that fire before a step is chosen (e.g. StepSelecting) or
    errors that occur outside any step scope (e.g. PipelineError).
    Concrete subclasses should document whether they expect step_name
    to be populated.
    """

    _skip_registry: ClassVar[bool] = True

    step_name: str | None = None


# -- Pipeline Lifecycle Events -------------------------------------------------


@dataclass(frozen=True, slots=True)
class PipelineStarted(PipelineEvent):
    """Emitted when a pipeline run begins."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_PIPELINE_LIFECYCLE


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineCompleted(PipelineEvent):
    """Emitted when a pipeline run completes successfully."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_PIPELINE_LIFECYCLE

    execution_time_ms: float
    steps_executed: int


@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineError(StepScopedEvent):
    """Emitted when a pipeline run fails with an error.

    Inherits StepScopedEvent because errors may occur within a step scope
    (step_name populated) or outside any step (step_name=None).
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_PIPELINE_LIFECYCLE

    error_type: str
    error_message: str
    traceback: str | None = None


# -- Step Lifecycle Events -----------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class StepSelecting(StepScopedEvent):
    """Emitted when step selection begins. step_name defaults to None.

    Note: Consumers should handle receiving StepSelecting without a subsequent
    StepSelected -- this occurs when no strategy provides a step at the given
    step_index, causing the loop to break before selection completes.
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_STEP_LIFECYCLE

    step_index: int
    strategy_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class StepSelected(StepScopedEvent):
    """Emitted when a step is selected for execution."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_STEP_LIFECYCLE

    step_number: int
    strategy_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StepSkipped(StepScopedEvent):
    """Emitted when a step is skipped."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_STEP_LIFECYCLE

    step_number: int
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class StepStarted(StepScopedEvent):
    """Emitted when a step begins execution."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_STEP_LIFECYCLE

    step_number: int
    system_key: str | None = None
    user_key: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class StepCompleted(StepScopedEvent):
    """Emitted when a step completes execution.

    execution_time_ms is float for sub-ms precision; PipelineStepState
    stores as int.
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_STEP_LIFECYCLE

    step_number: int
    execution_time_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


# -- Cache Events --------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheLookup(StepScopedEvent):
    """Emitted when a cache lookup is initiated."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CACHE

    input_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheHit(StepScopedEvent):
    """Emitted when a cache lookup finds a matching entry."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CACHE

    input_hash: str
    cached_at: datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheMiss(StepScopedEvent):
    """Emitted when a cache lookup finds no matching entry."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CACHE

    input_hash: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CacheReconstruction(StepScopedEvent):
    """Emitted when cached models are reconstructed from DB."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CACHE

    model_count: int
    instance_count: int


# -- LLM Call Events -----------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallPrepared(StepScopedEvent):
    """Emitted when LLM calls are prepared for a step."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL

    call_count: int
    system_key: str | None = None
    user_key: str | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallStarting(StepScopedEvent):
    """Emitted when an individual LLM call begins."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL

    call_index: int
    rendered_system_prompt: str
    rendered_user_prompt: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallCompleted(StepScopedEvent):
    """Emitted when an individual LLM call completes.

    validation_errors contains any Pydantic validation errors from
    parsing the response. Must not be mutated after creation.
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL

    call_index: int
    raw_response: str | None
    parsed_result: dict[str, Any] | None
    model_name: str | None
    attempt_count: int
    validation_errors: list[str] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallRetry(StepScopedEvent):
    """Emitted when an LLM call is retried after a failure."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL

    attempt: int
    max_retries: int
    error_type: str
    error_message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallFailed(StepScopedEvent):
    """Emitted when an LLM call fails after exhausting retries."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL

    max_retries: int
    last_error: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallRateLimited(StepScopedEvent):
    """Emitted when an LLM call is rate-limited and waiting."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL

    attempt: int
    wait_seconds: float
    backoff_type: str


# -- Consensus Events ----------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusStarted(StepScopedEvent):
    """Emitted when consensus voting begins for a step."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CONSENSUS

    threshold: float
    max_calls: int
    strategy_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusAttempt(StepScopedEvent):
    """Emitted for each consensus voting attempt."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CONSENSUS

    attempt: int
    group_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusReached(StepScopedEvent):
    """Emitted when consensus is successfully reached."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CONSENSUS

    attempt: int
    threshold: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ConsensusFailed(StepScopedEvent):
    """Emitted when consensus cannot be reached after exhausting calls."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_CONSENSUS

    max_calls: int
    largest_group_size: int


# -- Instructions & Context Events ---------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class InstructionsStored(StepScopedEvent):
    """Emitted when instructions are stored for a step."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_INSTRUCTIONS_CONTEXT

    instruction_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class InstructionsLogged(StepScopedEvent):
    """Emitted when instructions are logged during step execution.

    logged_keys lists the instruction keys that were logged. Must not be
    mutated after creation (convention, not enforced at runtime).
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_INSTRUCTIONS_CONTEXT

    logged_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True, kw_only=True)
class ContextUpdated(StepScopedEvent):
    """Emitted when pipeline context is updated with new keys.

    new_keys and context_snapshot are mutable containers; must not be
    mutated after creation (convention, not enforced at runtime).
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_INSTRUCTIONS_CONTEXT

    new_keys: list[str]
    context_snapshot: dict[str, Any]


# -- Transformation Events -----------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationStarting(StepScopedEvent):
    """Emitted when a transformation step begins."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TRANSFORMATION

    transformation_class: str
    cached: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class TransformationCompleted(StepScopedEvent):
    """Emitted when a transformation step completes."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TRANSFORMATION

    data_key: str
    execution_time_ms: float
    cached: bool


# -- Extraction Events ---------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractionStarting(StepScopedEvent):
    """Emitted when an extraction step begins."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION

    extraction_class: str
    model_class: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractionCompleted(StepScopedEvent):
    """Emitted when an extraction step completes successfully."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION

    extraction_class: str
    model_class: str
    instance_count: int
    execution_time_ms: float


@dataclass(frozen=True, slots=True, kw_only=True)
class ExtractionError(StepScopedEvent):
    """Emitted when an extraction step fails.

    validation_errors contains Pydantic validation details if applicable.
    Must not be mutated after creation (convention, not enforced at runtime).
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_EXTRACTION

    extraction_class: str
    error_type: str
    error_message: str
    validation_errors: list[str] = field(default_factory=list)


# -- State Events --------------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class StateSaved(StepScopedEvent):
    """Emitted when step state is persisted to the database."""

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_STATE

    step_number: int
    input_hash: str
    execution_time_ms: float


# -- Tool Call Events ----------------------------------------------------------


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallStarting(StepScopedEvent):
    """Emitted when a tool call begins during agent execution.

    tool_args is a mutable container; must not be mutated after creation
    (convention, not enforced at runtime).
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TOOL_CALL

    tool_name: str
    tool_args: dict[str, Any]
    call_index: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallCompleted(StepScopedEvent):
    """Emitted when a tool call completes during agent execution.

    result_preview is truncated to 200 chars by the emitting toolset.
    error is populated when the tool raised an exception (which is re-raised
    after emission).
    """

    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TOOL_CALL

    tool_name: str
    result_preview: str | None
    execution_time_ms: float
    call_index: int
    error: str | None = None


# -- Exports -------------------------------------------------------------------

__all__ = [
    # Base classes
    "PipelineEvent",
    "StepScopedEvent",
    # Category constants
    "CATEGORY_PIPELINE_LIFECYCLE",
    "CATEGORY_STEP_LIFECYCLE",
    "CATEGORY_CACHE",
    "CATEGORY_LLM_CALL",
    "CATEGORY_CONSENSUS",
    "CATEGORY_INSTRUCTIONS_CONTEXT",
    "CATEGORY_TRANSFORMATION",
    "CATEGORY_EXTRACTION",
    "CATEGORY_STATE",
    "CATEGORY_TOOL_CALL",
    # Helpers (public only; _EVENT_REGISTRY and _derive_event_type are internal)
    # -- use PipelineEvent.resolve_event() for registry access
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
    # Tool Call
    "ToolCallStarting",
    "ToolCallCompleted",
]
