"""``AgentTool`` — declarative pipeline-bindable LLM agent tool.

Each subclass declares ``Inputs`` (pipeline-side data, a
``StepInputs`` subclass), ``Args`` (LLM-supplied call args, a
``BaseModel``), and a ``run(cls, inputs, args, ctx)`` classmethod.
``resolve_tool_binds`` wraps subclasses into pydantic-ai-compatible
callables for ``FunctionToolset(tools=...)``.

``__init_subclass__`` validates the ``Inputs`` / ``Args`` contract.
Per the per-artifact convention, contract failures are captured
into ``_init_subclass_errors`` rather than raised — class always
constructs.
"""
from __future__ import annotations

import re
from typing import Any, ClassVar, TYPE_CHECKING

from pydantic import BaseModel

from llm_pipeline.inputs import StepInputs
from llm_pipeline.runtime import PipelineContext

if TYPE_CHECKING:
    from llm_pipeline.specs.validation import ValidationIssue

__all__ = ["AgentTool", "resolve_tool_binds"]


_TOOL_INPUTS_PATTERN = re.compile(r"^Inputs$")
_TOOL_ARGS_PATTERN = re.compile(r"^Args$")


class AgentTool:
    """Base for declarative agent tools.

    Subclasses must define:

    * ``Inputs``: a ``StepInputs`` subclass.
    * ``Args``: a ``pydantic.BaseModel`` (drives the tool schema).
    * ``run(cls, inputs, args, ctx) -> Any``: classmethod.
    """

    Inputs: ClassVar[type[StepInputs]]
    Args: ClassVar[type[BaseModel]]

    # See LLMStepNode._init_subclass_errors for the model. Empty when
    # the contract is satisfied; populated otherwise. Class always
    # constructs.
    _init_subclass_errors: ClassVar[list["ValidationIssue"]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from llm_pipeline.specs.validation import (
            ValidationIssue,
            ValidationLocation,
        )

        cls._init_subclass_errors = []

        inputs_attr = cls.__dict__.get("Inputs")
        args_attr = cls.__dict__.get("Args")

        # Allow intermediate abstract subclasses without Inputs/Args.
        if inputs_attr is None and args_attr is None:
            return

        errors: list[ValidationIssue] = []
        here = ValidationLocation(node=cls.__name__)

        if inputs_attr is None:
            errors.append(ValidationIssue(
                severity="error", code="missing_inputs",
                message=(
                    f"{cls.__name__} declares Args but not Inputs; "
                    f"every AgentTool must declare both."
                ),
                location=here,
                suggestion=(
                    f"Add a nested `class Inputs(StepInputs): ...` on "
                    f"{cls.__name__}."
                ),
            ))
        if args_attr is None:
            errors.append(ValidationIssue(
                severity="error", code="missing_args",
                message=(
                    f"{cls.__name__} declares Inputs but not Args; "
                    f"every AgentTool must declare both."
                ),
                location=here,
                suggestion=(
                    f"Add a nested `class Args(BaseModel): ...` on "
                    f"{cls.__name__}."
                ),
            ))

        if (
            inputs_attr is not None
            and not (isinstance(inputs_attr, type) and issubclass(inputs_attr, StepInputs))
        ):
            errors.append(ValidationIssue(
                severity="error", code="tool_inputs_not_stepinputs",
                message=(
                    f"{cls.__name__}.Inputs must be a StepInputs "
                    f"subclass; got {inputs_attr!r}."
                ),
                location=here,
                suggestion=(
                    "Subclass llm_pipeline.inputs.StepInputs."
                ),
            ))

        if (
            args_attr is not None
            and not (isinstance(args_attr, type) and issubclass(args_attr, BaseModel))
        ):
            errors.append(ValidationIssue(
                severity="error", code="tool_args_not_basemodel",
                message=(
                    f"{cls.__name__}.Args must be a pydantic BaseModel "
                    f"subclass; got {args_attr!r}."
                ),
                location=here,
                suggestion="Subclass pydantic.BaseModel.",
            ))

        if (
            isinstance(inputs_attr, type)
            and not _TOOL_INPUTS_PATTERN.match(inputs_attr.__name__)
        ):
            errors.append(ValidationIssue(
                severity="error", code="tool_inputs_name",
                message=(
                    f"{cls.__name__}.Inputs must be named 'Inputs' "
                    f"(got {inputs_attr.__name__!r})."
                ),
                location=here,
            ))
        if (
            isinstance(args_attr, type)
            and not _TOOL_ARGS_PATTERN.match(args_attr.__name__)
        ):
            errors.append(ValidationIssue(
                severity="error", code="tool_args_name",
                message=(
                    f"{cls.__name__}.Args must be named 'Args' "
                    f"(got {args_attr.__name__!r})."
                ),
                location=here,
            ))

        cls._init_subclass_errors = errors

    @classmethod
    def run(
        cls,
        inputs: StepInputs,
        args: BaseModel,
        ctx: PipelineContext,
    ) -> Any:
        """Execute the tool. Subclasses must override."""
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
    """Resolve tool Binds into pydantic-ai compatible callables.

    For each Bind: resolve ``Inputs`` via its SourcesSpec adapter,
    build resources, then wrap the tool into a function whose
    signature exposes ``Tool.Args`` fields. Returns callables ready
    for ``FunctionToolset(tools=...)``.
    """
    from llm_pipeline.resources import resolve_resources

    resolved: list = []
    for bind in tool_binds:
        tool_cls = bind.tool
        if bind.inputs is not None:
            tool_inputs = bind.inputs.resolve(adapter_ctx)
            resolve_resources(tool_inputs, pipeline_ctx)
        else:
            tool_inputs = tool_cls.Inputs() if tool_cls.Inputs.model_fields else None

        resolved.append(
            _make_tool_wrapper(tool_cls, tool_inputs, pipeline_ctx)
        )
    return resolved


def _make_tool_wrapper(
    tool_cls: type["AgentTool"],
    resolved_inputs: Any,
    pipeline_ctx: "PipelineContext",
):
    """Build a pydantic-ai compatible function from an AgentTool.

    The returned function's ``__signature__`` exposes the tool's
    ``Args`` fields so pydantic-ai derives the JSON schema from it.
    The closure captures resolved inputs and context.
    """
    import inspect

    from llm_pipeline.naming import to_snake_case

    args_cls = tool_cls.Args

    def wrapper(**kwargs):
        args = args_cls(**kwargs)
        return tool_cls.run(resolved_inputs, args, pipeline_ctx)

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
    wrapper.__annotations__ = {
        name: field_info.annotation
        for name, field_info in args_cls.model_fields.items()
    }

    return wrapper
