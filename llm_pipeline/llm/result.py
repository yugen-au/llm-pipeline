"""LLM call result dataclass for structured capture of LLM responses."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
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

    # -- Serialization ---------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize result to dict with all fields."""
        return asdict(self)

    def to_json(self) -> str:
        """Serialize result to JSON string."""
        return json.dumps(self.to_dict())

    # -- Status properties -----------------------------------------------------

    @property
    def is_success(self) -> bool:
        """True when parsed output is present.

        validation_errors are diagnostic only (from prior attempts) and do
        not affect success status.
        """
        return self.parsed is not None

    @property
    def is_failure(self) -> bool:
        """True when no parsed output is present."""
        return self.parsed is None

    # -- Factory classmethods --------------------------------------------------

    @classmethod
    def success(
        cls,
        parsed: dict[str, Any],
        raw_response: str,
        model_name: str,
        attempt_count: int = 1,
        validation_errors: list[str] | None = None,
    ) -> LLMCallResult:
        """Create a successful result with non-None parsed output.

        Raises:
            ValueError: If parsed is None.
        """
        if parsed is None:
            raise ValueError("parsed must not be None for a success result")
        return cls(
            parsed=parsed,
            raw_response=raw_response,
            model_name=model_name,
            attempt_count=attempt_count,
            validation_errors=validation_errors if validation_errors is not None else [],
        )

    @classmethod
    def failure(
        cls,
        raw_response: str,
        model_name: str,
        attempt_count: int,
        validation_errors: list[str],
        parsed: None = None,
    ) -> LLMCallResult:
        """Create a failed result with no parsed output.

        An empty validation_errors list is valid for timeout or network
        failures where no validation was attempted.
        """
        return cls(
            parsed=parsed,
            raw_response=raw_response,
            model_name=model_name,
            attempt_count=attempt_count,
            validation_errors=validation_errors,
        )
