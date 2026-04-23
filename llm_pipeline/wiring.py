"""Adapter source types and Bind dataclass for declarative pipeline wiring.

Sources describe how a step's (or extraction pathway's) inputs are
assembled from pipeline input + prior step outputs at adapter-resolve
time. The closed set is: FromInput, FromOutput, FromPipeline, Computed.

Bind pairs a step (or extraction) with a SourcesSpec describing how its
inputs are sourced. Strategies return a list of Bind instances from
``get_bindings()``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "AdapterContext",
    "Bind",
    "Computed",
    "FromInput",
    "FromOutput",
    "FromPipeline",
    "Source",
    "SourcesSpec",
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
