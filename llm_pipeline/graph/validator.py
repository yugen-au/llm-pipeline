"""Pipeline structural validator.

Returns ``list[ValidationIssue]`` with ``location.path`` set per the
:class:`llm_pipeline.specs.pipelines.PipelineFields` routing table.
The caller (``Pipeline.__init_subclass__``) stores the list on
``cls._init_subclass_errors``; the per-artifact ``PipelineBuilder``
later routes each issue onto the matching spec sub-component via
``attach_class_captures``.

Scope: pipeline-relational checks. Per-class contract checks (node
naming, INPUTS / INSTRUCTIONS / MODEL / OUTPUT etc.) live on each
node base's ``__init_subclass__``.
"""
from __future__ import annotations

from typing import Any

from llm_pipeline.inputs import PipelineInputData
from llm_pipeline.specs.pipelines import PipelineFields
from llm_pipeline.specs.validation import ValidationIssue, ValidationLocation
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


__all__ = ["validate_pipeline"]


NodeBinding = Step | Extraction | Review


def validate_pipeline(
    pipeline_cls: type,
    *,
    bindings: list[NodeBinding],
    input_cls: type[PipelineInputData] | None,
    start_node: type | None,
) -> list[ValidationIssue]:
    """Run every structural compile-time check; return collected issues.

    ``bindings`` is the deduped binding list (1:1 with the new spec's
    ``nodes`` rows). ``start_node`` is the resolved Python class
    (``cls.start_node``) or ``None``.
    """
    from llm_pipeline.graph.nodes import (
        ExtractionNode,
        LLMStepNode,
        ReviewNode,
    )

    issues: list[ValidationIssue] = []
    raw_nodes = [b.cls for b in bindings if isinstance(b.cls, type)]

    issues.extend(_check_pipeline_naming(pipeline_cls))
    issues.extend(_check_input_data(pipeline_cls, input_cls))

    if start_node is not None and raw_nodes:
        issues.extend(_check_start_node(pipeline_cls, raw_nodes, start_node))
        upstream_per_node = _topological_upstream(raw_nodes, start_node)
        issues.extend(_check_acyclic(pipeline_cls, raw_nodes))
    else:
        upstream_per_node = {n: set() for n in raw_nodes}

    for binding in bindings:
        if not isinstance(binding.cls, type):
            continue
        issues.extend(_check_binding(
            binding,
            upstream=upstream_per_node.get(binding.cls, set()),
            input_cls=input_cls,
            llm_step_base=LLMStepNode,
            extraction_base=ExtractionNode,
            review_base=ReviewNode,
        ))

    return issues


# ---------------------------------------------------------------------------
# Pipeline-level checks
# ---------------------------------------------------------------------------


def _check_pipeline_naming(pipeline_cls: type) -> list[ValidationIssue]:
    if pipeline_cls.__name__.endswith("Pipeline"):
        return []
    return [ValidationIssue(
        severity="error", code="pipeline_name_suffix",
        message=(
            f"Pipeline class '{pipeline_cls.__name__}' must end with "
            f"'Pipeline' suffix."
        ),
        location=ValidationLocation(pipeline=pipeline_cls.__name__),
        suggestion=(
            f"Rename '{pipeline_cls.__name__}' to "
            f"'{pipeline_cls.__name__}Pipeline' (or similar)."
        ),
    )]


def _check_input_data(
    pipeline_cls: type, input_cls: type[PipelineInputData] | None,
) -> list[ValidationIssue]:
    if input_cls is None:
        return []
    if isinstance(input_cls, type) and issubclass(input_cls, PipelineInputData):
        return []
    return [ValidationIssue(
        severity="error", code="input_data_wrong_type",
        message=(
            f"{pipeline_cls.__name__}.INPUT_DATA must be a "
            f"PipelineInputData subclass, got {input_cls!r}."
        ),
        location=ValidationLocation(
            pipeline=pipeline_cls.__name__,
            path=PipelineFields.INPUT_DATA,
        ),
        suggestion=(
            "Subclass PipelineInputData and assign INPUT_DATA = "
            "<YourInputDataClass>."
        ),
    )]


def _check_start_node(
    pipeline_cls: type, raw_nodes: list[type], start_node: type,
) -> list[ValidationIssue]:
    if start_node in raw_nodes:
        return []
    start_repr = (
        start_node.__name__
        if isinstance(start_node, type) else repr(start_node)
    )
    return [ValidationIssue(
        severity="error", code="start_node_not_in_nodes",
        message=f"start_node {start_repr} is not present in nodes.",
        location=ValidationLocation(pipeline=pipeline_cls.__name__),
        suggestion=(
            "Set start_node to one of the classes referenced in the "
            "nodes list, or remove the explicit assignment (defaults "
            "to nodes[0])."
        ),
    )]


# ---------------------------------------------------------------------------
# Cycles + topology
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
    """For each node, the set of nodes that always precede it."""
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


def _check_acyclic(
    pipeline_cls: type, raw_nodes: list[type],
) -> list[ValidationIssue]:
    """Return one ``pipeline_cycle`` issue per distinct cycle."""
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[type, int] = {n: WHITE for n in raw_nodes}
    path: list[type] = []
    seen_cycles: set[str] = set()
    issues: list[ValidationIssue] = []

    def _dfs(node: type) -> None:
        colour[node] = GRAY
        path.append(node)
        for nxt in _next_node_classes(node, raw_nodes):
            if colour.get(nxt) == GRAY:
                cycle_start = path.index(nxt)
                cycle = path[cycle_start:] + [nxt]
                cycle_repr = " -> ".join(c.__name__ for c in cycle)
                if cycle_repr not in seen_cycles:
                    seen_cycles.add(cycle_repr)
                    issues.append(ValidationIssue(
                        severity="error", code="pipeline_cycle",
                        message=(
                            f"Pipeline graph cycle: {cycle_repr}. "
                            f"Pipelines must be DAGs."
                        ),
                        location=ValidationLocation(
                            pipeline=pipeline_cls.__name__,
                        ),
                    ))
                continue
            if colour.get(nxt) == WHITE:
                _dfs(nxt)
        path.pop()
        colour[node] = BLACK

    for node in raw_nodes:
        if colour[node] == WHITE:
            _dfs(node)
    return issues


# ---------------------------------------------------------------------------
# Per-binding checks
# ---------------------------------------------------------------------------


def _node_name_for(binding: NodeBinding) -> str:
    """Return the snake_case registry key for ``binding.cls``."""
    cls = binding.cls
    if isinstance(binding, Step):
        return cls.step_name()
    suffix_map = {Extraction: "Extraction", Review: "Review"}
    suffix = next(
        (s for k, s in suffix_map.items() if isinstance(binding, k)),
        None,
    )
    from llm_pipeline.naming import to_snake_case
    return to_snake_case(cls.__name__, strip_suffix=suffix)


def _check_binding(
    binding: NodeBinding,
    *,
    upstream: set[type],
    input_cls: type[PipelineInputData] | None,
    llm_step_base: type,
    extraction_base: type,
    review_base: type,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    node_cls = binding.cls
    node_name = _node_name_for(binding)
    here = ValidationLocation(node=node_cls.__name__)

    # Per-source wiring checks.
    if isinstance(binding.inputs_spec, SourcesSpec):
        for field_name, source in binding.inputs_spec.field_sources.items():
            issues.extend(_check_source(
                source,
                node_cls=node_cls,
                node_name=node_name,
                field_name=field_name,
                input_cls=input_cls,
                upstream=upstream,
            ))

    # Binding-kind cross-check → routes to nodes[node_name].
    binding_path = PipelineFields.node(node_name)
    if isinstance(binding, Step) and not issubclass(node_cls, llm_step_base):
        issues.append(ValidationIssue(
            severity="error", code="step_binding_wrong_kind",
            message=(
                f"Step({node_cls.__name__}, ...): {node_cls.__name__} is "
                f"not an LLMStepNode subclass."
            ),
            location=ValidationLocation(
                node=node_cls.__name__, path=binding_path,
            ),
            suggestion=(
                f"Subclass LLMStepNode on {node_cls.__name__}, or use "
                f"a different binding wrapper."
            ),
        ))
    elif isinstance(binding, Extraction) and not issubclass(node_cls, extraction_base):
        issues.append(ValidationIssue(
            severity="error", code="extraction_binding_wrong_kind",
            message=(
                f"Extraction({node_cls.__name__}, ...): {node_cls.__name__} "
                f"is not an ExtractionNode subclass."
            ),
            location=ValidationLocation(
                node=node_cls.__name__, path=binding_path,
            ),
            suggestion=(
                f"Subclass ExtractionNode on {node_cls.__name__}, or use "
                f"a different binding wrapper."
            ),
        ))
    elif isinstance(binding, Review) and not issubclass(node_cls, review_base):
        issues.append(ValidationIssue(
            severity="error", code="review_binding_wrong_kind",
            message=(
                f"Review({node_cls.__name__}, ...): {node_cls.__name__} is "
                f"not a ReviewNode subclass."
            ),
            location=ValidationLocation(
                node=node_cls.__name__, path=binding_path,
            ),
            suggestion=(
                f"Subclass ReviewNode on {node_cls.__name__}, or use "
                f"a different binding wrapper."
            ),
        ))

    return issues


# ---------------------------------------------------------------------------
# Per-source walker
# ---------------------------------------------------------------------------


def _check_source(
    source: Source,
    *,
    node_cls: type,
    node_name: str,
    field_name: str,
    input_cls: type[PipelineInputData] | None,
    upstream: set[type],
) -> list[ValidationIssue]:
    """Validate a single source. Routes to nodes[name].wiring.field_sources[k]."""
    here = ValidationLocation(
        node=node_cls.__name__,
        path=PipelineFields.source(node_name, field_name),
    )
    location_str = f"{node_cls.__name__} inputs_spec[{field_name!r}]"
    issues: list[ValidationIssue] = []

    if isinstance(source, FromInput):
        if input_cls is None:
            issues.append(ValidationIssue(
                severity="error", code="from_input_no_input_data",
                message=(
                    f"{location_str}: FromInput(...) used but pipeline "
                    f"declares no INPUT_DATA."
                ),
                location=here,
                suggestion=(
                    "Set INPUT_DATA on the pipeline class to the "
                    "PipelineInputData subclass holding this field."
                ),
            ))
            return issues
        try:
            _validate_dotted_path(input_cls, source.path, location=location_str)
        except ValueError as exc:
            issues.append(ValidationIssue(
                severity="error", code="from_input_unknown_path",
                message=str(exc),
                location=here,
                suggestion=(
                    f"Pick a path that exists on {input_cls.__name__}, "
                    f"or extend INPUT_DATA with the missing field."
                ),
            ))
    elif isinstance(source, FromOutput):
        if source.step_cls not in upstream:
            step_name = (
                source.step_cls.__name__
                if isinstance(source.step_cls, type)
                else repr(source.step_cls)
            )
            issues.append(ValidationIssue(
                severity="error", code="from_output_not_upstream",
                message=(
                    f"{location_str}: FromOutput references node "
                    f"'{step_name}', which is not upstream of this node "
                    f"in the pipeline graph."
                ),
                location=here,
                suggestion=(
                    "Reorder nodes so the referenced node executes "
                    "before this one, or pick a different upstream node."
                ),
            ))
            return issues
        if source.field is not None:
            try:
                _validate_instructions_field(
                    source.step_cls, source.field, location=location_str,
                )
            except ValueError as exc:
                issues.append(ValidationIssue(
                    severity="error", code="from_output_unknown_field",
                    message=str(exc),
                    location=here,
                    suggestion=(
                        f"Pick a field that exists on "
                        f"{source.step_cls.__name__}'s output schema, or "
                        f"extend the schema with the missing field."
                    ),
                ))
    elif isinstance(source, FromPipeline):
        # PipelineDeps attrs are dynamic; skip static check.
        return issues
    elif isinstance(source, Computed):
        for inner in source.sources:
            issues.extend(_check_source(
                inner,
                node_cls=node_cls,
                node_name=node_name,
                field_name=field_name,
                input_cls=input_cls,
                upstream=upstream,
            ))
    else:
        issues.append(ValidationIssue(
            severity="error", code="unknown_source_type",
            message=(
                f"{location_str}: unknown Source subclass "
                f"{type(source).__name__}."
            ),
            location=here,
            suggestion=(
                "Use one of FromInput / FromOutput / FromPipeline / Computed."
            ),
        ))

    return issues
