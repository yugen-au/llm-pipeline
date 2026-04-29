"""Stub — Phase 3b will rebuild creator steps as ``LLMStepNode`` subclasses.

The legacy module declared 4 ``@step_definition``-decorated steps
(``RequirementsAnalysisStep``, ``CodeGenerationStep``,
``PromptGenerationStep``, ``CodeValidationStep``) plus a
``GenerationRecordExtraction`` ``PipelineExtraction`` subclass. The
pydantic-graph migration retired the legacy bases; the meta-pipeline
will be re-shaped as a graph in a follow-up.
"""
from __future__ import annotations

from typing import Any

_NOT_IMPLEMENTED = (
    "Creator step rewrites pending. The pydantic-graph migration "
    "retired @step_definition + LLMStep + PipelineExtraction. "
    "Phase 3b rebuilds these as graph nodes."
)


class _StubStep:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise NotImplementedError(_NOT_IMPLEMENTED)


class RequirementsAnalysisStep(_StubStep):
    pass


class CodeGenerationStep(_StubStep):
    pass


class PromptGenerationStep(_StubStep):
    pass


class CodeValidationStep(_StubStep):
    pass


class GenerationRecordExtraction(_StubStep):
    pass


__all__ = [
    "RequirementsAnalysisStep",
    "CodeGenerationStep",
    "PromptGenerationStep",
    "CodeValidationStep",
    "GenerationRecordExtraction",
]
