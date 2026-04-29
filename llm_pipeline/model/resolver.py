"""Shared model resolution for pipeline steps.

Resolves the effective model for a step using the three-tier precedence:

1. DB override: ``StepModelConfig`` row keyed by ``(pipeline_name, step_name)``
   — set via the pipelines UI, wins over everything.
2. Step definition: ``step_def.model`` — either per-use (call-site arg on
   ``create_definition``) or the ``@step_definition(model=...)`` decorator
   default.
3. Pipeline default: the pipeline's ``_default_model`` class attribute.

This ordering is canonical and matches ``PipelineConfig._resolve_step_model``.
The module is DB-session-typed (not pipeline-typed) so it can be reused
from the pipeline runtime, the UI endpoint, and the eval runner.
"""
from __future__ import annotations

from typing import Any, Optional, Protocol

from sqlmodel import Session, select

from llm_pipeline.db.step_config import StepModelConfig


class _StepDefLike(Protocol):
    """Duck-typed shape of objects accepted by the resolver."""

    step_name: str
    model: Optional[str]


ResolutionSource = str  # Literal["db", "step_definition", "pipeline_default", "none"]


def resolve_model_from_step_def(
    step_def: _StepDefLike,
) -> Optional[str]:
    """Return the step-definition model (tier 1) or ``None``.

    Pure read — no DB access. Covers only the tier-1 slot on a
    ``StepDefinition``; callers needing fallback across tiers 2/3 should
    use ``resolve_model_with_fallbacks``.
    """
    return getattr(step_def, "model", None)


def resolve_model_with_fallbacks(
    step_def: _StepDefLike,
    session: Session,
    pipeline_name: str,
    pipeline_default_model: Optional[str],
) -> tuple[Optional[str], ResolutionSource]:
    """Resolve effective step model across all three tiers.

    Canonical precedence (matches ``PipelineConfig._resolve_step_model``):

    1. ``StepModelConfig`` DB row for ``(pipeline_name, step_def.step_name)``
    2. ``step_def.model``
    3. ``pipeline_default_model``

    Args:
        step_def: ``StepDefinition`` (reads ``step_name`` and ``model``).
        session: SQLModel ``Session`` for the DB lookup at tier 2.
        pipeline_name: Pipeline scope for the tier-2 lookup. Must match the
            ``pipeline_name`` column on ``StepModelConfig`` rows.
        pipeline_default_model: Pipeline-level fallback (tier 3). Pass
            ``None`` when no pipeline default is configured.

    Returns:
        Tuple of ``(model, source)`` where ``source`` is one of
        ``"db" | "step_definition" | "pipeline_default" | "none"``. ``model``
        is ``None`` iff ``source == "none"``.
    """
    # Tier 2: DB override wins
    row = session.exec(
        select(StepModelConfig).where(
            StepModelConfig.pipeline_name == pipeline_name,
            StepModelConfig.step_name == step_def.step_name,
        )
    ).first()
    if row is not None:
        return row.model, "db"

    # Tier 1: step definition
    step_model = getattr(step_def, "model", None)
    if step_model:
        return step_model, "step_definition"

    # Tier 3: pipeline default
    if pipeline_default_model:
        return pipeline_default_model, "pipeline_default"

    return None, "none"


__all__ = [
    "resolve_model_from_step_def",
    "resolve_model_with_fallbacks",
    "ResolutionSource",
]
