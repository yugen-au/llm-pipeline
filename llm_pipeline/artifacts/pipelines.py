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

from typing import ClassVar, Literal

from pydantic import Field

from llm_pipeline.artifacts.base import ArtifactField, ArtifactRef, ArtifactSpec
from llm_pipeline.artifacts.blocks import JsonSchemaWithRefs
from llm_pipeline.artifacts.fields import FieldRef, FieldsBase
from llm_pipeline.artifacts.kinds import KIND_PIPELINE


__all__ = [
    "EdgeSpec",
    "NodeBindingSpec",
    "PipelineFields",
    "PipelineSpec",
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


class PipelineFields(FieldsBase):
    """Routing keys for :class:`PipelineSpec` issue captures."""

    SPEC_CLS = PipelineSpec

    INPUT_DATA = FieldRef("input_data")

    @classmethod
    def node(cls, node_name: str) -> FieldRef:
        """Path to ``spec.nodes[i]`` where ``i.node_name == node_name``."""
        return FieldRef(f"nodes[{node_name}]")

    @classmethod
    def source(cls, node_name: str, src_field: str) -> FieldRef:
        """Path to ``spec.nodes[i].wiring.field_sources[src_field]``."""
        return FieldRef(f"nodes[{node_name}].wiring.field_sources[{src_field}]")
