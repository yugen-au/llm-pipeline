"""Adapter source types + per-node binding dataclasses for pipeline wiring.

Sources describe how a node's inputs are assembled from pipeline input,
prior node outputs, or pipeline-level attributes at adapter-resolve
time. The closed set is: ``FromInput``, ``FromOutput``, ``FromPipeline``,
``Computed``.

Per-node bindings (``Step``, ``Extraction``, ``Review``) pair a node
class with a ``SourcesSpec`` describing how its inputs are sourced.
``Pipeline.nodes`` is a list of these wrappers — wiring is fully
pipeline-level, never on the node class.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass
from types import UnionType
from typing import Any, Callable

from pydantic import BaseModel

__all__ = [
    "AdapterContext",
    "Computed",
    "Extraction",
    "FromInput",
    "FromOutput",
    "FromPipeline",
    "Review",
    "Source",
    "SourcesSpec",
    "Step",
]


@dataclass
class AdapterContext:
    """Runtime context passed to ``Source.resolve()``."""
    input: Any
    outputs: dict[type, list[Any]]
    pipeline: Any


class Source:
    """Abstract base for adapter source types."""

    def resolve(self, ctx: AdapterContext) -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class FromInput(Source):
    """Reads a field from the validated pipeline input.

    ``path`` supports dotted access (e.g. ``"user.email"``).
    """
    path: str

    def resolve(self, ctx: AdapterContext) -> Any:
        value: Any = ctx.input
        for part in self.path.split("."):
            value = getattr(value, part)
        return value


@dataclass(frozen=True)
class FromOutput(Source):
    """Reads a prior step's output.

    By default, returns the first call's instructions instance. Pass
    ``index`` to select a different call. Pass ``field`` to return a
    specific field of the instructions instance.
    """
    step_cls: type
    index: int = 0
    field: str | None = None

    def resolve(self, ctx: AdapterContext) -> Any:
        outputs = ctx.outputs.get(self.step_cls)
        if not outputs:
            raise KeyError(
                f"FromOutput: no outputs recorded for step "
                f"{self.step_cls.__name__}"
            )
        try:
            instance = outputs[self.index]
        except IndexError as exc:
            raise IndexError(
                f"FromOutput: step {self.step_cls.__name__} has "
                f"{len(outputs)} output(s); index {self.index} is out of range"
            ) from exc
        if self.field is not None:
            return getattr(instance, self.field)
        return instance


@dataclass(frozen=True)
class FromPipeline(Source):
    """Reads an ambient pipeline attribute (e.g. ``session``, ``logger``)."""
    attr: str

    def resolve(self, ctx: AdapterContext) -> Any:
        return getattr(ctx.pipeline, self.attr)


class Computed(Source):
    """Deferred function call: sources resolve first, then ``fn(*resolved)``.

    Use sparingly — only when the consuming step/extraction cannot do
    the computation itself given its declared inputs.
    """
    __slots__ = ("fn", "sources")

    def __init__(self, fn: Callable[..., Any], *sources: Source) -> None:
        self.fn = fn
        self.sources = sources

    def resolve(self, ctx: AdapterContext) -> Any:
        resolved = [s.resolve(ctx) for s in self.sources]
        return self.fn(*resolved)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Computed):
            return NotImplemented
        return self.fn is other.fn and self.sources == other.sources

    def __hash__(self) -> int:
        return hash((id(self.fn), self.sources))

    def __repr__(self) -> str:
        name = getattr(self.fn, "__name__", repr(self.fn))
        return f"Computed({name}, {list(self.sources)!r})"


@dataclass
class SourcesSpec:
    """Return value of ``{InputsCls}.sources(...)``.

    Carries the target inputs class and the declared source per field.
    At adapter resolve time, each source materializes and the inputs
    class is constructed (with Pydantic validation).
    """
    inputs_cls: type
    field_sources: dict[str, Source]

    def resolve(self, ctx: AdapterContext) -> Any:
        resolved = {
            name: source.resolve(ctx)
            for name, source in self.field_sources.items()
        }
        return self.inputs_cls(**resolved)


# ---------------------------------------------------------------------------
# Per-node bindings: Step / Extraction / Review
# ---------------------------------------------------------------------------


def _validate_binding_post_init(
    binding: Any, kind: str,
) -> list[Any]:
    """Capture binding-level wiring errors as ``ValidationIssue`` records.

    Used by ``Step`` / ``Extraction`` / ``Review`` ``__post_init__`` to
    avoid raising on framework-rule violations. Class always
    constructs; the issues are stored on the binding instance and
    aggregated into the pipeline spec by
    ``Pipeline.__init_subclass__``.

    Returns the list of issues so the caller can stash it on
    ``self._init_post_errors``. ``kind`` is the wrapper-class name
    used in error messages (e.g. ``"Step"``).
    """
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    issues: list[ValidationIssue] = []
    cls_repr = (
        binding.cls.__name__
        if isinstance(binding.cls, type) and hasattr(binding.cls, "__name__")
        else repr(binding.cls)
    )
    here = ValidationLocation(node=cls_repr, field="inputs_spec")

    if not isinstance(binding.cls, type):
        issues.append(ValidationIssue(
            severity="error", code="binding_cls_not_class",
            message=(
                f"{kind}.cls must be a class, got {binding.cls!r}"
            ),
            location=ValidationLocation(node=cls_repr),
            suggestion=(
                f"Pass the class itself, not an instance: "
                f"`{kind}({cls_repr})`."
            ),
        ))
    if not isinstance(binding.inputs_spec, SourcesSpec):
        issues.append(ValidationIssue(
            severity="error", code="binding_inputs_spec_wrong_type",
            message=(
                f"{kind}.inputs_spec must be a SourcesSpec, got "
                f"{type(binding.inputs_spec).__name__}"
            ),
            location=here,
            suggestion=(
                f"Build inputs_spec with "
                f"`{cls_repr}.INPUTS.sources(...)`."
            ),
        ))
        return issues  # remaining check needs a real SourcesSpec
    inputs_cls = getattr(binding.cls, "INPUTS", None)
    if (
        inputs_cls is not None
        and binding.inputs_spec.inputs_cls is not inputs_cls
    ):
        wired_cls = binding.inputs_spec.inputs_cls
        wired_name = (
            wired_cls.__name__
            if hasattr(wired_cls, "__name__") else repr(wired_cls)
        )
        issues.append(ValidationIssue(
            severity="error", code="binding_inputs_cls_mismatch",
            message=(
                f"{kind}({cls_repr}, inputs_spec=...): "
                f"inputs_spec.inputs_cls is {wired_name}, but "
                f"{cls_repr}.INPUTS is {inputs_cls.__name__}. They "
                f"must match."
            ),
            location=here,
            suggestion=(
                f"Rebuild inputs_spec from the matching class: "
                f"`{inputs_cls.__name__}.sources(...)`, or update "
                f"{cls_repr}.INPUTS to {wired_name}."
            ),
        ))
    return issues


@dataclass
class Step:
    """Pipeline-level binding for an ``LLMStepNode`` subclass.

    Pairs a step class (the *contract* — INPUTS, INSTRUCTIONS,
    DEFAULT_TOOLS, ``prepare()``) with its *wiring* (the
    ``SourcesSpec`` saying where each INPUTS field comes from).

    The ``inputs_spec``'s ``inputs_cls`` must match ``cls.INPUTS``.
    Mismatches are *captured* into ``self._init_post_errors`` rather
    than raised — the binding still exists; the pipeline spec
    surfaces the issue via ``derive_issues``.
    """

    cls: type
    inputs_spec: SourcesSpec

    def __post_init__(self) -> None:
        self._init_post_errors = _validate_binding_post_init(self, "Step")


@dataclass
class Extraction:
    """Pipeline-level binding for an ``ExtractionNode`` subclass.

    Same shape as ``Step`` — the extraction's contract (INPUTS, MODEL,
    ``extract()``) is on the class; the wiring is here. The framework
    runs ``extract()`` and writes its rows both to the DB and to
    ``state.outputs[ExtractionCls.__name__]`` so downstream
    ``FromOutput(MyExtraction, ...)`` works.
    """

    cls: type
    inputs_spec: SourcesSpec

    def __post_init__(self) -> None:
        self._init_post_errors = _validate_binding_post_init(
            self, "Extraction",
        )


@dataclass
class Review:
    """Pipeline-level binding for a ``ReviewNode`` subclass.

    Same shape as the others. ``ReviewNode`` declares INPUTS (what
    the reviewer sees) and OUTPUT (the reviewer's structured
    response). Reviewer response is recorded at
    ``state.outputs[ReviewCls.__name__]`` on resume.
    """

    cls: type
    inputs_spec: SourcesSpec

    def __post_init__(self) -> None:
        self._init_post_errors = _validate_binding_post_init(self, "Review")


# ---------------------------------------------------------------------------
# Helper utilities (used by graph validator + others)
# ---------------------------------------------------------------------------


def _unwrap_optional(annotation: Any) -> Any:
    """Unwrap ``Optional[X]`` / ``X | None`` to ``X``. Leaves other types as-is."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is UnionType:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _validate_dotted_path(
    model_cls: type[BaseModel], path: str, *, location: str
) -> None:
    """Walk a dotted path through nested BaseModels. Raise on missing field.

    Used by the graph validator to statically check ``FromInput(path)``
    references against ``Pipeline.INPUT_DATA``.
    """
    parts = path.split(".")
    current: Any = model_cls
    for part in parts:
        fields = getattr(current, "model_fields", None)
        if fields is None:
            # Stepped into a non-BaseModel field type; cannot statically walk further.
            return
        if part not in fields:
            raise ValueError(
                f"{location}: FromInput references path '{path}', "
                f"but '{part}' is not a field on {current.__name__}"
            )
        annotation = fields[part].annotation
        current = _unwrap_optional(annotation)


def _validate_instructions_field(
    step_cls: type, field_name: str, *, location: str
) -> None:
    """Check ``field_name`` exists on ``step_cls.INSTRUCTIONS`` if present.

    Used by the graph validator to statically check
    ``FromOutput(step_cls, field=...)`` references.
    """
    instructions_cls = getattr(step_cls, "INSTRUCTIONS", None)
    if instructions_cls is None:
        return
    fields = getattr(instructions_cls, "model_fields", None)
    if fields is None:
        return
    if field_name not in fields:
        raise ValueError(
            f"{location}: FromOutput(step={step_cls.__name__}, field='{field_name}') "
            f"— '{field_name}' is not a field on "
            f"{instructions_cls.__name__}"
        )
