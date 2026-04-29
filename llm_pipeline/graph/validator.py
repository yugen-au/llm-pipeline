"""Compile-time validator for pydantic-graph-native pipelines.

Runs at ``Pipeline.__init_subclass__``. Enforces the
"if it compiles, it works" contract:

1. Naming conventions: ``{Name}Pipeline``, ``{Name}Step``,
   ``{Name}Extraction``, ``{Name}Review``.
2. ``INPUT_DATA`` is a ``PipelineInputData`` subclass.
3. Every node's ``inputs_spec`` is a valid ``SourcesSpec``:
   - ``FromInput(path)`` resolves against ``INPUT_DATA``'s nested
     ``BaseModel`` fields.
   - ``FromOutput(StepCls)`` references a step that appears
     **upstream** in the graph (topologically reachable from
     ``start_node`` and visited before this node).
   - ``FromOutput(StepCls, field=X)`` resolves against
     ``StepCls.INSTRUCTIONS.model_fields``.
4. Every ``ExtractionNode.source_step`` is upstream and is an
   ``LLMStepNode``.
5. The graph is acyclic (we forbid cycles even though pydantic-graph
   permits them — DAG is the contract for the eval moat).

Reuses ``llm_pipeline.wiring._validate_dotted_path`` and
``_validate_instructions_field`` for the per-source checks.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.wiring import (
    Computed,
    FromInput,
    FromOutput,
    FromPipeline,
    Source,
    SourcesSpec,
    _validate_dotted_path,
    _validate_instructions_field,
)

if TYPE_CHECKING:
    from llm_pipeline.graph.nodes import (
        ExtractionNode,
        LLMStepNode,
        ReviewNode,
    )

__all__ = ["validate_pipeline"]


def validate_pipeline(
    pipeline_cls: type,
    *,
    nodes: list[type],
    start_node: type,
    input_cls: type[PipelineInputData] | None,
) -> None:
    """Run every Phase-1 compile-time check on ``pipeline_cls``.

    Raises ``TypeError`` or ``ValueError`` on any violation. Designed
    to fire at ``Pipeline.__init_subclass__`` time.
    """
    from llm_pipeline.graph.nodes import (
        ExtractionNode,
        LLMStepNode,
        ReviewNode,
    )

    _validate_pipeline_naming(pipeline_cls)
    _validate_input_data(pipeline_cls, input_cls)
    _validate_node_naming(nodes, LLMStepNode, ExtractionNode, ReviewNode)
    _validate_start_node(nodes, start_node)

    upstream_per_node = _topological_upstream(nodes, start_node)
    _assert_acyclic(nodes, upstream_per_node)

    for node_cls in nodes:
        upstream = upstream_per_node.get(node_cls, set())
        _validate_node(
            node_cls,
            upstream=upstream,
            input_cls=input_cls,
            llm_step_base=LLMStepNode,
            extraction_base=ExtractionNode,
            review_base=ReviewNode,
        )


# ---------------------------------------------------------------------------
# Pipeline-level checks
# ---------------------------------------------------------------------------


def _validate_pipeline_naming(pipeline_cls: type) -> None:
    if not pipeline_cls.__name__.endswith("Pipeline"):
        raise ValueError(
            f"Pipeline class '{pipeline_cls.__name__}' must end with "
            f"'Pipeline' suffix."
        )


def _validate_input_data(
    pipeline_cls: type, input_cls: type[PipelineInputData] | None,
) -> None:
    if input_cls is None:
        return
    if not (isinstance(input_cls, type) and issubclass(input_cls, PipelineInputData)):
        raise TypeError(
            f"{pipeline_cls.__name__}.INPUT_DATA must be a "
            f"PipelineInputData subclass, got {input_cls!r}."
        )


def _validate_node_naming(
    nodes: list[type],
    llm_step_base: type,
    extraction_base: type,
    review_base: type,
) -> None:
    for node in nodes:
        if issubclass(node, llm_step_base):
            if not node.__name__.endswith("Step"):
                raise ValueError(
                    f"LLMStepNode subclass '{node.__name__}' must end "
                    f"with 'Step' suffix."
                )
        elif issubclass(node, extraction_base):
            if not node.__name__.endswith("Extraction"):
                raise ValueError(
                    f"ExtractionNode subclass '{node.__name__}' must end "
                    f"with 'Extraction' suffix."
                )
        elif issubclass(node, review_base):
            if not node.__name__.endswith("Review"):
                raise ValueError(
                    f"ReviewNode subclass '{node.__name__}' must end "
                    f"with 'Review' suffix."
                )
        else:
            raise TypeError(
                f"Node '{node.__name__}' is not a subclass of "
                f"LLMStepNode, ExtractionNode, or ReviewNode."
            )


def _validate_start_node(nodes: list[type], start_node: type) -> None:
    if start_node not in nodes:
        raise ValueError(
            f"start_node {start_node.__name__} is not present in nodes."
        )


# ---------------------------------------------------------------------------
# Edge graph (topological upstream sets)
# ---------------------------------------------------------------------------


def _next_node_classes(node_cls: type, nodes: list[type]) -> set[type]:
    """Resolve the set of node classes reachable from ``node_cls.run``.

    Walks the return annotation only (parameter annotations may
    reference types only available under ``TYPE_CHECKING`` —
    ``GraphRunContext`` etc. — and we don't need them here). Resolves
    forward references against the localns built from ``nodes``, so
    cross-module string refs (``"TopicExtractionStep"``) work.
    """
    from pydantic_graph import End

    name_to_node = {n.__name__: n for n in nodes}
    return_annotation = node_cls.run.__annotations__.get("return")
    if return_annotation is None:
        return set()

    if isinstance(return_annotation, str):
        # Forward reference (or `from __future__ import annotations`).
        # Eval against the run method's module globals plus the node-
        # name localns. NameError on unknown name is swallowed; the
        # corresponding edge will surface when pydantic-graph's own
        # validator fires at Graph(nodes=...) construction.
        try:
            return_annotation = eval(  # noqa: S307 — controlled expression
                return_annotation,
                getattr(node_cls.run, "__globals__", {}),
                name_to_node | {"End": End},
            )
        except (NameError, SyntaxError):
            return set()

    return _extract_node_targets(return_annotation, name_to_node, end_cls=End)


def _extract_node_targets(
    annotation: Any,
    name_to_node: dict[str, type],
    *,
    end_cls: type,
) -> set[type]:
    import typing
    from types import UnionType

    targets: set[type] = set()
    origin = typing.get_origin(annotation)

    if origin is typing.Union or origin is UnionType:
        for arg in typing.get_args(annotation):
            targets |= _extract_node_targets(arg, name_to_node, end_cls=end_cls)
        return targets

    if origin is end_cls or annotation is end_cls:
        return targets  # End is a terminal; no node target.

    if isinstance(annotation, type):
        # Could be End (no args) or a node class.
        if annotation is end_cls:
            return targets
        if annotation.__name__ in name_to_node:
            targets.add(name_to_node[annotation.__name__])
        return targets

    if isinstance(annotation, str):
        node_cls = name_to_node.get(annotation)
        if node_cls is not None:
            targets.add(node_cls)
        return targets

    return targets


def _topological_upstream(
    nodes: list[type], start_node: type,
) -> dict[type, set[type]]:
    """For each node, compute the set of nodes that always precede it.

    Walks the graph from ``start_node`` along ``run()`` return-type
    edges. ``upstream[N]`` = every node visited on every path from
    ``start_node`` to ``N``, exclusive of ``N`` itself.

    Used to validate ``FromOutput(StepCls)`` references — they must
    always resolve to an output recorded earlier in the run.
    """
    upstream: dict[type, set[type]] = {n: set() for n in nodes}
    visited: set[type] = set()

    def _walk(current: type, ancestors: frozenset[type]) -> None:
        if current in ancestors:
            # Cycle — let the dedicated check raise.
            return
        new_upstream = upstream.get(current, set())
        if current in visited and ancestors.issubset(new_upstream):
            return
        visited.add(current)
        upstream[current] = new_upstream | ancestors
        next_ancestors = ancestors | {current}
        for nxt in _next_node_classes(current, nodes):
            _walk(nxt, next_ancestors)

    _walk(start_node, frozenset())
    return upstream


def _assert_acyclic(
    nodes: list[type], upstream: dict[type, set[type]],
) -> None:
    """Raise ``ValueError`` on any cycle in the node graph."""
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[type, int] = {n: WHITE for n in nodes}
    path: list[type] = []

    def _dfs(node: type) -> None:
        colour[node] = GRAY
        path.append(node)
        for nxt in _next_node_classes(node, nodes):
            if colour.get(nxt) == GRAY:
                cycle_start = path.index(nxt)
                cycle = path[cycle_start:] + [nxt]
                cycle_repr = " -> ".join(c.__name__ for c in cycle)
                raise ValueError(
                    f"Pipeline graph cycle: {cycle_repr}. "
                    f"Pipelines must be DAGs."
                )
            if colour.get(nxt) == WHITE:
                _dfs(nxt)
        path.pop()
        colour[node] = BLACK

    for node in nodes:
        if colour[node] == WHITE:
            _dfs(node)


# ---------------------------------------------------------------------------
# Per-node checks
# ---------------------------------------------------------------------------


def _validate_node(
    node_cls: type,
    *,
    upstream: set[type],
    input_cls: type[PipelineInputData] | None,
    llm_step_base: type,
    extraction_base: type,
    review_base: type,
) -> None:
    spec = getattr(node_cls, "inputs_spec", None)
    if spec is not None:
        _validate_inputs_spec(
            node_cls, spec, upstream=upstream, input_cls=input_cls,
        )

    if issubclass(node_cls, llm_step_base):
        _validate_llm_step(node_cls)
    elif issubclass(node_cls, extraction_base):
        _validate_extraction(node_cls, upstream=upstream, llm_step_base=llm_step_base)
    elif issubclass(node_cls, review_base):
        _validate_review(node_cls, upstream=upstream, llm_step_base=llm_step_base)


def _validate_llm_step(node_cls: type) -> None:
    from llm_pipeline.graph.instructions import LLMResultMixin

    inputs_cls = getattr(node_cls, "INPUTS", None)
    instructions_cls = getattr(node_cls, "INSTRUCTIONS", None)

    if inputs_cls is None:
        raise TypeError(f"{node_cls.__name__}.INPUTS must be set.")
    if instructions_cls is None:
        raise TypeError(f"{node_cls.__name__}.INSTRUCTIONS must be set.")
    if not (isinstance(instructions_cls, type) and issubclass(instructions_cls, LLMResultMixin)):
        raise TypeError(
            f"{node_cls.__name__}.INSTRUCTIONS must subclass "
            f"LLMResultMixin so every output carries confidence_score "
            f"+ notes and gets example-validated at class-load time. "
            f"Got {instructions_cls!r}."
        )

    # Naming: {Name}Inputs / {Name}Instructions
    prefix = node_cls.__name__[: -len("Step")]
    expected_inputs = f"{prefix}Inputs"
    if inputs_cls.__name__ != expected_inputs:
        raise ValueError(
            f"{node_cls.__name__}.INPUTS must be named "
            f"'{expected_inputs}', got '{inputs_cls.__name__}'."
        )
    expected_instructions = f"{prefix}Instructions"
    if instructions_cls.__name__ != expected_instructions:
        raise ValueError(
            f"{node_cls.__name__}.INSTRUCTIONS must be named "
            f"'{expected_instructions}', got '{instructions_cls.__name__}'."
        )


def _validate_extraction(
    node_cls: type, *, upstream: set[type], llm_step_base: type,
) -> None:
    from sqlmodel import SQLModel

    model_cls = getattr(node_cls, "MODEL", None)
    inputs_cls = getattr(node_cls, "INPUTS", None)
    source_step = getattr(node_cls, "source_step", None)

    if model_cls is None:
        raise TypeError(f"{node_cls.__name__}.MODEL must be set.")
    if not (isinstance(model_cls, type) and issubclass(model_cls, SQLModel)):
        raise TypeError(
            f"{node_cls.__name__}.MODEL must be a SQLModel subclass, "
            f"got {model_cls!r}."
        )
    if inputs_cls is None:
        raise TypeError(f"{node_cls.__name__}.INPUTS must be set.")
    if source_step is None:
        raise TypeError(f"{node_cls.__name__}.source_step must be set.")
    if not (isinstance(source_step, type) and issubclass(source_step, llm_step_base)):
        raise TypeError(
            f"{node_cls.__name__}.source_step must be an LLMStepNode "
            f"subclass, got {source_step!r}."
        )
    if source_step not in upstream:
        raise ValueError(
            f"{node_cls.__name__}.source_step references "
            f"'{source_step.__name__}', which is not upstream of this "
            f"extraction in the pipeline graph."
        )


def _validate_review(
    node_cls: type, *, upstream: set[type], llm_step_base: type,
) -> None:
    target_step = getattr(node_cls, "target_step", None)
    if target_step is None:
        raise TypeError(f"{node_cls.__name__}.target_step must be set.")
    if not (isinstance(target_step, type) and issubclass(target_step, llm_step_base)):
        raise TypeError(
            f"{node_cls.__name__}.target_step must be an LLMStepNode "
            f"subclass, got {target_step!r}."
        )
    if target_step not in upstream:
        raise ValueError(
            f"{node_cls.__name__}.target_step references "
            f"'{target_step.__name__}', which is not upstream of this "
            f"review in the pipeline graph."
        )


# ---------------------------------------------------------------------------
# Source-spec walkers (delegate field-existence checks to wiring helpers)
# ---------------------------------------------------------------------------


def _validate_inputs_spec(
    node_cls: type,
    spec: SourcesSpec,
    *,
    upstream: set[type],
    input_cls: type[PipelineInputData] | None,
) -> None:
    if not isinstance(spec, SourcesSpec):
        raise TypeError(
            f"{node_cls.__name__}.inputs_spec must be a SourcesSpec, "
            f"got {type(spec).__name__}."
        )
    for field_name, source in spec.field_sources.items():
        _validate_source(
            source,
            input_cls=input_cls,
            upstream=upstream,
            location=f"{node_cls.__name__}.inputs_spec[{field_name!r}]",
        )


def _validate_source(
    source: Source,
    *,
    input_cls: type[PipelineInputData] | None,
    upstream: set[type],
    location: str,
) -> None:
    if isinstance(source, FromInput):
        if input_cls is None:
            raise ValueError(
                f"{location}: FromInput(...) used but pipeline declares "
                f"no INPUT_DATA."
            )
        _validate_dotted_path(input_cls, source.path, location=location)
    elif isinstance(source, FromOutput):
        if source.step_cls not in upstream:
            raise ValueError(
                f"{location}: FromOutput references step "
                f"'{source.step_cls.__name__}', which is not upstream "
                f"of this node in the pipeline graph."
            )
        if source.field is not None:
            _validate_instructions_field(
                source.step_cls, source.field, location=location,
            )
    elif isinstance(source, FromPipeline):
        # PipelineDeps attrs are dynamic; skip static check.
        return
    elif isinstance(source, Computed):
        for inner in source.sources:
            _validate_source(
                inner,
                input_cls=input_cls,
                upstream=upstream,
                location=location,
            )
    else:
        raise TypeError(
            f"{location}: unknown Source subclass {type(source).__name__}."
        )
