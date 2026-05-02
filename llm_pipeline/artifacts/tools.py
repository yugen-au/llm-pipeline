"""``ToolSpec`` — :class:`AgentTool` subclasses.

Each ``tools/foo.py`` declares an :class:`llm_pipeline.agent_tool.AgentTool`
subclass with nested ``Inputs`` (StepInputs) and ``Args`` (BaseModel)
classes plus a ``run`` classmethod. Steps bind tools via
``DEFAULT_TOOLS``; the walker registers each tool in
``registries[KIND_TOOL]``.
"""
from __future__ import annotations

from typing import Any, Literal

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.base.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.artifacts.base.builder import SpecBuilder
from llm_pipeline.artifacts.base.fields import FieldRef, FieldsBase
from llm_pipeline.artifacts.base.kinds import KIND_TOOL
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _to_registry_key,
)


__all__ = ["MANIFEST", "ToolBuilder", "ToolFields", "ToolSpec", "ToolsWalker"]


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


class ToolBuilder(SpecBuilder):
    """Build a :class:`ToolSpec` from an :class:`AgentTool` subclass.

    Reads ``cls.INPUTS`` / ``cls.ARGS`` / ``cls.run`` directly. Missing
    attrs produce ``None``-valued spec fields; the per-class capture
    model surfaces the contract violation.
    """

    KIND = KIND_TOOL
    SPEC_CLS = ToolSpec

    def kind_fields(self) -> dict[str, Any]:
        cls = self.cls
        inputs_cls = getattr(cls, "INPUTS", None)
        args_cls = getattr(cls, "ARGS", None)
        return {
            "inputs": self.json_schema(inputs_cls),
            "args": self.json_schema(args_cls),
            "body": self.code_body("run"),
        }


class ToolsWalker(Walker):
    """Register :class:`AgentTool` subclasses from ``tools/``.

    Each subclass declares ``INPUTS`` / ``ARGS`` ClassVars (paired
    StepInputs / BaseModel classes) plus a ``run`` classmethod.
    Class-level contract violations live on ``cls._init_subclass_errors``
    and flow into ``ToolSpec`` via :meth:`ArtifactSpec.attach_class_captures`.
    """

    KIND = KIND_TOOL
    BUILDER = ToolBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.agent_tool import AgentTool

        return _is_locally_defined_class(value, mod, AgentTool)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Tool")


MANIFEST = ArtifactManifest(
    kind=KIND_TOOL,
    subfolder="tools",
    level=3,
    spec_cls=ToolSpec,
    fields_cls=ToolFields,
    walker=ToolsWalker(),
)
