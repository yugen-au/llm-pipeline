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
    mutated after creation.
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
        """
        # Explicit form required: slots=True breaks zero-arg super()
        super(PipelineEvent, cls).__init_subclass__(**kwargs)
        # Skip registration for intermediate bases (leading underscore)
        if cls.__name__.startswith("_"):
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


# -- Test event (prototype verification) --------------------------------------


@dataclass(frozen=True, slots=True)
class PipelineStarted(PipelineEvent):
    """Emitted when a pipeline run begins."""

    pass
