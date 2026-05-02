"""Pipeline base class for pydantic-graph-native pipelines.

A pipeline subclass declares:

- ``INPUT_DATA``: a ``PipelineInputData`` subclass (or ``None`` for
  input-less pipelines).
- ``nodes``: ordered list of ``Step`` / ``Extraction`` / ``Review``
  wrappers, each pairing a node class with its ``inputs_spec``.
- Optional ``start_node``: defaults to the raw class of ``nodes[0]``.

At ``__init_subclass__`` time the class:

1. Filters ``nodes`` to valid bindings (capturing pipeline-level
   ``invalid_binding_type`` / ``duplicate_node_class`` issues for
   anything that doesn't survive).
2. Builds ``cls._wiring`` (``dict[type, NodeBinding]``) and the raw
   class list for pydantic-graph.
3. Builds the pydantic-graph ``Graph`` (best-effort; failures
   capture ``graph_build_failed``).
4. Builds a ``PipelineSpec`` skeleton with empty ``issues`` lists
   on every component. ``build_pipeline_spec`` never raises — on
   internal failure it returns a minimal shell spec carrying a
   ``spec_build_failed`` issue, so ``cls._spec`` is always a
   usable shape.
5. Stamps every captured framework-rule violation onto its natural
   home in the spec:

   - Node ``_init_subclass_errors`` (missing INPUTS / INSTRUCTIONS /
     MODEL / OUTPUT, prepare-signature issues, etc.) →
     ``NodeSpec.issues``.
   - Binding wrapper ``_init_post_errors`` (binding_*) →
     ``NodeSpec.issues``.
   - PromptVariables ``_init_subclass_errors`` (auto_vars,
     missing_field_description) → ``PromptSpec.issues``.

6. Runs the structural validator
   (:func:`validate_pipeline_into_spec`) which appends issues onto
   each spec component as it walks (per-node naming /
   contracts → ``NodeSpec.issues``; per-wiring-field source
   checks → ``SourceSpec.issues``; cycles / start_node →
   ``PipelineSpec.issues``).

7. Sets ``cls._init_subclass_errors = derive_issues(cls._spec)`` —
   the flat list across every level.

The class object always constructs. Consumers consult
``cls._init_subclass_errors`` (or call ``derive_issues(spec)``,
or read per-component ``.issues``) to decide whether the pipeline
is runnable. Calling ``Pipeline()`` is **not** how pipelines are
run — use ``llm_pipeline.graph.run_pipeline_in_memory(...)`` (Phase
1) or the DB-backed runtime (Phase 2).

Phoenix-aware validation runs separately at discovery time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic_graph import Graph

from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.graph.validator import validate_pipeline
from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.specs.validation import ValidationIssue, ValidationLocation
from llm_pipeline.wiring import Extraction, Review, Step

if TYPE_CHECKING:
    pass

__all__ = ["Pipeline", "PipelineEnd"]


# Type alias for any per-node binding wrapper.
NodeBinding = Step | Extraction | Review


@dataclass
class PipelineEnd:
    """Default ``End[T]`` payload for a pipeline run.

    Returned from the last node's ``run()`` as ``End(PipelineEnd())``.
    Carries no data — the canonical run output is ``state.outputs``,
    surfaced via the runtime's return value.
    """


class Pipeline:
    """Base class for declarative pipeline definitions.

    Subclass and declare ``INPUT_DATA`` and ``nodes`` (a list of
    ``Step`` / ``Extraction`` / ``Review`` wrappers). Optionally
    declare ``start_node`` (defaults to the raw class of ``nodes[0]``).

    Example::

        class TextAnalyzerPipeline(Pipeline):
            INPUT_DATA = TextAnalyzerInputData
            nodes = [
                Step(SentimentAnalysisStep,
                     inputs_spec=SentimentAnalysisInputs.sources(
                         text=FromInput("text"),
                     )),
                Step(TopicExtractionStep,
                     inputs_spec=TopicExtractionInputs.sources(
                         text=FromInput("text"),
                         sentiment=FromOutput(
                             SentimentAnalysisStep, field="sentiment",
                         ),
                     )),
                Extraction(TopicExtraction,
                           inputs_spec=...),
                Step(SummaryStep, inputs_spec=...),
            ]
    """

    INPUT_DATA: ClassVar[type[PipelineInputData] | None] = None
    nodes: ClassVar[list[NodeBinding]] = []
    start_node: ClassVar[type | None] = None

    # Populated by __init_subclass__
    _graph: ClassVar[Graph[PipelineState, PipelineDeps, Any] | None] = None
    _node_classes: ClassVar[dict[str, type]] = {}
    # Wiring dict keyed by node base class. Threaded into PipelineDeps
    # by the runtime so node bodies read their wiring from there.
    _wiring: ClassVar[dict[type, NodeBinding]] = {}
    # Issues collected at __init_subclass__ time. The per-artifact
    # PipelineBuilder routes them onto the new PipelineSpec via
    # attach_class_captures.
    _init_subclass_errors: ClassVar[list[ValidationIssue]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.nodes:
            cls._init_subclass_errors = []
            return

        issues: list[ValidationIssue] = []

        # 1. Filter to valid binding wrappers.
        valid_bindings: list[NodeBinding] = []
        for i, binding in enumerate(cls.nodes):
            if not isinstance(binding, (Step, Extraction, Review)):
                issues.append(ValidationIssue(
                    severity="error", code="invalid_binding_type",
                    message=(
                        f"{cls.__name__}.nodes[{i}] must be a Step, "
                        f"Extraction, or Review wrapper; got {binding!r}."
                    ),
                    location=ValidationLocation(pipeline=cls.__name__),
                    suggestion=(
                        "Wrap with Step(NodeCls, inputs_spec=...), "
                        "Extraction(NodeCls, inputs_spec=...), or "
                        "Review(NodeCls, inputs_spec=...)."
                    ),
                ))
            else:
                valid_bindings.append(binding)

        # 2. Dedup by node class (first occurrence wins).
        wiring: dict[type, NodeBinding] = {}
        deduped_bindings: list[NodeBinding] = []
        for binding in valid_bindings:
            if not isinstance(binding.cls, type):
                continue
            if binding.cls in wiring:
                issues.append(ValidationIssue(
                    severity="error", code="duplicate_node_class",
                    message=(
                        f"{cls.__name__}.nodes contains duplicate node "
                        f"class {binding.cls.__name__}."
                    ),
                    location=ValidationLocation(
                        pipeline=cls.__name__, node=binding.cls.__name__,
                    ),
                    suggestion="Remove the duplicate.",
                ))
                continue
            wiring[binding.cls] = binding
            deduped_bindings.append(binding)
        raw_nodes = [b.cls for b in deduped_bindings]

        cls._wiring = wiring

        if cls.start_node is None and raw_nodes:
            cls.start_node = raw_nodes[0]

        # 3. Sibling-node namespace for forward-ref resolution in run()
        #    return annotations.
        sibling_ns = {n.__name__: n for n in raw_nodes}
        for node in raw_nodes:
            existing = getattr(node, "_pipeline_namespace", None) or {}
            node._pipeline_namespace = dict(existing) | sibling_ns

        # 4. Best-effort graph build.
        if raw_nodes:
            try:
                cls._graph = Graph(nodes=tuple(raw_nodes), name=cls.__name__)
                cls._node_classes = {n.__name__: n for n in raw_nodes}
            except Exception as exc:
                issues.append(ValidationIssue(
                    severity="error", code="graph_build_failed",
                    message=(
                        f"Could not build pydantic-graph for "
                        f"{cls.__name__}: {exc!s}"
                    ),
                    location=ValidationLocation(pipeline=cls.__name__),
                ))
                cls._graph = None
                cls._node_classes = {}
        else:
            cls._graph = None
            cls._node_classes = {}

        # 5. Run structural validator — appends path-routed issues.
        issues.extend(validate_pipeline(
            cls,
            bindings=deduped_bindings,
            input_cls=cls.INPUT_DATA,
            start_node=cls.start_node,
        ))

        # Wrapper __post_init__ captures (binding_*).
        for binding in deduped_bindings:
            issues.extend(getattr(binding, "_init_post_errors", []))

        cls._init_subclass_errors = issues

    @classmethod
    def graph(cls) -> Graph[PipelineState, PipelineDeps, Any]:
        """Return the compiled ``pydantic_graph.Graph`` for this pipeline."""
        if cls._graph is None:
            raise RuntimeError(
                f"{cls.__name__} has no compiled graph — declare "
                f"`nodes = [...]` and re-import the module."
            )
        return cls._graph

    @classmethod
    def pipeline_name(cls) -> str:
        """Snake-cased name with ``Pipeline`` suffix stripped."""
        from llm_pipeline.naming import to_snake_case

        return to_snake_case(cls.__name__, strip_suffix="Pipeline")
