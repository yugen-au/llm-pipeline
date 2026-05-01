"""Pipeline base class for pydantic-graph-native pipelines.

A pipeline subclass declares:

- ``INPUT_DATA``: a ``PipelineInputData`` subclass (or ``None`` for
  input-less pipelines).
- ``nodes``: ordered list of ``Step`` / ``Extraction`` / ``Review``
  wrappers, each pairing a node class with its ``inputs_spec``.
- Optional ``start_node``: defaults to the raw class of ``nodes[0]``.

At ``__init_subclass__`` time the class:

1. Walks ``nodes`` and builds ``cls._wiring`` (``dict[type, Step |
   Extraction | Review]`` keyed by node base class). Bindings whose
   wrappers captured errors are still included in the wiring so the
   spec can describe them; only entries whose ``cls`` field isn't a
   class get filtered out.
2. Runs the structural validator (``validate_pipeline``). The
   validator captures issues into a list; it never raises.
3. Aggregates per-binding ``_init_post_errors``, per-node
   ``_init_subclass_errors`` (from each step / extraction / review
   class), and per-PromptVariables ``_init_subclass_errors`` into
   ``cls._init_subclass_errors``.
4. Builds the ``pydantic_graph.Graph`` and the ``PipelineSpec`` on a
   best-effort basis. Failures are captured rather than raised.

The class object always constructs. Consumers consult
``cls._init_subclass_errors`` (or call ``derive_issues(cls.inspect())``)
to decide whether the pipeline is runnable. Calling ``Pipeline()`` is
**not** how pipelines are run — use
``llm_pipeline.graph.run_pipeline_in_memory(...)`` (Phase 1) or the
DB-backed runtime (Phase 2).

Phoenix-aware validation (prompt existence, template-vs-PromptVariables
drift, sync push) runs separately at discovery time when
``uv run llm-pipeline`` boots. Tests / IDE / type-checking don't
trigger discovery, so they don't touch Phoenix.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic_graph import Graph

from llm_pipeline.graph.spec import PipelineSpec, build_pipeline_spec
from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.graph.validator import validate_pipeline
from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.wiring import Extraction, Review, Step

if TYPE_CHECKING:
    from llm_pipeline.graph.spec import ValidationIssue

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
    # Typed introspection surface, built once at __init_subclass__
    # and surfaced via ``Pipeline.inspect()``. Phoenix-aware fields on
    # each node's ``prompt`` start as ``None`` and are filled in by
    # the discovery-time Phoenix validator.
    _spec: ClassVar[PipelineSpec | None] = None
    # Aggregated validation issues from all sources (binding wrappers,
    # node ``__init_subclass__``, the structural validator, graph/spec
    # build failures). Empty when the pipeline is structurally clean.
    # Each subclass gets its own fresh list.
    _init_subclass_errors: ClassVar[list["ValidationIssue"]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.nodes:
            cls._init_subclass_errors = []
            return

        from llm_pipeline.graph.nodes import LLMStepNode
        from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

        errors: list[ValidationIssue] = []

        # Filter to entries that are actual binding wrappers. Anything
        # else is a flat-out misuse — capture it and skip; downstream
        # processing only sees real bindings.
        valid_bindings: list[NodeBinding] = []
        for i, binding in enumerate(cls.nodes):
            if not isinstance(binding, (Step, Extraction, Review)):
                errors.append(ValidationIssue(
                    severity="error", code="invalid_binding_type",
                    message=(
                        f"{cls.__name__}.nodes[{i}] must be a Step, "
                        f"Extraction, or Review wrapper; got {binding!r}. "
                        f"Bare node classes are no longer accepted — "
                        f"wrap them with the appropriate binding."
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

        # Build the wiring dict + raw-class list (for pydantic-graph).
        # Capture duplicates; first occurrence wins so downstream still
        # has something to operate on.
        wiring: dict[type, NodeBinding] = {}
        raw_nodes: list[type] = []
        for binding in valid_bindings:
            if not isinstance(binding.cls, type):
                continue  # binding wrapper already captured this
            if binding.cls in wiring:
                errors.append(ValidationIssue(
                    severity="error", code="duplicate_node_class",
                    message=(
                        f"{cls.__name__}.nodes contains duplicate node "
                        f"class {binding.cls.__name__}. Each node class "
                        f"may appear at most once per pipeline."
                    ),
                    location=ValidationLocation(
                        pipeline=cls.__name__, node=binding.cls.__name__,
                    ),
                    suggestion=(
                        f"Remove the duplicate, or use a different node "
                        f"class."
                    ),
                ))
                continue
            wiring[binding.cls] = binding
            raw_nodes.append(binding.cls)

        cls._wiring = wiring

        if cls.start_node is None and raw_nodes:
            cls.start_node = raw_nodes[0]

        # Aggregate per-binding capture errors.
        for binding in valid_bindings:
            errors.extend(getattr(binding, "_init_post_errors", []))

        # Aggregate per-node capture errors (missing INPUTS / MODEL /
        # OUTPUT / INSTRUCTIONS, prepare-signature mismatches, ...).
        for node_cls in raw_nodes:
            errors.extend(getattr(node_cls, "_init_subclass_errors", []))

        # Aggregate per-PromptVariables capture errors for each step.
        for node_cls in raw_nodes:
            if isinstance(node_cls, type) and issubclass(node_cls, LLMStepNode):
                pv_cls = getattr(node_cls, "prompt_variables_cls", None)
                if pv_cls is not None:
                    errors.extend(
                        getattr(pv_cls, "_init_subclass_errors", []),
                    )

        # Run the structural validator. It never raises — every
        # violation comes back as a ValidationIssue.
        errors.extend(validate_pipeline(
            cls,
            nodes=valid_bindings,
            start_node=cls.start_node,
            input_cls=cls.INPUT_DATA,
        ))

        # Sibling-node namespace for forward-ref resolution in run()
        # return annotations. Read by ``_build_node_def``.
        sibling_ns = {n.__name__: n for n in raw_nodes}
        for node in raw_nodes:
            existing = getattr(node, "_pipeline_namespace", None) or {}
            node._pipeline_namespace = dict(existing) | sibling_ns

        # Best-effort graph + spec build. Failures (likely due to
        # invalid return annotations on a node's `run`, etc.) get
        # captured; class still constructs.
        if raw_nodes:
            try:
                cls._graph = Graph(nodes=tuple(raw_nodes), name=cls.__name__)
                cls._node_classes = {n.__name__: n for n in raw_nodes}
            except Exception as exc:
                errors.append(ValidationIssue(
                    severity="error", code="graph_build_failed",
                    message=(
                        f"Could not build pydantic-graph for "
                        f"{cls.__name__}: {exc!s}"
                    ),
                    location=ValidationLocation(pipeline=cls.__name__),
                ))
                cls._graph = None
                cls._node_classes = {}

            try:
                cls._spec = build_pipeline_spec(cls)
            except Exception as exc:
                errors.append(ValidationIssue(
                    severity="error", code="spec_build_failed",
                    message=(
                        f"Could not build PipelineSpec for "
                        f"{cls.__name__}: {exc!s}"
                    ),
                    location=ValidationLocation(pipeline=cls.__name__),
                ))
                cls._spec = None
        else:
            cls._graph = None
            cls._node_classes = {}
            cls._spec = None

        cls._init_subclass_errors = errors

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

    @classmethod
    def inspect(cls) -> PipelineSpec:
        """Return the typed ``PipelineSpec`` introspection surface.

        Built once at ``__init_subclass__`` time and cached. The same
        instance is returned on every call. Phoenix-aware fields on
        each node's ``prompt`` are populated by the discovery-time
        Phoenix validator; ``None`` until that runs.
        """
        if cls._spec is None:
            raise RuntimeError(
                f"{cls.__name__} has no compiled spec — declare "
                f"`nodes = [...]` and re-import the module."
            )
        return cls._spec
