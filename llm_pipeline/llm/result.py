"""LLM call result dataclass for structured capture of LLM responses."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class LLMCallResult:
    """Immutable record of a single LLM call's outcome.

    Captures parsed output, raw response text, model metadata, and any
    validation errors encountered during response processing.

    Fields containing mutable containers (parsed dict, validation_errors list)
    must not be mutated after creation.
    """

    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)
