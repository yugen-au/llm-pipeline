"""Adapter source types and Bind dataclass for declarative pipeline wiring.

Sources describe how a step's (or extraction pathway's) inputs are
assembled from pipeline input + prior step outputs at adapter-resolve
time. The closed set is: FromInput, FromOutput, FromPipeline, Computed.

Bind pairs a step (or extraction) with a SourcesSpec describing how its
inputs are sourced. Strategies return a list of Bind instances from
``get_bindings()``.
"""
from __future__ import annotations

import typing
from dataclasses import dataclass, field
from types import UnionType
from typing import Any, Callable

from pydantic import BaseModel

__all__ = [
    "AdapterContext",
    "Bind",
    "Computed",
    "FromInput",
    "FromOutput",
    "FromPipeline",
    "Source",
    "SourcesSpec",
    "validate_bindings",
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


@dataclass
class Bind:
    """Wires a step (or extraction) with its input adapter.

    Exactly one of ``step`` / ``extraction`` must be provided. The
    ``extractions`` list is only valid when ``step`` is set (nested
    extraction binds under a step bind).
    """
    step: type | None = None
    extraction: type | None = None
    inputs: SourcesSpec | None = None
    extractions: list["Bind"] = field(default_factory=list)

    def __post_init__(self) -> None:
        has_step = self.step is not None
        has_extraction = self.extraction is not None
        if has_step == has_extraction:
            raise ValueError(
                "Bind must have exactly one of step= or extraction= set, "
                f"got step={self.step!r}, extraction={self.extraction!r}"
            )
        if self.inputs is None:
            raise ValueError("Bind requires inputs= (a SourcesSpec)")
        if self.extractions and not has_step:
            raise ValueError(
                "Nested extractions are only valid when step= is set"
            )
        for child in self.extractions:
            if child.step is not None or child.extraction is None:
                raise ValueError(
                    "Nested Binds under a step must have extraction= set, not step="
                )


# ---------------------------------------------------------------------------
# Static analysis
# ---------------------------------------------------------------------------


def validate_bindings(
    bindings: list[Bind],
    *,
    input_cls: type[BaseModel],
) -> None:
    """Statically verify a strategy's bindings against pipeline INPUT_DATA and step INSTRUCTIONS.

    Raises ``ValueError`` on any violation:

    - Top-level ``Bind`` with ``extraction=`` (instead of ``step=``).
    - ``FromInput(path)`` referencing a path that does not exist on ``input_cls``.
    - ``FromOutput(step_cls, ...)`` referencing a step that does not appear
      earlier in the bindings list. An extraction nested under a step may
      reference that step's output (it runs after the step completes).
    - ``FromOutput(step_cls, field=X)`` where ``X`` is not a field on
      ``step_cls.INSTRUCTIONS`` (checked only when ``INSTRUCTIONS`` is set).
    - ``Computed`` with an invalid nested source (recursive validation).

    ``FromPipeline`` sources are not checked statically — pipeline attrs are
    too dynamic to verify at strategy-class time.

    Designed to be called at pipeline class creation / strategy instantiation
    so errors surface at import rather than at pipeline run.
    """
    steps_seen: set[type] = set()

    for i, bind in enumerate(bindings):
        if bind.step is None:
            raise ValueError(
                f"validate_bindings: binding[{i}] has no step "
                f"(extractions cannot be top-level bindings)"
            )
        step_label = f"binding[{i}] step={bind.step.__name__}"

        # Step's own inputs adapter — may only read from strictly earlier steps.
        _validate_spec(
            bind.inputs,
            input_cls=input_cls,
            steps_seen=steps_seen,
            location=step_label,
        )

        # Nested extraction binds — may additionally reference the owning step.
        extended_seen = steps_seen | {bind.step}
        for j, ext_bind in enumerate(bind.extractions):
            if ext_bind.extraction is None:
                # Guarded by Bind.__post_init__, but kept defensive.
                raise ValueError(
                    f"{step_label} extractions[{j}]: missing extraction="
                )
            ext_label = (
                f"{step_label} extractions[{j}] "
                f"extraction={ext_bind.extraction.__name__}"
            )
            _validate_spec(
                ext_bind.inputs,
                input_cls=input_cls,
                steps_seen=extended_seen,
                location=ext_label,
            )

        steps_seen.add(bind.step)


def _validate_spec(
    spec: SourcesSpec | None,
    *,
    input_cls: type[BaseModel],
    steps_seen: set[type],
    location: str,
) -> None:
    if spec is None:
        # Guarded by Bind.__post_init__, but kept defensive.
        raise ValueError(f"{location}: missing inputs SourcesSpec")
    for field_name, source in spec.field_sources.items():
        _validate_source(
            source,
            input_cls=input_cls,
            steps_seen=steps_seen,
            location=f"{location} field={field_name}",
        )


def _validate_source(
    source: Source,
    *,
    input_cls: type[BaseModel],
    steps_seen: set[type],
    location: str,
) -> None:
    if isinstance(source, FromInput):
        _validate_dotted_path(input_cls, source.path, location=location)
    elif isinstance(source, FromOutput):
        if source.step_cls not in steps_seen:
            raise ValueError(
                f"{location}: FromOutput references step "
                f"{source.step_cls.__name__}, which does not appear earlier "
                f"in the bindings (or is not in this strategy)"
            )
        if source.field is not None:
            _validate_instructions_field(
                source.step_cls, source.field, location=location
            )
    elif isinstance(source, FromPipeline):
        # Pipeline attrs are too dynamic (session, logger, user-defined) to
        # verify statically. Skipped intentionally.
        return
    elif isinstance(source, Computed):
        for inner in source.sources:
            _validate_source(
                inner,
                input_cls=input_cls,
                steps_seen=steps_seen,
                location=location,
            )
    else:
        raise TypeError(
            f"{location}: unknown Source subclass {type(source).__name__}"
        )


def _validate_dotted_path(
    model_cls: type[BaseModel], path: str, *, location: str
) -> None:
    """Walk a dotted path through nested BaseModels. Raise on missing field."""
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


def _unwrap_optional(annotation: Any) -> Any:
    """Unwrap ``Optional[X]`` / ``X | None`` to ``X``. Leaves other types as-is."""
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is UnionType:
        args = [a for a in typing.get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def _validate_instructions_field(
    step_cls: type, field_name: str, *, location: str
) -> None:
    """Check ``field_name`` exists on ``step_cls.INSTRUCTIONS`` if present."""
    instructions_cls = getattr(step_cls, "INSTRUCTIONS", None)
    if instructions_cls is None:
        # Step not migrated / not decorated with @step_definition — skip.
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
