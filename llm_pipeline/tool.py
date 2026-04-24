"""Declarative pipeline tools.

A ``PipelineTool`` is a first-class bindable unit that a step's LLM
agent can invoke during execution. Tools are to agent tool-use what
``PipelineExtraction`` is to post-step data extraction: they declare
their own inputs, their own LLM-facing args, and run via a
classmethod the framework can dispatch.

Two declaration surfaces:

* ``Inputs``: a ``StepInputs`` subclass listing pipeline-side data
  needed by the tool (plain fields + resources). Resolved once per
  step run by the framework before the tool is exposed to the LLM.
* ``Args``: a ``pydantic.BaseModel`` describing what the LLM passes
  each time it calls the tool. Drives the pydantic-ai tool schema.

The ``run()`` classmethod takes both plus ambient context and returns
whatever the LLM should see as the call result (any value pydantic-ai
can serialise).

Why classmethod (not instance method):

* Tools can be invoked many times in one step run; classmethod makes
  clear that no per-call state persists on the tool itself
* Cross-call state belongs in a ``Resource`` — explicit, typed,
  shared fixture with a documented build recipe
* Trivially unit-testable: ``MyTool.run(inputs, args, ctx)`` with no
  agent / step / pipeline setup

Strategy wires tools symmetrically with extractions — a step's Bind
carries a ``tools=[Bind(tool=..., inputs=...), ...]`` list. Variants
add, drop, or re-wire tools by editing that list; no "source agent"
to mutate. Steps can declare default tools via
``@step_definition(..., tools=[...])`` which the strategy may
override per binding.
"""
from __future__ import annotations

import re
from typing import Any, ClassVar

from pydantic import BaseModel

from llm_pipeline.inputs import StepInputs
from llm_pipeline.runtime import PipelineContext

__all__ = ["PipelineTool"]


_TOOL_INPUTS_PATTERN = re.compile(r"^Inputs$")
_TOOL_ARGS_PATTERN = re.compile(r"^Args$")


class PipelineTool:
    """Base class for declarative pipeline tools.

    Subclasses must define:

    * ``Inputs``: a ``StepInputs`` subclass (fields + resources) —
      what the tool needs from the pipeline side. Resolved once per
      step run.
    * ``Args``: a ``pydantic.BaseModel`` — what the LLM passes per
      call. Used to derive the tool schema.
    * ``run(cls, inputs, args, ctx) -> Any``: classmethod that
      executes the tool with the resolved pipeline-side inputs, the
      LLM-provided args, and the ambient pipeline context.

    The class-creation hook validates the ``Inputs`` / ``Args``
    contract so authors get loud errors at import rather than
    runtime surprises.
    """

    Inputs: ClassVar[type[StepInputs]]
    Args: ClassVar[type[BaseModel]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

        # Allow intermediate abstract subclasses without Inputs/Args set —
        # validate only when both are present on the leaf class.
        inputs_attr = cls.__dict__.get("Inputs")
        args_attr = cls.__dict__.get("Args")

        if inputs_attr is None and args_attr is None:
            return

        if inputs_attr is None:
            raise TypeError(
                f"{cls.__name__} defines Args but not Inputs; every "
                f"PipelineTool must declare both an Inputs (StepInputs "
                f"subclass) and an Args (pydantic BaseModel) nested class."
            )
        if args_attr is None:
            raise TypeError(
                f"{cls.__name__} defines Inputs but not Args; every "
                f"PipelineTool must declare both an Inputs (StepInputs "
                f"subclass) and an Args (pydantic BaseModel) nested class."
            )

        if not (isinstance(inputs_attr, type) and issubclass(inputs_attr, StepInputs)):
            raise TypeError(
                f"{cls.__name__}.Inputs must be a StepInputs subclass "
                f"(got {inputs_attr!r}). Pipeline-side data declarations "
                f"share the StepInputs machinery so the Resource(...) "
                f"field marker and .sources() adapter work uniformly."
            )

        if not (isinstance(args_attr, type) and issubclass(args_attr, BaseModel)):
            raise TypeError(
                f"{cls.__name__}.Args must be a pydantic BaseModel "
                f"subclass (got {args_attr!r}). Args drives the pydantic-ai "
                f"tool schema presented to the LLM."
            )

        # Naming enforcement keeps the surface obvious at the call site.
        if not _TOOL_INPUTS_PATTERN.match(inputs_attr.__name__):
            raise TypeError(
                f"{cls.__name__}.Inputs must be named 'Inputs' "
                f"(got {inputs_attr.__name__!r})."
            )
        if not _TOOL_ARGS_PATTERN.match(args_attr.__name__):
            raise TypeError(
                f"{cls.__name__}.Args must be named 'Args' "
                f"(got {args_attr.__name__!r})."
            )

    @classmethod
    def run(
        cls,
        inputs: StepInputs,
        args: BaseModel,
        ctx: PipelineContext,
    ) -> Any:
        """Execute the tool.

        Subclasses must override. The concrete signature should narrow
        ``inputs`` to ``cls.Inputs`` and ``args`` to ``cls.Args``. The
        return value is surfaced to the LLM as the tool-call result —
        any type pydantic-ai can serialise is fine (``str``, ``dict``,
        ``BaseModel``, etc.).
        """
        raise NotImplementedError(
            f"{cls.__name__}.run must be implemented by subclasses"
        )
