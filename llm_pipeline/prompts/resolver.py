"""Shared prompt key resolution for pipeline steps.

Resolves ``system_instruction_key`` / ``user_prompt_key`` for a
``StepDefinition`` using the three-tier precedence:

1. Explicit per-use (strategy call-site arg on ``create_definition``)
2. ``@step_definition(default_system_key=..., default_user_key=...)``
3. DB auto-discovery: ``{step_name}.{strategy_name}`` then ``{step_name}``

Tiers 1 and 2 are recorded on the ``StepDefinition`` at construction time,
so ``resolve_from_step_def`` is a pure read. Tier 3 needs DB access and
is only consulted when either key is still ``None``.

This module is DB-session-typed (not pipeline-typed) so it can be reused
from both the pipeline runtime (``strategy.create_step``) and HTTP handlers
(``ui.routes.pipelines.get_step_prompts``, ``ui.routes.evals.prod-prompts``).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlmodel import Session, select

from llm_pipeline.db.prompt import Prompt
from llm_pipeline.naming import to_snake_case

if TYPE_CHECKING:
    from llm_pipeline.strategy import StepDefinition


def resolve_from_step_def(
    step_def: "StepDefinition",
) -> tuple[Optional[str], Optional[str]]:
    """Return (system_key, user_key) as declared on the StepDefinition.

    Covers tiers 1 + 2: explicit call-site keys and decorator defaults both
    populate ``step_def.system_instruction_key`` / ``user_prompt_key`` at
    construction time. No DB access, no pipeline context required.

    Returns:
        Tuple of (system_key, user_key). Either element may be ``None`` when
        the corresponding tier-1/tier-2 value was not provided; callers
        needing tier-3 fallback should use ``resolve_with_auto_discovery``.
    """
    return step_def.system_instruction_key, step_def.user_prompt_key


def _lookup_prompt_key(
    session: Session, key: str, prompt_type: str
) -> Optional[str]:
    """Return ``key`` if an active Prompt row exists for (key, prompt_type), else None."""
    row = session.exec(
        select(Prompt).where(
            Prompt.prompt_key == key,
            Prompt.prompt_type == prompt_type,
            Prompt.is_active == True,  # noqa: E712 - SQLModel requires `==`
            Prompt.is_latest == True,  # noqa: E712
        )
    ).first()
    return row.prompt_key if row else None


def resolve_with_auto_discovery(
    step_def: "StepDefinition",
    session: Session,
    strategy_name: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Resolve prompt keys with tier-3 DB auto-discovery fallback.

    Behaviour:
    - Starts from ``resolve_from_step_def(step_def)``.
    - For any side still ``None``, queries the Prompt table:
        1. ``{step_name}.{strategy_name}`` (skipped when ``strategy_name`` is None)
        2. ``{step_name}``
      Returns the first matching active Prompt's ``prompt_key`` per side.
    - Per-side resolution is independent: system may resolve via tier-2
      while user resolves via tier-3.

    Args:
        step_def: The StepDefinition (reads ``step_class.__name__``).
        session: SQLModel ``Session`` for DB lookups.
        strategy_name: Current strategy's ``name`` (snake_case), or ``None``
            when the caller cannot associate a strategy (e.g. step-targeted
            eval without strategy binding).

    Returns:
        Tuple of (system_key, user_key). Either element may still be
        ``None`` if no declared key exists and no matching Prompt is found.
    """
    system_key, user_key = resolve_from_step_def(step_def)
    if system_key is not None and user_key is not None:
        return system_key, user_key

    step_class_name = step_def.step_class.__name__
    step_name = to_snake_case(step_class_name, strip_suffix="Step")

    # Tier 3a: strategy-level key (only when strategy_name known)
    if strategy_name:
        strategy_key = f"{step_name}.{strategy_name}"
        if system_key is None:
            system_key = _lookup_prompt_key(session, strategy_key, "system")
        if user_key is None:
            user_key = _lookup_prompt_key(session, strategy_key, "user")

    # Tier 3b: step-level key
    if system_key is None:
        system_key = _lookup_prompt_key(session, step_name, "system")
    if user_key is None:
        user_key = _lookup_prompt_key(session, step_name, "user")

    return system_key, user_key


__all__ = ["resolve_from_step_def", "resolve_with_auto_discovery"]
