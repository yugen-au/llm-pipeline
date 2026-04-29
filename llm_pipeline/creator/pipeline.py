"""Stub — Phase 3b will rebuild against graph ``Pipeline`` shape.

The legacy module declared ``StepCreatorPipeline`` as a
``PipelineConfig`` + ``PipelineStrategy`` + ``LLMStep`` orchestration.
The pydantic-graph migration retired all three; the meta-pipeline
will be re-shaped as a graph (``CodeGenerationStep ->
CodeValidationStep -> ...``) in a follow-up.
"""
from __future__ import annotations

from typing import Any

_NOT_IMPLEMENTED = (
    "Creator (meta-pipeline) rewrite pending. The pydantic-graph "
    "migration retired the PipelineConfig + PipelineStrategy + "
    "@step_definition stack the creator generated against. Phase 3b "
    "rebuilds against LLMStepNode + Pipeline.nodes."
)


class StepCreatorPipeline:
    """Stub. Phase 3b reimplements against the graph shape."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError(_NOT_IMPLEMENTED)


__all__ = ["StepCreatorPipeline"]
