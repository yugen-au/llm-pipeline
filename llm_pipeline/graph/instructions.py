"""``LLMResultMixin`` — the framework's contract for LLM output schemas.

Every ``LLMStepNode.INSTRUCTIONS`` class must subclass this. It pins
two things on every LLM output:

- ``confidence_score: float`` (0..1, default 0.95) — surfaced by
  evaluators and the consensus engine.
- ``notes: str | None`` — free-form reasoning slot the model can
  populate.

It also runs example validation at class-creation time: if the
subclass declares an ``example: ClassVar[dict]``, the mixin's
``__init_subclass__`` calls ``cls(**cls.example)`` and raises if it
fails to validate. Schema/example drift is caught the moment the
file is imported.

The framework's compile-time validator (``graph/validator.py``)
hard-requires ``issubclass(INSTRUCTIONS, LLMResultMixin)`` — declaring
a plain ``BaseModel`` as ``INSTRUCTIONS`` is rejected.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


__all__ = ["LLMResultMixin"]


class LLMResultMixin(BaseModel):
    """Standardised LLM-output schema base.

    Every step's ``INSTRUCTIONS`` class must inherit from this so
    confidence + notes are always present and example validation
    fires at class-creation time.
    """

    confidence_score: float = Field(
        default=0.95,
        ge=0.0,
        le=1.0,
        description="Confidence in this analysis (0-1).",
    )
    notes: str | None = Field(
        default=None,
        description="General observations, reasoning, or additional context.",
    )

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Only validate when an `example` ClassVar is declared on the
        # subclass itself (not inherited). Skips intermediate
        # exampleless mixins.
        if "example" not in cls.__dict__:
            return
        example = cls.__dict__["example"]
        if not isinstance(example, dict):
            raise ValueError(
                f"{cls.__name__}.example must be a dict, "
                f"got {type(example).__name__}.",
            )
        try:
            cls(**example)
        except Exception as exc:
            raise ValueError(
                f"{cls.__name__}.example validation failed: {exc}\n"
                f"Example dict must match the class fields exactly.",
            ) from exc

    @classmethod
    def get_example(cls) -> "LLMResultMixin | None":
        """Construct an example instance from ``cls.example`` if declared."""
        example = getattr(cls, "example", None)
        if isinstance(example, dict):
            return cls(**example)
        return None

    @classmethod
    def create_failure(cls, reason: str, **safe_defaults: Any) -> "LLMResultMixin":
        """Build a failure result with confidence 0 and a notes-formatted reason."""
        return cls(
            confidence_score=0.0,
            notes=f"Failed: {reason}",
            **safe_defaults,
        )
