"""Evaluators for the eval system + a registry for custom user evaluators.

Three layers:

1. :class:`FieldMatchEvaluator` — generic per-field equality, the
   building block ``build_auto_evaluators`` emits one of per
   ``INSTRUCTIONS`` field.

2. :func:`build_auto_evaluators` — zero-config "auto" suite. Given an
   instructions class (or any pydantic model), returns one evaluator
   per declared field. Skips ``confidence_score`` and ``notes`` from
   :class:`LLMResultMixin` since those aren't ground-truth-comparable.

3. :func:`register_evaluator` decorator + :func:`get_evaluator` /
   :func:`list_evaluators` lookup — the runner consults these when a
   case's ``metadata["evaluators"]`` references a custom evaluator by
   name.

Evaluators are pydantic-evals ``Evaluator`` subclasses; they consume an
``EvaluatorContext`` with ``ctx.output`` (the task return) and
``ctx.expected_output`` (the case's ``expected_output``). Both can be
``dict`` or pydantic-model — the helpers below normalise.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List

from pydantic_evals.evaluators import Evaluator, EvaluatorContext


# ---------------------------------------------------------------------------
# FieldMatchEvaluator
# ---------------------------------------------------------------------------


# Skip-list — these fields live on every LLMResultMixin subclass but
# aren't part of the ground-truth schema, so auto-evaluators emitted
# from a pipeline's INSTRUCTIONS shouldn't compare them.
_AUTO_EVAL_SKIP_FIELDS = frozenset({"confidence_score", "notes"})


def _read_field(obj: Any, field_name: str) -> tuple[bool, Any]:
    """Return ``(present, value)`` for ``field_name`` on a dict or model."""
    if isinstance(obj, dict):
        if field_name in obj:
            return True, obj[field_name]
        return False, None
    if hasattr(obj, field_name):
        return True, getattr(obj, field_name)
    return False, None


@dataclass(repr=False)
class FieldMatchEvaluator(Evaluator):
    """Per-field equality between task ``output`` and case ``expected_output``.

    Returns ``{field_name: bool}`` so each field's evaluation lands as
    a separate assertion in the pydantic-evals report. Self-skips
    (returns ``{}`` — pydantic-evals treats this as "no result") when
    the field is missing on the expected side.
    """

    field_name: str = ""
    label: str | None = None

    def evaluate(self, ctx: EvaluatorContext[Any, Any, Any]) -> dict[str, bool]:
        expected = ctx.expected_output
        if expected is None:
            return {}

        has_expected, expected_val = _read_field(expected, self.field_name)
        if not has_expected:
            return {}

        _, output_val = _read_field(ctx.output, self.field_name)
        return {self.label or self.field_name: output_val == expected_val}


def build_auto_evaluators(instructions_cls: type) -> List[FieldMatchEvaluator]:
    """One ``FieldMatchEvaluator`` per declared field on ``instructions_cls``.

    Skips :class:`LLMResultMixin`'s ``confidence_score`` / ``notes`` —
    those are operational fields, not ground-truth-comparable. The
    runner appends the auto-evaluator suite to whatever per-case
    custom evaluators the dataset declares.
    """
    fields = getattr(instructions_cls, "model_fields", {}) or {}
    return [
        FieldMatchEvaluator(field_name=name)
        for name in fields
        if name not in _AUTO_EVAL_SKIP_FIELDS
    ]


# ---------------------------------------------------------------------------
# Custom evaluator registry
# ---------------------------------------------------------------------------


_EVALUATOR_REGISTRY: dict[str, type[Evaluator]] = {}


def register_evaluator(
    name: str | None = None,
) -> Callable[[type[Evaluator]], type[Evaluator]]:
    """Decorator: register an :class:`Evaluator` subclass under ``name``.

    The runner looks up custom evaluators referenced in a case's
    ``metadata["evaluators"]`` list against this registry. Default
    name is ``cls.__name__``.

    Example::

        @register_evaluator(name="length_at_most_280")
        @dataclass
        class TweetLengthEvaluator(Evaluator):
            def evaluate(self, ctx):
                return len(ctx.output.get("text", "")) <= 280
    """

    def _decorate(cls: type[Evaluator]) -> type[Evaluator]:
        if not isinstance(cls, type) or not issubclass(cls, Evaluator):
            raise TypeError(
                f"@register_evaluator expects an Evaluator subclass; "
                f"got {cls!r}."
            )
        key = name or cls.__name__
        existing = _EVALUATOR_REGISTRY.get(key)
        if existing is not None and existing is not cls:
            raise ValueError(
                f"evaluator name {key!r} already registered to "
                f"{existing.__name__}; pick a unique name or unregister "
                f"the existing one first."
            )
        _EVALUATOR_REGISTRY[key] = cls
        return cls

    return _decorate


def get_evaluator(name: str) -> type[Evaluator]:
    """Look up a registered evaluator class by name. Raises ``KeyError``."""
    cls = _EVALUATOR_REGISTRY.get(name)
    if cls is None:
        raise KeyError(
            f"evaluator {name!r} not registered. "
            f"Available: {sorted(_EVALUATOR_REGISTRY)}",
        )
    return cls


def list_evaluators() -> list[str]:
    """Sorted list of registered evaluator names."""
    return sorted(_EVALUATOR_REGISTRY)


def clear_evaluator_registry() -> None:
    """Remove every registered evaluator. Test-only helper."""
    _EVALUATOR_REGISTRY.clear()


def build_case_evaluators(
    instructions_cls: type | None,
    custom_names: list[str] | None,
) -> list[Evaluator]:
    """Compose the per-case evaluator list: auto + custom (by name).

    ``instructions_cls`` is optional — pipeline-level evals don't have
    a single instructions class to auto-generate from. In that case
    only the custom evaluators apply.
    """
    auto: list[Evaluator] = (
        build_auto_evaluators(instructions_cls) if instructions_cls else []
    )
    custom: list[Evaluator] = []
    for name in custom_names or []:
        cls = get_evaluator(name)
        custom.append(cls())
    return [*auto, *custom]


__all__ = [
    "FieldMatchEvaluator",
    "build_auto_evaluators",
    "build_case_evaluators",
    "register_evaluator",
    "get_evaluator",
    "list_evaluators",
    "clear_evaluator_registry",
]
