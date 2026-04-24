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

__all__ = ["PipelineTool", "resolve_tool_binds"]


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


# ---------------------------------------------------------------------------
# Runtime resolution: Bind list → pydantic-ai tool functions
# ---------------------------------------------------------------------------


def resolve_tool_binds(
    tool_binds: list,
    adapter_ctx: Any,
    pipeline_ctx: "PipelineContext",
) -> list:
    """Resolve a list of tool Binds into pydantic-ai compatible callables.

    For each tool Bind:
    1. Resolve the tool's ``Inputs`` via its SourcesSpec adapter.
    2. Build resource-typed fields on the resolved inputs.
    3. Wrap the tool into a function whose signature exposes
       ``Tool.Args`` fields — pydantic-ai derives the LLM-facing
       schema from this signature.

    Returns a list of callables ready for ``FunctionToolset(tools=...)``.
    """
    import inspect

    from llm_pipeline.naming import to_snake_case
    from llm_pipeline.resources import resolve_resources

    resolved: list = []
    for bind in tool_binds:
        tool_cls = bind.tool
        # Resolve tool inputs (non-resource fields via adapter, then resources)
        if bind.inputs is not None:
            tool_inputs = bind.inputs.resolve(adapter_ctx)
            resolve_resources(tool_inputs, pipeline_ctx)
        else:
            # Tool with no inputs (e.g. stateless utility)
            tool_inputs = tool_cls.Inputs() if tool_cls.Inputs.model_fields else None

        resolved.append(
            _make_tool_wrapper(tool_cls, tool_inputs, pipeline_ctx)
        )
    return resolved


def _make_tool_wrapper(
    tool_cls: type["PipelineTool"],
    resolved_inputs: Any,
    pipeline_ctx: "PipelineContext",
):
    """Build a pydantic-ai compatible function from a PipelineTool.

    The returned function's ``__signature__`` exposes the tool's ``Args``
    fields so pydantic-ai can derive the JSON schema for the LLM. The
    closure captures resolved inputs and context — the LLM only sees
    the Args-derived parameters.
    """
    import inspect

    args_cls = tool_cls.Args

    def wrapper(**kwargs):
        args = args_cls(**kwargs)
        return tool_cls.run(resolved_inputs, args, pipeline_ctx)

    # Build a signature from Args fields so pydantic-ai sees real params
    params: list[inspect.Parameter] = []
    for name, field_info in args_cls.model_fields.items():
        default = (
            field_info.default
            if field_info.default is not None
            else inspect.Parameter.empty
        )
        params.append(inspect.Parameter(
            name,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            annotation=field_info.annotation,
            default=default,
        ))

    wrapper.__signature__ = inspect.Signature(params)
    wrapper.__name__ = to_snake_case(tool_cls.__name__)
    wrapper.__qualname__ = wrapper.__name__
    wrapper.__doc__ = tool_cls.__doc__ or f"Tool: {tool_cls.__name__}"
    # Annotations dict needed by some introspection paths
    wrapper.__annotations__ = {
        name: field_info.annotation
        for name, field_info in args_cls.model_fields.items()
    }

    return wrapper
