"""``ToolSpec`` — :class:`AgentTool` subclasses.

Each ``tools/foo.py`` declares an :class:`llm_pipeline.agent_tool.AgentTool`
subclass with nested ``Inputs`` (StepInputs) and ``Args`` (BaseModel)
classes plus a ``run`` classmethod. Steps bind tools via
``DEFAULT_TOOLS``; the walker registers each tool in
``registries[KIND_TOOL]``.
"""
from __future__ import annotations

from typing import Literal

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.artifacts.fields import FieldRef, FieldsBase
from llm_pipeline.artifacts.kinds import KIND_TOOL


__all__ = ["ToolFields", "ToolSpec"]


class ToolSpec(ArtifactSpec):
    """An ``AgentTool`` subclass declared in ``llm_pipelines/tools/``."""

    kind: Literal[KIND_TOOL] = KIND_TOOL  # type: ignore[assignment]

    # Pydantic Inputs class shape — pipeline-side data the tool needs.
    inputs: JsonSchemaWithRefs | None = None

    # Pydantic Args class shape — what the LLM passes per call. Drives
    # the tool schema sent to the model.
    args: JsonSchemaWithRefs | None = None

    # Body of ``run(cls, inputs, args, ctx)``.
    body: CodeBodySpec | None = None


class ToolFields(FieldsBase):
    """Routing-key vocabulary for :class:`ToolSpec` issue captures."""

    SPEC_CLS = ToolSpec

    INPUTS = FieldRef("inputs")
    ARGS = FieldRef("args")
    BODY = FieldRef("body")
