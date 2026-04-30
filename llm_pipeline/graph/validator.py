"""Compile-time validator for pydantic-graph-native pipelines.

Runs at ``Pipeline.__init_subclass__``. Enforces the
"if it compiles, it works" contract:

1. Naming conventions: ``{Name}Pipeline``, ``{Name}Step``,
   ``{Name}Extraction``, ``{Name}Review``.
2. ``INPUT_DATA`` is a ``PipelineInputData`` subclass.
3. ``inputs_spec.inputs_cls`` matches the bound node's ``INPUTS`` (also
   enforced by the wrapper's own ``__post_init__``; re-asserted here for
   defence in depth).
4. Every node binding's ``inputs_spec`` is a valid ``SourcesSpec``:
   - ``FromInput(path)`` resolves against ``INPUT_DATA``'s nested
     ``BaseModel`` fields.
   - ``FromOutput(NodeCls)`` references a node that appears
     **upstream** in the graph (topologically reachable from
     ``start_node`` and visited before this node).
   - ``FromOutput(NodeCls, field=X)`` resolves against the upstream
     node's output schema (``INSTRUCTIONS`` for steps; ``MODEL``
     fields for extractions; ``OUTPUT`` for reviews).
5. ``LLMStepNode`` subclasses declare INPUTS/INSTRUCTIONS, INSTRUCTIONS
   subclasses ``LLMResultMixin``, and the ``prepare`` method's return
   annotation matches a concrete ``PromptVariables`` subclass (the
   latter check is delegated to ``LLMStepNode.__init_subclass__``).
6. ``ExtractionNode`` subclasses declare INPUTS/MODEL.
7. ``ReviewNode`` subclasses declare INPUTS/OUTPUT.
8. The graph is acyclic.

This file performs *only structural* checks. Phoenix-aware validation
(prompt existence, template-vs-PromptVariables drift, sync push) lives
in a separate routine that runs at discovery time.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.wiring import (
    Computed,
    Extraction,
    FromInput,
    FromOutput,
    FromPipeline,
    Review,
    Source,
    SourcesSpec,
    Step,
    _validate_dotted_path,
    _validate_instructions_field,
)

if TYPE_CHECKING:
    pass

__all__ = ["validate_pipeline"]


# Type alias: any per-node binding wrapper.
NodeBinding = Step | Extraction | Review


def validate_pipeline(
    pipeline_cls: type,
    *,
    nodes: list[NodeBinding],
    start_node: type,
    input_cls: type[PipelineInputData] | None,
) -> None:
    """Run every structural compile-time check on ``pipeline_cls``.

    ``nodes`` is the list of ``Step | Extraction | Review`` wrappers
    declared on the pipeline. Raises ``TypeError`` or ``ValueError``
    on any violation.
    """
    from llm_pipeline.graph.nodes import (
        ExtractionNode,
        LLMStepNode,
        ReviewNode,
    )

    raw_nodes = [b.cls for b in nodes]

    _validate_pipeline_naming(pipeline_cls)
    _validate_input_data(pipeline_cls, input_cls)
    _validate_node_naming(raw_nodes, LLMStepNode, ExtractionNode, ReviewNode)
    _validate_start_node(raw_nodes, start_node)

    upstream_per_node = _topological_upstream(raw_nodes, start_node)
    _assert_acyclic(raw_nodes, upstream_per_node)

    for binding in nodes:
        upstream = upstream_per_node.get(binding.cls, set())
        _validate_binding(
            binding,
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
    raw_nodes: list[type],
    llm_step_base: type,
    extraction_base: type,
    review_base: type,
) -> None:
    for node in raw_nodes:
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


def _validate_start_node(raw_nodes: list[type], start_node: type) -> None:
    if start_node not in raw_nodes:
        raise ValueError(
            f"start_node {start_node.__name__} is not present in nodes."
        )


# ---------------------------------------------------------------------------
# Edge graph (topological upstream sets)
# ---------------------------------------------------------------------------


def _next_node_classes(node_cls: type, raw_nodes: list[type]) -> set[type]:
    """Resolve the set of node classes reachable from ``node_cls.run``."""
    from pydantic_graph import End

    name_to_node = {n.__name__: n for n in raw_nodes}
    return_annotation = node_cls.run.__annotations__.get("return")
    if return_annotation is None:
        return set()

    if isinstance(return_annotation, str):
        try:
            return_annotation = eval(  # noqa: S307
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
        return targets

    if isinstance(annotation, type):
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
    raw_nodes: list[type], start_node: type,
) -> dict[type, set[type]]:
    """For each node, compute the set of nodes that always precede it."""
    upstream: dict[type, set[type]] = {n: set() for n in raw_nodes}
    visited: set[type] = set()

    def _walk(current: type, ancestors: frozenset[type]) -> None:
        if current in ancestors:
            return
        new_upstream = upstream.get(current, set())
        if current in visited and ancestors.issubset(new_upstream):
            return
        visited.add(current)
        upstream[current] = new_upstream | ancestors
        next_ancestors = ancestors | {current}
        for nxt in _next_node_classes(current, raw_nodes):
            _walk(nxt, next_ancestors)

    _walk(start_node, frozenset())
    return upstream


def _assert_acyclic(
    raw_nodes: list[type], upstream: dict[type, set[type]],
) -> None:
    """Raise ``ValueError`` on any cycle in the node graph."""
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[type, int] = {n: WHITE for n in raw_nodes}
    path: list[type] = []

    def _dfs(node: type) -> None:
        colour[node] = GRAY
        path.append(node)
        for nxt in _next_node_classes(node, raw_nodes):
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

    for node in raw_nodes:
        if colour[node] == WHITE:
            _dfs(node)


# ---------------------------------------------------------------------------
# Per-binding checks
# ---------------------------------------------------------------------------


def _validate_binding(
    binding: NodeBinding,
    *,
    upstream: set[type],
    input_cls: type[PipelineInputData] | None,
    llm_step_base: type,
    extraction_base: type,
    review_base: type,
) -> None:
    """Validate a single ``Step | Extraction | Review`` binding."""
    node_cls = binding.cls

    # Cross-check inputs_spec.inputs_cls vs cls.INPUTS (also enforced
    # in wrapper __post_init__).
    declared_inputs = getattr(node_cls, "INPUTS", None)
    if declared_inputs is not None and binding.inputs_spec.inputs_cls is not declared_inputs:
        raise ValueError(
            f"{type(binding).__name__}({node_cls.__name__}, ...): "
            f"inputs_spec.inputs_cls is "
            f"{binding.inputs_spec.inputs_cls.__name__}, but "
            f"{node_cls.__name__}.INPUTS is "
            f"{declared_inputs.__name__}."
        )

    _validate_inputs_spec(
        node_cls, binding.inputs_spec,
        upstream=upstream, input_cls=input_cls,
    )

    if isinstance(binding, Step):
        if not issubclass(node_cls, llm_step_base):
            raise TypeError(
                f"Step({node_cls.__name__}, ...): {node_cls.__name__} "
                f"is not an LLMStepNode subclass."
            )
        _validate_llm_step(node_cls)
    elif isinstance(binding, Extraction):
        if not issubclass(node_cls, extraction_base):
            raise TypeError(
                f"Extraction({node_cls.__name__}, ...): "
                f"{node_cls.__name__} is not an ExtractionNode subclass."
            )
        _validate_extraction(node_cls)
    elif isinstance(binding, Review):
        if not issubclass(node_cls, review_base):
            raise TypeError(
                f"Review({node_cls.__name__}, ...): {node_cls.__name__} "
                f"is not a ReviewNode subclass."
            )
        _validate_review(node_cls)


def _validate_llm_step(node_cls: type) -> None:
    """Check Step contract — INPUTS/INSTRUCTIONS shape and naming."""
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

    # Naming: {Name}Inputs / {Name}Instructions.
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


def _validate_extraction(node_cls: type) -> None:
    """Check Extraction contract — INPUTS/MODEL declared and well-typed."""
    from sqlmodel import SQLModel

    model_cls = getattr(node_cls, "MODEL", None)
    inputs_cls = getattr(node_cls, "INPUTS", None)

    if model_cls is None:
        raise TypeError(f"{node_cls.__name__}.MODEL must be set.")
    if not (isinstance(model_cls, type) and issubclass(model_cls, SQLModel)):
        raise TypeError(
            f"{node_cls.__name__}.MODEL must be a SQLModel subclass, "
            f"got {model_cls!r}."
        )
    if inputs_cls is None:
        raise TypeError(f"{node_cls.__name__}.INPUTS must be set.")


def _validate_review(node_cls: type) -> None:
    """Check Review contract — INPUTS/OUTPUT declared."""
    from pydantic import BaseModel

    inputs_cls = getattr(node_cls, "INPUTS", None)
    output_cls = getattr(node_cls, "OUTPUT", None)

    if inputs_cls is None:
        raise TypeError(f"{node_cls.__name__}.INPUTS must be set.")
    if output_cls is None:
        raise TypeError(f"{node_cls.__name__}.OUTPUT must be set.")
    if not (isinstance(output_cls, type) and issubclass(output_cls, BaseModel)):
        raise TypeError(
            f"{node_cls.__name__}.OUTPUT must be a Pydantic BaseModel "
            f"subclass declaring the reviewer's response shape, got "
            f"{output_cls!r}."
        )


# ---------------------------------------------------------------------------
# Source-spec walkers
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
            f"{node_cls.__name__} binding.inputs_spec must be a "
            f"SourcesSpec, got {type(spec).__name__}."
        )
    for field_name, source in spec.field_sources.items():
        _validate_source(
            source,
            input_cls=input_cls,
            upstream=upstream,
            location=f"{node_cls.__name__} inputs_spec[{field_name!r}]",
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
                f"{location}: FromOutput references node "
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
