"""Stub — Phase 3b will rewrite the meta-pipeline's prompt seeds.

The legacy module declared a sentiment-analysis exemplar (built on
``LLMStep`` + ``step_definition``) and a ``_seed_prompts`` helper
that pushed creator templates into the local ``prompts`` table on
boot. Phoenix now owns prompts; the meta-pipeline rewrite (Phase 3b)
will re-shape the exemplars as graph ``LLMStepNode`` subclasses and
seed via the existing Phoenix migration script.
"""
from __future__ import annotations

FRAMEWORK_REFERENCE = ""


def _seed_prompts(cls: type, engine: object) -> None:
    """No-op until Phase 3b. Phoenix owns prompts now."""
    del cls, engine


__all__ = ["FRAMEWORK_REFERENCE", "_seed_prompts"]
