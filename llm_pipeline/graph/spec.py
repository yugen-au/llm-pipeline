"""Back-compat re-exports for the legacy ``graph.spec`` module.

The legacy ``PipelineSpec`` / ``NodeSpec`` / ``PromptSpec`` /
``ToolSpec`` and the ``build_pipeline_spec`` / ``derive_issues`` /
``is_runnable`` helpers were retired with the per-artifact migration.
The new ``PipelineSpec`` lives in :mod:`llm_pipeline.specs.pipelines`;
validation types live in :mod:`llm_pipeline.specs.validation`. This
module re-exports the names that survived so existing imports keep
working until callers update.
"""
from __future__ import annotations

from llm_pipeline.specs.pipelines import EdgeSpec, SourceSpec, WiringSpec
from llm_pipeline.specs.validation import (
    ValidationIssue,
    ValidationLocation,
    ValidationSummary,
)

__all__ = [
    "EdgeSpec",
    "SourceSpec",
    "ValidationIssue",
    "ValidationLocation",
    "ValidationSummary",
    "WiringSpec",
]
