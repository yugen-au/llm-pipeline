"""``PipelineSpec`` — ``Pipeline`` subclasses (Level 5).

A pipeline composes Level-4 nodes (steps, extractions, reviews)
into a graph. Each ``Pipeline.nodes`` entry is a wrapper binding
(``Step(NodeCls, inputs_spec=...)``, etc.) that pairs a node class
with its pipeline-level wiring.

The new :class:`PipelineSpec` is the per-artifact-architecture view
of a pipeline. It REFERENCES nodes by registry key rather than
nesting their full contracts — class-contract data
(INPUTS / INSTRUCTIONS / prepare body / etc.) lives canonically on
the standalone :class:`StepSpec` / :class:`ExtractionSpec` /
:class:`ReviewSpec` instances, populated by the per-kind walkers.
The frontend resolves cross-artifact references via the universal
``(kind, name)`` resolver — no duplication.

Each binding gets its own :class:`NodeBindingSpec` row carrying:

- ``binding_kind`` — the wrapper type (``step`` / ``extraction`` /
  ``review``); informs the UI's binding-card rendering and gates
  edit operations.
- ``node_name`` — snake_case ref into the matching per-kind
  registry. Click-through dispatches to the standalone node spec.
- ``wiring`` — the ``inputs_spec`` serialised. Reuses the existing
  :class:`WiringSpec` / :class:`SourceSpec` types from
  :mod:`llm_pipeline.graph.spec`; the validator already populates
  per-source issues there at ``Pipeline.__init_subclass__`` time.
- ``issues`` (inherited) — binding-wrapper captures
  (``step_binding_wrong_kind``, etc.) from the wrapper's
  ``__post_init__``.

The legacy :class:`llm_pipeline.graph.spec.PipelineSpec` continues
to power the existing ``/api/pipelines/*`` routes; this new spec
populates the per-artifact ``registries[KIND_PIPELINE]`` slot for
the kind-uniform ``/api/artifacts/{kind}`` surface. Convergence to
a single shape is a follow-up phase.

Limitations of the spec → code round-trip in V1:

- ``Computed`` source bodies (the ``fn`` callable inside a
  ``Computed(...)`` wiring source) are referenced by qualname only;
  the function source isn't captured. The demo doesn't use
  ``Computed`` and round-trip support lands when the first concrete
  use case appears.
- Pipeline-file imports are derivable from binding refs at codegen
  time (we know the referenced node classes and their source
  paths) — no need to store them.
"""
from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import Field

from llm_pipeline.artifacts.base import ArtifactField, ArtifactRef, ArtifactSpec
from llm_pipeline.artifacts.base.blocks import JsonSchemaWithRefs
from llm_pipeline.artifacts.base.builder import SpecBuilder, _class_to_artifact_ref
from llm_pipeline.artifacts.base.fields import FieldRef
from llm_pipeline.artifacts.base.kinds import KIND_PIPELINE
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.walker import Walker, _is_locally_defined_class


__all__ = [
    "MANIFEST",
    "EdgeSpec",
    "NodeBindingSpec",
    "PipelineBuilder",
    "PipelineSpec",
    "PipelinesWalker",
    "SourceSpec",
    "WiringSpec",
]


class SourceSpec(ArtifactField):
    """Serialised view of one wiring source adapter."""

    kind: Literal["from_input", "from_output", "from_pipeline", "computed"]
    path: str | None = None
    step_cls: str | None = None
    index: int | None = None
    field: str | None = None
    attr: str | None = None
    fn: str | None = None
    sources: list["SourceSpec"] | None = None


class WiringSpec(ArtifactField):
    """A node's pipeline-level wiring (its ``inputs_spec`` serialised)."""

    inputs_cls: str
    field_sources: dict[str, SourceSpec]


class EdgeSpec(ArtifactField):
    """A directed edge between pipeline nodes (or to ``End``)."""

    from_node: str
    to_node: str
    branch: str | None = None


class NodeBindingSpec(ArtifactField):
    """One ``Step`` / ``Extraction`` / ``Review`` wrapper inside a pipeline.

    Carries the binding-level state — wrapper kind, the registry
    name of the wrapped node, and the resolved wiring — without
    duplicating the node's class contract. Per-class contract
    issues (missing INPUTS, naming mismatches, etc.) live on the
    standalone per-kind spec keyed by ``node_name`` in the matching
    registry; the frontend follows the ref via the universal
    resolver.

    Inherits ``issues`` from :class:`ArtifactField` — populated
    from the wrapper's ``_init_post_errors`` (binding-kind
    mismatches like ``Step(SomeReviewNode)``, etc.).
    """

    # ``node_name`` is the lookup key when NodeBindingSpec appears
    # in a ``list[NodeBindingSpec]`` slot
    # (``PipelineSpec.nodes[topic_extraction]``).
    IDENTITY_FIELD: ClassVar[str | None] = "node_name"

    # Which wrapper class wraps the node — gates binding-specific
    # UI affordances (``Step`` shows prompt section; ``Extraction``
    # shows table mapping; ``Review`` shows webhook config).
    binding_kind: Literal["step", "extraction", "review"]

    # Registry key in ``registries[KIND_STEP|KIND_EXTRACTION|KIND_REVIEW]``
    # — snake_case, derived from the binding's class name with the
    # matching suffix stripped.
    node_name: str

    # Pipeline-level wiring — the ``inputs_spec`` serialised into
    # source descriptors. Reuses the legacy types from
    # ``graph/spec.py``; per-source validation issues
    # (``from_input_unknown_path``, ``from_output_not_upstream``,
    # etc.) live nested on each ``SourceSpec.issues``, populated by
    # the structural validator at ``Pipeline.__init_subclass__``
    # time.
    wiring: WiringSpec


class PipelineSpec(ArtifactSpec):
    """A ``Pipeline`` subclass declared in ``llm_pipelines/pipelines/``."""

    kind: Literal[KIND_PIPELINE] = KIND_PIPELINE  # type: ignore[assignment]

    # The pipeline's ``INPUT_DATA`` class shape — what the pipeline
    # accepts at run time (``run_pipeline_in_memory(..., input_data=...)``).
    # ``None`` when ``INPUT_DATA`` isn't set on the class; a captured
    # issue surfaces on ``self.issues``.
    input_data: JsonSchemaWithRefs | None = None

    # The bindings in ``Pipeline.nodes`` declaration order, deduped
    # by node class (first occurrence wins — duplicates surface as
    # ``duplicate_node_class`` issues on ``self.issues``).
    nodes: list[NodeBindingSpec] = Field(default_factory=list)

    # Directed edges from each node to its successors (or ``End``),
    # derived from each node's ``run()`` return-type annotation.
    # Reuses :class:`EdgeSpec` from the legacy spec; ``EdgeSpec.branch``
    # is the placeholder for future binding-driven branching.
    edges: list[EdgeSpec] = Field(default_factory=list)

    # The pipeline's start node — wrapped as :class:`ArtifactRef`
    # carrying the source-side Python class name plus a resolved
    # ref into the matching node registry (``KIND_STEP`` /
    # ``KIND_EXTRACTION`` / ``KIND_REVIEW``) when the resolver
    # matches. ``None`` when ``cls.start_node`` is unset (typically
    # because the pipeline has no valid bindings).
    start_node: ArtifactRef | None = None

    # Auto-generated routing-key constants for the ArtifactField-typed
    # fields above (``INPUT_DATA``, ``NODES``, ``EDGES``, ``START_NODE``)
    # are produced by :meth:`ArtifactField.__pydantic_init_subclass__`.
    # Parameterised lookups for runtime-keyed paths live as
    # classmethods alongside.

    @classmethod
    def node(cls, node_name: str) -> FieldRef:
        """Path to ``spec.nodes[i]`` where ``i.node_name == node_name``."""
        return FieldRef(f"nodes[{node_name}]")

    @classmethod
    def source(cls, node_name: str, src_field: str) -> FieldRef:
        """Path to ``spec.nodes[i].wiring.field_sources[src_field]``."""
        return FieldRef(f"nodes[{node_name}].wiring.field_sources[{src_field}]")


class PipelineBuilder(SpecBuilder):
    """Build a :class:`PipelineSpec` directly from a ``Pipeline`` subclass.

    Reads ``cls._wiring`` (deduped bindings), ``cls.INPUT_DATA``,
    ``cls.start_node``, and the per-node ``run()`` return annotations
    to construct nodes / input_data / start_node / edges. Routes
    ``cls._init_subclass_errors`` onto matching components via
    :meth:`attach_class_captures`.

    Class-contract issues (missing INPUTS, prepare-signature
    mismatches, etc.) live canonically on the standalone per-kind
    spec — not duplicated here.
    """

    SPEC_CLS = PipelineSpec

    def kind_fields(self) -> dict[str, Any]:
        from llm_pipeline.wiring import Extraction, Review, Step

        cls = self.cls
        deduped_bindings = list(getattr(cls, "_wiring", {}).values())
        raw_nodes = [b.cls for b in deduped_bindings]

        node_bindings: list[NodeBindingSpec] = []
        for binding in deduped_bindings:
            if isinstance(binding, Step):
                binding_kind = "step"
            elif isinstance(binding, Extraction):
                binding_kind = "extraction"
            elif isinstance(binding, Review):
                binding_kind = "review"
            else:
                continue
            node_bindings.append(NodeBindingSpec(
                binding_kind=binding_kind,
                node_name=_node_name_for_binding(binding),
                wiring=_build_wiring_spec(binding),
            ))

        edges = _build_edges(raw_nodes)

        input_data_cls = getattr(cls, "INPUT_DATA", None)
        input_data = self.json_schema(input_data_cls)

        start_node_ref = _class_to_artifact_ref(
            getattr(cls, "start_node", None), self.resolver,
        )

        return {
            "input_data": input_data,
            "nodes": node_bindings,
            "edges": edges,
            "start_node": start_node_ref,
        }


class PipelinesWalker(Walker):
    """Register ``Pipeline`` subclasses from ``pipelines/``."""

    BUILDER = PipelineBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.graph.pipeline import Pipeline

        return _is_locally_defined_class(value, mod, Pipeline)

    def name_for(self, attr_name, value):
        return value.pipeline_name()


# ---------------------------------------------------------------------------
# Helpers used by PipelineBuilder
# ---------------------------------------------------------------------------


def _node_name_for_binding(binding) -> str:
    """Snake_case registry key for ``binding.cls``."""
    from llm_pipeline.naming import to_snake_case
    from llm_pipeline.wiring import Extraction, Review, Step

    cls = binding.cls
    if isinstance(binding, Step):
        return cls.step_name()
    suffix = "Extraction" if isinstance(binding, Extraction) else "Review"
    return to_snake_case(cls.__name__, strip_suffix=suffix)


def _build_wiring_spec(binding) -> WiringSpec:
    """Serialise a binding's ``inputs_spec`` into a :class:`WiringSpec`."""
    spec = binding.inputs_spec
    return WiringSpec(
        inputs_cls=f"{spec.inputs_cls.__module__}.{spec.inputs_cls.__qualname__}",
        field_sources={
            name: _serialise_source(src)
            for name, src in spec.field_sources.items()
        },
    )


def _serialise_source(source) -> SourceSpec:
    from llm_pipeline.wiring import Computed, FromInput, FromOutput, FromPipeline

    if isinstance(source, FromInput):
        return SourceSpec(kind="from_input", path=source.path)
    if isinstance(source, FromOutput):
        return SourceSpec(
            kind="from_output",
            step_cls=source.step_cls.__name__,
            index=source.index,
            field=source.field,
        )
    if isinstance(source, FromPipeline):
        return SourceSpec(kind="from_pipeline", attr=source.attr)
    if isinstance(source, Computed):
        return SourceSpec(
            kind="computed",
            fn=getattr(source.fn, "__qualname__", repr(source.fn)),
            sources=[_serialise_source(s) for s in source.sources],
        )
    raise TypeError(f"Unknown Source subclass {type(source).__name__!r}")


def _build_edges(raw_nodes: list[type]) -> list[EdgeSpec]:
    """Build the EdgeSpec list from each node's ``run()`` return annotations."""
    from llm_pipeline.graph.validator import _next_node_classes

    edges = []
    for node in raw_nodes:
        targets = _next_node_classes(node, raw_nodes)
        if _run_returns_end(node, raw_nodes):
            edges.append(EdgeSpec(from_node=node.__name__, to_node="End"))
        for target in targets:
            edges.append(EdgeSpec(
                from_node=node.__name__, to_node=target.__name__,
            ))
    return edges


def _run_returns_end(node_cls: type, raw_nodes: list[type]) -> bool:
    """True if ``node_cls.run()``'s return annotation reaches ``End``."""
    import typing
    from types import UnionType
    from pydantic_graph import End

    return_annotation = node_cls.run.__annotations__.get("return")
    if return_annotation is None:
        return False
    if isinstance(return_annotation, str):
        try:
            name_to_node = {n.__name__: n for n in raw_nodes}
            return_annotation = eval(  # noqa: S307
                return_annotation,
                getattr(node_cls.run, "__globals__", {}),
                name_to_node | {"End": End},
            )
        except (NameError, SyntaxError):
            return False

    def _has_end(ann) -> bool:
        if ann is End:
            return True
        origin = typing.get_origin(ann)
        if origin is End:
            return True
        if origin is typing.Union or origin is UnionType:
            return any(_has_end(arg) for arg in typing.get_args(ann))
        return False

    return _has_end(return_annotation)


MANIFEST = ArtifactManifest(
    subfolder="pipelines",
    level=5,
    spec_cls=PipelineSpec,
    walker=PipelinesWalker(),
)
