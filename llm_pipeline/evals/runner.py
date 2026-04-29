"""Eval runner — stubbed pending pydantic-evals migration.

The legacy runner drove ``PipelineConfig.execute`` over a sandbox
copy of the registered pipeline, mutating per-variant prompts +
models, then stored ``EvaluationCaseResult`` rows. The pydantic-graph
migration retired ``PipelineConfig``; the eval system migration to
``pydantic_evals.Dataset.evaluate(task=run_pipeline_with_input)`` is
out of scope for the graph migration but tracked as a follow-up.

This module preserves the import surface
(``EvalRunner``, ``_phoenix_latest_version_id``,
``_build_run_snapshot``, etc.) but every public method raises
``NotImplementedError`` so an eval invocation surfaces a clear error
instead of silently malfunctioning.
"""
from __future__ import annotations

from typing import Any, Optional


_NOT_IMPLEMENTED_MESSAGE = (
    "Eval system rewrite pending. The pydantic-graph migration retired "
    "the legacy PipelineConfig.execute path the runner depended on. "
    "Track at: pydantic-evals + Phoenix Datasets follow-up."
)


def _phoenix_latest_version_id(prompt_name: str) -> Optional[str]:
    """Stub — used to be Phoenix latest-version lookup for snapshotting."""
    del prompt_name
    return None


class EvalRunner:
    """Stub. The full implementation is migrated in a follow-up."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)


def _build_run_snapshot(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)


def _build_step_target_snapshot(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)


def _build_pipeline_target_snapshot(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)


def _apply_variant_to_sandbox(*args: Any, **kwargs: Any) -> Any:
    raise NotImplementedError(_NOT_IMPLEMENTED_MESSAGE)


__all__ = [
    "EvalRunner",
    "_phoenix_latest_version_id",
    "_build_run_snapshot",
    "_build_step_target_snapshot",
    "_build_pipeline_target_snapshot",
    "_apply_variant_to_sandbox",
]
