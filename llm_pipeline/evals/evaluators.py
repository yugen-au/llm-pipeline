"""
Auto field-match evaluators for pydantic-evals integration.

FieldMatchEvaluator: per-field equality check, self-skipping when expected is absent.
build_auto_evaluators: zero-config generator returning one evaluator per model field.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List

from pydantic_evals.evaluators import Evaluator


@dataclass(repr=False)
class FieldMatchEvaluator(Evaluator):
    """Evaluator that checks a single field matches between output and expected.

    Skips (returns empty dict) when expected_output is None or field not present.
    """

    field_name: str = ""

    def evaluate(self, ctx: Any) -> bool | dict:
        expected = ctx.expected_output
        if expected is None:
            return {}

        if isinstance(expected, dict):
            if self.field_name not in expected:
                return {}
            expected_val = expected[self.field_name]
        elif hasattr(expected, self.field_name):
            expected_val = getattr(expected, self.field_name)
        else:
            return {}

        output_val = getattr(ctx.output, self.field_name, None)
        if output_val is None and isinstance(ctx.output, dict):
            output_val = ctx.output.get(self.field_name)

        return output_val == expected_val


def build_auto_evaluators(instructions_cls: type) -> List[FieldMatchEvaluator]:
    """Build one FieldMatchEvaluator per field on a Pydantic model class."""
    fields = getattr(instructions_cls, "model_fields", {})
    return [FieldMatchEvaluator(field_name=f) for f in fields.keys()]


__all__ = ["FieldMatchEvaluator", "build_auto_evaluators"]
