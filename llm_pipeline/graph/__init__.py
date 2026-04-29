"""Pydantic-graph-native pipeline orchestration.

Public API for declaring pipelines as ``pydantic_graph.Graph`` instances.
Three node kinds are siblings in the graph:

- ``LLMStepNode`` — calls a Phoenix-resolved prompt and writes its
  validated instructions output to ``state.outputs``.
- ``ExtractionNode`` — reads a step's output, produces SQLModel rows,
  persists them, and writes them to ``state.extractions``.
- ``ReviewNode`` — pause-point for human review (Phase 2 wires the
  pause via the persistence backend).

A pipeline subclass declares ``INPUT_DATA``, ``nodes`` (the node
classes that make up the graph), and an optional ``start_node``. The
class-level validator runs at ``__init_subclass__`` and enforces the
"if it compiles, it works" contract: every ``FromOutput(StepCls,
field=X)`` resolves against ``StepCls.INSTRUCTIONS.model_fields``;
every edge target is in ``nodes``; naming conventions hold; the graph
is acyclic; ``FromInput`` paths resolve against ``INPUT_DATA``.

Adapter machinery (``Bind``, ``SourcesSpec``, ``FromInput``,
``FromOutput``, ``FromPipeline``, ``Computed``, ``StepInputs``) is
re-exported from ``llm_pipeline.wiring`` and ``llm_pipeline.inputs``
so user code only imports from ``llm_pipeline.graph``.
"""
from __future__ import annotations

from llm_pipeline.graph.nodes import (
    ExtractionNode,
    LLMStepNode,
    PipelineDeps,
    ReviewNode,
)
from llm_pipeline.graph.pipeline import Pipeline, PipelineEnd
from llm_pipeline.graph.runtime import run_pipeline_in_memory
from llm_pipeline.graph.state import PipelineState
from llm_pipeline.inputs import PipelineInputData, StepInputs
from llm_pipeline.wiring import (
    Bind,
    Computed,
    FromInput,
    FromOutput,
    FromPipeline,
    SourcesSpec,
)

__all__ = [
    # Node base classes
    "LLMStepNode",
    "ExtractionNode",
    "ReviewNode",
    # Pipeline base class + result type
    "Pipeline",
    "PipelineEnd",
    # State + deps
    "PipelineState",
    "PipelineDeps",
    # Runtime
    "run_pipeline_in_memory",
    # Re-exports for convenience (so user code only imports from llm_pipeline.graph)
    "PipelineInputData",
    "StepInputs",
    "Bind",
    "Computed",
    "FromInput",
    "FromOutput",
    "FromPipeline",
    "SourcesSpec",
]
