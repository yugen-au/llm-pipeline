"""Pipeline base class for pydantic-graph-native pipelines.

A pipeline subclass declares:

- ``INPUT_DATA``: a ``PipelineInputData`` subclass (or ``None`` for
  input-less pipelines).
- ``nodes``: ordered list of ``Step`` / ``Extraction`` / ``Review``
  wrappers, each pairing a node class with its ``inputs_spec``.
- Optional ``start_node``: defaults to the raw class of ``nodes[0]``.

At ``__init_subclass__`` time the class:

1. Walks ``nodes`` and builds ``cls._wiring`` (``dict[type, Step |
   Extraction | Review]`` keyed by node base class).
2. Runs the compile-time validator (``validate_pipeline``) — purely
   structural checks. ``FromInput`` paths resolve against
   ``INPUT_DATA``; ``FromOutput`` references point upstream; naming
   conventions hold; the graph is acyclic. *No Phoenix calls.*
3. Compiles ``pydantic_graph.Graph(nodes=raw_classes)``.

Phoenix-aware validation (prompt existence, template-vs-PromptVariables
drift, sync push) runs separately at discovery time when
``uv run llm-pipeline`` boots. Tests / IDE / type-checking don't
trigger discovery, so they don't touch Phoenix.

Calling ``Pipeline()`` is **not** how pipelines are run — use
``llm_pipeline.graph.run_pipeline_in_memory(...)`` (Phase 1) or the
DB-backed runtime (Phase 2).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic_graph import Graph

from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.graph.validator import validate_pipeline
from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.wiring import Extraction, Review, Step

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

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.nodes:
            return

        # Validate every entry is a Step / Extraction / Review wrapper.
        for i, binding in enumerate(cls.nodes):
            if not isinstance(binding, (Step, Extraction, Review)):
                raise TypeError(
                    f"{cls.__name__}.nodes[{i}] must be a Step, "
                    f"Extraction, or Review wrapper; got {binding!r}. "
                    f"Bare node classes are no longer accepted — wrap "
                    f"them with the appropriate binding."
                )

        # Build the wiring dict + raw-class list (for pydantic-graph).
        wiring: dict[type, NodeBinding] = {}
        raw_nodes: list[type] = []
        for i, binding in enumerate(cls.nodes):
            if binding.cls in wiring:
                raise ValueError(
                    f"{cls.__name__}.nodes[{i}]: duplicate node class "
                    f"{binding.cls.__name__}. Each node class may "
                    f"appear at most once per pipeline."
                )
            wiring[binding.cls] = binding
            raw_nodes.append(binding.cls)

        cls._wiring = wiring

        if cls.start_node is None:
            cls.start_node = raw_nodes[0]

        # Structural validation only. No Phoenix calls.
        validate_pipeline(
            cls,
            nodes=list(cls.nodes),
            start_node=cls.start_node,
            input_cls=cls.INPUT_DATA,
        )

        # Sibling-node namespace for forward-ref resolution in run()
        # return annotations. Read by ``_build_node_def``.
        sibling_ns = {n.__name__: n for n in raw_nodes}
        for node in raw_nodes:
            existing = getattr(node, "_pipeline_namespace", None) or {}
            node._pipeline_namespace = dict(existing) | sibling_ns

        cls._graph = Graph(nodes=tuple(raw_nodes), name=cls.__name__)
        cls._node_classes = {n.__name__: n for n in raw_nodes}

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
