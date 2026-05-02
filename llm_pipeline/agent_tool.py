"""``AgentTool`` — declarative pipeline-bindable LLM agent tool.

Each subclass declares ``INPUTS`` (a ``StepInputs`` subclass holding
pipeline-side data) and ``ARGS`` (a ``BaseModel`` describing what the
LLM passes per call), plus a ``run(cls, inputs, args, ctx)``
classmethod. ``resolve_tool_binds`` wraps subclasses into
pydantic-ai-compatible callables for ``FunctionToolset(tools=...)``.

Class shape mirrors :class:`LLMStepNode` / :class:`ExtractionNode` /
:class:`ReviewNode`: UPPER_CASE ClassVars hold module-level classes,
naming convention ``{prefix}Tool`` ⇒ ``{prefix}Inputs`` /
``{prefix}Args``. ``__init_subclass__`` captures contract violations
into ``_init_subclass_errors`` rather than raising — class always
constructs.
"""
from __future__ import annotations

from typing import Any, ClassVar, TYPE_CHECKING

from pydantic import BaseModel

from llm_pipeline.inputs import StepInputs
from llm_pipeline.runtime import PipelineContext

if TYPE_CHECKING:
    from llm_pipeline.specs.validation import ValidationIssue

__all__ = ["AgentTool", "resolve_tool_binds"]


class AgentTool:
    """Base for declarative agent tools."""

    INPUTS: ClassVar[type[StepInputs]] = None  # type: ignore[assignment]
    ARGS: ClassVar[type[BaseModel]] = None  # type: ignore[assignment]

    # See LLMStepNode._init_subclass_errors for the model.
    _init_subclass_errors: ClassVar[list["ValidationIssue"]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        from llm_pipeline.specs.tools import ToolFields
        from llm_pipeline.specs.validation import (
            ValidationIssue,
            ValidationLocation,
        )

        cls._init_subclass_errors = []
        errors: list[ValidationIssue] = []

        # Naming convention.
        if not cls.__name__.endswith("Tool"):
            errors.append(ValidationIssue(
                severity="error", code="tool_name_suffix",
                message=(
                    f"AgentTool subclass {cls.__name__!r} must end with "
                    f"'Tool' suffix."
                ),
                location=ValidationLocation(node=cls.__name__),
                suggestion=f"Rename to '{cls.__name__}Tool' or similar.",
            ))

        # Required attrs.
        if cls.INPUTS is None:
            errors.append(ValidationIssue(
                severity="error", code="missing_inputs",
                message=(
                    f"{cls.__name__}.INPUTS must be set to a StepInputs "
                    f"subclass."
                ),
                location=ValidationLocation(
                    node=cls.__name__, field=ToolFields.INPUTS,
                ),
                suggestion=(
                    f"Set INPUTS = <YourInputsClass> on {cls.__name__} "
                    f"(must subclass StepInputs)."
                ),
            ))
        if cls.ARGS is None:
            errors.append(ValidationIssue(
                severity="error", code="missing_args",
                message=(
                    f"{cls.__name__}.ARGS must be set to a Pydantic "
                    f"BaseModel subclass declaring the LLM call args."
                ),
                location=ValidationLocation(
                    node=cls.__name__, field=ToolFields.ARGS,
                ),
                suggestion=(
                    f"Set ARGS = <YourArgsClass> on {cls.__name__} "
                    f"(a Pydantic BaseModel)."
                ),
            ))

        inputs_cls = cls.INPUTS
        if (
            inputs_cls is not None
            and not (isinstance(inputs_cls, type) and issubclass(inputs_cls, StepInputs))
        ):
            errors.append(ValidationIssue(
                severity="error", code="tool_inputs_not_stepinputs",
                message=(
                    f"{cls.__name__}.INPUTS must be a StepInputs "
                    f"subclass; got {inputs_cls!r}."
                ),
                location=ValidationLocation(
                    node=cls.__name__, field=ToolFields.INPUTS,
                ),
                suggestion="Subclass llm_pipeline.inputs.StepInputs.",
            ))

        args_cls = cls.ARGS
        if (
            args_cls is not None
            and not (isinstance(args_cls, type) and issubclass(args_cls, BaseModel))
        ):
            errors.append(ValidationIssue(
                severity="error", code="tool_args_not_basemodel",
                message=(
                    f"{cls.__name__}.ARGS must be a Pydantic BaseModel "
                    f"subclass; got {args_cls!r}."
                ),
                location=ValidationLocation(
                    node=cls.__name__, field=ToolFields.ARGS,
                ),
                suggestion="Subclass pydantic.BaseModel.",
            ))

        # Name-mismatch checks — only meaningful once the Tool suffix
        # is present (otherwise the prefix derivation is nonsense).
        if cls.__name__.endswith("Tool"):
            prefix = cls.__name__[: -len("Tool")]
            if isinstance(inputs_cls, type):
                expected = f"{prefix}Inputs"
                if inputs_cls.__name__ != expected:
                    errors.append(ValidationIssue(
                        severity="error", code="tool_inputs_name_mismatch",
                        message=(
                            f"{cls.__name__}.INPUTS must be named "
                            f"'{expected}', got '{inputs_cls.__name__}'."
                        ),
                        location=ValidationLocation(
                            node=cls.__name__, field=ToolFields.INPUTS,
                        ),
                        suggestion=(
                            f"Rename {inputs_cls.__name__} to {expected}."
                        ),
                    ))
            if isinstance(args_cls, type):
                expected = f"{prefix}Args"
                if args_cls.__name__ != expected:
                    errors.append(ValidationIssue(
                        severity="error", code="tool_args_name_mismatch",
                        message=(
                            f"{cls.__name__}.ARGS must be named "
                            f"'{expected}', got '{args_cls.__name__}'."
                        ),
                        location=ValidationLocation(
                            node=cls.__name__, field=ToolFields.ARGS,
                        ),
                        suggestion=(
                            f"Rename {args_cls.__name__} to {expected}."
                        ),
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

    For each Bind: resolve ``INPUTS`` via its SourcesSpec adapter,
    build resources, then wrap the tool into a function whose
    signature exposes ``ARGS`` fields. Returns callables ready
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
            tool_inputs = tool_cls.INPUTS() if tool_cls.INPUTS.model_fields else None

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
    ``ARGS`` fields so pydantic-ai derives the JSON schema from it.
    The closure captures resolved inputs and context.
    """
    import inspect

    from llm_pipeline.naming import to_snake_case

    args_cls = tool_cls.ARGS

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
    wrapper.__name__ = to_snake_case(tool_cls.__name__, strip_suffix="Tool")
    wrapper.__qualname__ = wrapper.__name__
    wrapper.__doc__ = tool_cls.__doc__ or f"Tool: {tool_cls.__name__}"
    wrapper.__annotations__ = {
        name: field_info.annotation
        for name, field_info in args_cls.model_fields.items()
    }

    return wrapper
