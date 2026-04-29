"""Pipeline base class for pydantic-graph-native pipelines.

A pipeline subclass declares:

- ``INPUT_DATA``: a ``PipelineInputData`` subclass (or ``None`` for
  input-less pipelines).
- ``nodes``: ordered list of node classes that make up the graph.
- Optional ``start_node``: defaults to ``nodes[0]``.

At ``__init_subclass__`` time the class:

1. Runs the compile-time validator (``validate_pipeline``) — every
   ``FromInput`` path resolves, every ``FromOutput`` references an
   upstream step's ``INSTRUCTIONS`` field, naming conventions hold,
   the graph is acyclic.
2. Instantiates ``pydantic_graph.Graph(nodes=cls.nodes)`` and stores
   it as ``cls._graph``. pydantic-graph's own ``_validate_edges``
   layer-fires here, catching any return-type mismatch the framework
   validator missed.

Calling ``Pipeline()`` is **not** how pipelines are run — use
``llm_pipeline.graph.run_pipeline_in_memory(...)`` (Phase 1) or the
DB-backed runtime (Phase 2). Subclassing is the declaration; the
graph itself is the runtime artefact.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic_graph import Graph

from llm_pipeline.graph.state import PipelineDeps, PipelineState
from llm_pipeline.graph.validator import validate_pipeline
from llm_pipeline.inputs import PipelineInputData

__all__ = ["Pipeline", "PipelineEnd"]


@dataclass
class PipelineEnd:
    """Default ``End[T]`` payload for a pipeline run.

    Returned from the last node's ``run()`` as ``End(PipelineEnd())``.
    Carries no data — the canonical run output is ``state.outputs``,
    surfaced via the runtime's return value. The dataclass is here so
    pydantic-graph has a concrete ``RunEndT`` to discriminate.
    """


class Pipeline:
    """Base class for declarative pipeline definitions.

    Subclass and declare ``INPUT_DATA``, ``nodes``, and optionally
    ``start_node`` (defaults to ``nodes[0]``). The class body runs the
    Phase-1 compile-time checks at subclass-creation time.

    Example::

        class TextAnalyzerPipeline(Pipeline):
            INPUT_DATA = TextAnalyzerInputData
            nodes = [
                SentimentAnalysisStep,
                TopicExtractionStep,
                TopicExtraction,
                SummaryStep,
            ]
            # start_node defaults to nodes[0] (SentimentAnalysisStep).

    The framework provides ``run_pipeline_in_memory(pipeline_cls,
    input_data)`` to execute a graph; the UI runtime (Phase 2) plugs
    in DB persistence.
    """

    INPUT_DATA: ClassVar[type[PipelineInputData] | None] = None
    nodes: ClassVar[list[type]] = []
    start_node: ClassVar[type | None] = None

    # Populated by __init_subclass__
    _graph: ClassVar[Graph[PipelineState, PipelineDeps, Any] | None] = None
    _node_classes: ClassVar[dict[str, type]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Skip the base when nothing was declared (intermediate
        # inheritance chains shouldn't fire validation).
        if not cls.nodes:
            return

        if cls.start_node is None:
            cls.start_node = cls.nodes[0]

        validate_pipeline(
            cls,
            nodes=list(cls.nodes),
            start_node=cls.start_node,
            input_cls=cls.INPUT_DATA,
        )

        # Inject the sibling-node namespace onto every node class so
        # cross-module forward refs in ``run`` return annotations
        # resolve when pydantic-graph's edge-validator runs. Read by
        # ``llm_pipeline.graph.nodes._build_node_def``.
        sibling_ns = {n.__name__: n for n in cls.nodes}
        for node in cls.nodes:
            existing = getattr(node, "_pipeline_namespace", None) or {}
            node._pipeline_namespace = dict(existing) | sibling_ns

        cls._graph = Graph(nodes=tuple(cls.nodes), name=cls.__name__)
        cls._node_classes = {n.__name__: n for n in cls.nodes}

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
