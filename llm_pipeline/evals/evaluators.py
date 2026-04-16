"""
Auto field-match evaluators for pydantic-evals integration.

FieldMatchEvaluator: per-field equality check, self-skipping when expected is absent.
build_auto_evaluators: zero-config generator returning one evaluator per model field.
"""
from __future__ import annotations

from typing import Any, List


class FieldMatchEvaluator:
    """Evaluator that checks a single field matches between output and expected.

    Returns {} (skip) when expected is None or field not present in expected.
    Returns bool result otherwise.
    """

    def __init__(self, field_name: str):
        self.field_name = field_name

    def __repr__(self) -> str:
        return f"FieldMatchEvaluator({self.field_name!r})"

    def __call__(self, output: Any, expected: Any) -> dict | bool:
        """Compare output.field_name against expected[field_name].

        Args:
            output: step output (Pydantic model instance or object with attrs)
            expected: dict or None

        Returns:
            {} if expected is None or field absent from expected (skip).
            True if values match, False otherwise.
        """
        if expected is None:
            return {}

        # Support both dict and object expected
        if isinstance(expected, dict):
            if self.field_name not in expected:
                return {}
            expected_val = expected[self.field_name]
        elif hasattr(expected, self.field_name):
            expected_val = getattr(expected, self.field_name)
        else:
            return {}

        output_val = getattr(output, self.field_name, None)
        return output_val == expected_val


def build_auto_evaluators(instructions_cls: type) -> List[FieldMatchEvaluator]:
    """Build one FieldMatchEvaluator per field on a Pydantic model class.

    Args:
        instructions_cls: Pydantic BaseModel subclass (the step's instructions type)

    Returns:
        List of FieldMatchEvaluator, one per model_fields key.
    """
    fields = getattr(instructions_cls, "model_fields", {})
    return [FieldMatchEvaluator(f) for f in fields.keys()]


__all__ = ["FieldMatchEvaluator", "build_auto_evaluators"]
