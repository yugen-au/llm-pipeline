"""
Validator factories for pydantic-ai output_validator decorators.

Provides not_found_validator() and array_length_validator() which return
callables compatible with agent.output_validator(). Each factory closes
over its config at build time; per-call data is read from ctx.deps at
execution time.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic_ai import ModelRetry, RunContext

from llm_pipeline.agent_builders import StepDeps

DEFAULT_NOT_FOUND_INDICATORS: list[str] = [
    "not found",
    "no data",
    "n/a",
    "none",
    "not available",
    "not provided",
    "unknown",
    "no information",
]

_NUMBER_PREFIX_RE = re.compile(r"^\d+\.\s*")


def _strip_number_prefix(value: str) -> str:
    """Strip leading 'N. ' numeric prefix from a string."""
    return _NUMBER_PREFIX_RE.sub("", value)


def not_found_validator(
    indicators: list[str] | None = None,
) -> Any:
    """Factory: returns an output validator that checks for LLM evasion phrases.

    If indicators is None, uses DEFAULT_NOT_FOUND_INDICATORS.
    Non-string outputs pass through unchanged.
    """
    effective = indicators if indicators is not None else DEFAULT_NOT_FOUND_INDICATORS

    async def _not_found_validator(
        ctx: RunContext[StepDeps], output: Any
    ) -> Any:
        if not isinstance(output, str):
            return output
        lower = output.lower()
        for phrase in effective:
            if phrase.lower() in lower:
                raise ModelRetry(f"Response indicates not found: {output!r}")
        return output

    _not_found_validator.__name__ = "not_found_validator"
    _not_found_validator.__qualname__ = "not_found_validator"
    return _not_found_validator


def array_length_validator() -> Any:
    """Factory: returns an output validator for array length and ordering.

    Reads config from ctx.deps.array_validation at call time.
    No-op when ctx.deps.array_validation is None (agent is built once
    per step but may run multiple calls with different configs).

    Behavior:
    - Length mismatch: raises ModelRetry
    - allow_reordering: silently reorders items via model_copy
    - strip_number_prefix: strips leading "N. " when matching
    """

    async def _array_length_validator(
        ctx: RunContext[StepDeps], output: Any
    ) -> Any:
        config = ctx.deps.array_validation
        if config is None:
            return output

        if not config.array_field_name:
            raise ValueError(
                "ArrayValidationConfig.array_field_name must be set "
                "when using array_length_validator"
            )

        items = getattr(output, config.array_field_name)
        input_array = config.input_array

        # Filter empty inputs if configured
        if config.filter_empty_inputs:
            input_array = [x for x in input_array if x]

        # Length check
        if len(items) != len(input_array):
            raise ModelRetry(
                f"Expected {len(input_array)} items, got {len(items)}"
            )

        # Reorder if configured
        if config.allow_reordering and items:
            reordered = _reorder_items(
                items, input_array, config.match_field, config.strip_number_prefix
            )
            output = output.model_copy(
                update={config.array_field_name: reordered}
            )

        return output

    _array_length_validator.__name__ = "array_length_validator"
    _array_length_validator.__qualname__ = "array_length_validator"
    return _array_length_validator


def _reorder_items(
    items: list[Any],
    input_array: list[Any],
    match_field: str,
    strip_prefix: bool,
) -> list[Any]:
    """Reorder items to match input_array order using match_field.

    Builds a lookup from match_field values to items, then iterates
    input_array to produce the reordered list. Unmatched inputs get
    None filtered out; unmatched items are appended at the end.
    """

    def _normalize(val: Any) -> str:
        s = str(val).strip().lower()
        if strip_prefix:
            s = _strip_number_prefix(s)
        return s

    # Build lookup: normalized match_field value -> item
    lookup: dict[str, Any] = {}
    for item in items:
        raw = getattr(item, match_field, None)
        if raw is not None:
            lookup[_normalize(raw)] = item

    reordered: list[Any] = []
    used: set[str] = set()
    for inp in input_array:
        key = _normalize(inp)
        if key in lookup and key not in used:
            reordered.append(lookup[key])
            used.add(key)

    # Append any items not matched (preserve them rather than drop)
    for item in items:
        raw = getattr(item, match_field, None)
        if raw is not None:
            key = _normalize(raw)
            if key not in used:
                reordered.append(item)
                used.add(key)

    return reordered


__all__ = [
    "not_found_validator",
    "array_length_validator",
    "DEFAULT_NOT_FOUND_INDICATORS",
]
