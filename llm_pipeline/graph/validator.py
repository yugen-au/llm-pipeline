"""Compile-time validator for pydantic-graph-native pipelines.

Runs at ``Pipeline.__init_subclass__`` against an already-built
``PipelineSpec`` skeleton. Each helper *mutates the spec component
it describes* — appending issues to ``PipelineSpec.issues``,
``NodeSpec.issues``, or ``SourceSpec.issues`` as appropriate. No
exceptions are raised; the pipeline class always constructs and
``derive_issues(spec)`` returns the flat list when a flattened view
is needed.

Scope: pipeline-relational checks only. Class-property checks
(node naming, INPUTS / INSTRUCTIONS / MODEL / OUTPUT type and name
mismatches, INSTRUCTIONS-not-LLMResultMixin) live on each node
base class's ``__init_subclass__`` and surface via
``cls._init_subclass_errors`` — they exist on the class regardless
of whether any pipeline references it. The pipeline-time
``_stamp_class_captures`` copies them onto ``NodeSpec.issues`` so
the legacy ``cls._spec`` aggregate stays whole.

Checks performed here:

1. Pipeline-class naming convention: ``{Name}Pipeline``.
2. ``INPUT_DATA`` is a ``PipelineInputData`` subclass.
3. Every node binding's ``inputs_spec`` is a valid ``SourcesSpec``:
   - ``FromInput(path)`` resolves against ``INPUT_DATA``'s nested
     ``BaseModel`` fields → issue on the source.
   - ``FromOutput(NodeCls)`` references a node that appears
     **upstream** in the graph → issue on the source.
   - ``FromOutput(NodeCls, field=X)`` resolves against the upstream
     node's output schema → issue on the source.
4. Binding-kind cross-check: ``Step(NodeCls)`` wraps an
   ``LLMStepNode``, ``Extraction(...)`` wraps an ``ExtractionNode``,
   ``Review(...)`` wraps a ``ReviewNode`` → ``NodeSpec.issues``.
5. The graph is acyclic → pipeline-level issues.

The cross-check ``inputs_spec.inputs_cls`` vs ``cls.INPUTS`` is
owned by the wrapper's own ``__post_init__`` (captured into
``binding._init_post_errors`` and stamped onto ``NodeSpec.issues``
by the caller).

Phoenix-aware validation lives in a separate routine that runs at
discovery time.
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
    from llm_pipeline.graph.spec import (
        NodeSpec,
        PipelineSpec,
        SourceSpec,
        ValidationIssue,
    )

__all__ = ["validate_pipeline_into_spec"]


# Type alias: any per-node binding wrapper.
NodeBinding = Step | Extraction | Review


def validate_pipeline_into_spec(
    pipeline_cls: type,
    *,
    spec: "PipelineSpec",
    bindings: list[NodeBinding],
    input_cls: type[PipelineInputData] | None,
) -> None:
    """Run every structural compile-time check; mutate ``spec`` in place.

    ``bindings`` is the list of valid+deduped bindings (same list
    used to build ``spec.nodes`` — element order is 1:1 with
    ``spec.nodes``). Issues are appended onto the spec component
    they describe; nothing is returned.
    """
    from llm_pipeline.graph.nodes import (
        ExtractionNode,
        LLMStepNode,
        ReviewNode,
    )

    raw_nodes = [b.cls for b in bindings if isinstance(b.cls, type)]

    _validate_pipeline_naming(pipeline_cls, spec)
    _validate_input_data(pipeline_cls, input_cls, spec)
    # Per-node naming + per-kind contract violations are now captured
    # at class-definition time (each node base's __init_subclass__
    # populates ``cls._init_subclass_errors``). The pipeline-time
    # ``_stamp_class_captures`` copies them onto NodeSpec.issues.

    # Resolve start_node from spec.start_node (the name) back to the
    # actual class so we can run topological + acyclic checks.
    start_node = next(
        (n for n in raw_nodes if n.__name__ == spec.start_node), None,
    ) if spec.start_node else None
    if start_node is not None and raw_nodes:
        _validate_start_node(pipeline_cls, raw_nodes, start_node, spec)
        upstream_per_node = _topological_upstream(raw_nodes, start_node)
        _assert_acyclic(pipeline_cls, raw_nodes, spec)
    else:
        upstream_per_node = {n: set() for n in raw_nodes}

    for binding, node_spec in zip(bindings, spec.nodes):
        if not isinstance(binding.cls, type):
            continue
        _validate_binding_into_spec(
            binding,
            node_spec=node_spec,
            upstream=upstream_per_node.get(binding.cls, set()),
            input_cls=input_cls,
            llm_step_base=LLMStepNode,
            extraction_base=ExtractionNode,
            review_base=ReviewNode,
        )


# ---------------------------------------------------------------------------
# Pipeline-level checks → PipelineSpec.issues
# ---------------------------------------------------------------------------


def _validate_pipeline_naming(
    pipeline_cls: type, spec: "PipelineSpec",
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    if not pipeline_cls.__name__.endswith("Pipeline"):
        spec.issues.append(ValidationIssue(
            severity="error", code="pipeline_name_suffix",
            message=(
                f"Pipeline class '{pipeline_cls.__name__}' must end "
                f"with 'Pipeline' suffix."
            ),
            location=ValidationLocation(pipeline=pipeline_cls.__name__),
            suggestion=(
                f"Rename '{pipeline_cls.__name__}' to "
                f"'{pipeline_cls.__name__}Pipeline' (or similar)."
            ),
        ))


def _validate_input_data(
    pipeline_cls: type,
    input_cls: type[PipelineInputData] | None,
    spec: "PipelineSpec",
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    if input_cls is None:
        return
    if not (isinstance(input_cls, type) and issubclass(input_cls, PipelineInputData)):
        spec.issues.append(ValidationIssue(
            severity="error", code="input_data_wrong_type",
            message=(
                f"{pipeline_cls.__name__}.INPUT_DATA must be a "
                f"PipelineInputData subclass, got {input_cls!r}."
            ),
            location=ValidationLocation(
                pipeline=pipeline_cls.__name__, field="INPUT_DATA",
            ),
            suggestion=(
                f"Subclass PipelineInputData and assign INPUT_DATA = "
                f"<YourInputDataClass>."
            ),
        ))


def _validate_start_node(
    pipeline_cls: type,
    raw_nodes: list[type],
    start_node: type,
    spec: "PipelineSpec",
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    if start_node not in raw_nodes:
        start_repr = (
            start_node.__name__
            if isinstance(start_node, type) else repr(start_node)
        )
        spec.issues.append(ValidationIssue(
            severity="error", code="start_node_not_in_nodes",
            message=(
                f"start_node {start_repr} is not present in nodes."
            ),
            location=ValidationLocation(
                pipeline=pipeline_cls.__name__, field="start_node",
            ),
            suggestion=(
                "Set start_node to one of the classes referenced in "
                "the nodes list, or remove the explicit assignment "
                "(it defaults to nodes[0])."
            ),
        ))


# ---------------------------------------------------------------------------
# Edge graph (topological upstream sets) — used for FromOutput checks
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
    """For each node, compute the set of nodes that always precede it.

    Cycle-safe: the ``ancestors`` guard prevents infinite recursion if
    a cycle exists. Cycle reporting itself is done in
    :func:`_assert_acyclic`.
    """
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
    pipeline_cls: type,
    raw_nodes: list[type],
    spec: "PipelineSpec",
) -> None:
    """Append a ``pipeline_cycle`` issue for every cycle in the node graph."""
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[type, int] = {n: WHITE for n in raw_nodes}
    path: list[type] = []
    seen_cycles: set[str] = set()

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
                    spec.issues.append(ValidationIssue(
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


# ---------------------------------------------------------------------------
# Per-binding checks → NodeSpec.issues + per-source SourceSpec.issues
# ---------------------------------------------------------------------------


def _validate_binding_into_spec(
    binding: NodeBinding,
    *,
    node_spec: "NodeSpec",
    upstream: set[type],
    input_cls: type[PipelineInputData] | None,
    llm_step_base: type,
    extraction_base: type,
    review_base: type,
) -> None:
    """Validate a binding against its spec component, mutating in place."""
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    node_cls = binding.cls
    here = ValidationLocation(node=node_cls.__name__)

    # inputs_spec.inputs_cls vs cls.INPUTS is enforced by the wrapper's
    # __post_init__ (captured into binding._init_post_errors and stamped
    # onto NodeSpec.issues by the caller). Not re-checked here.

    # Walk the wiring sources, mutating each SourceSpec.issues.
    if isinstance(binding.inputs_spec, SourcesSpec):
        for field_name, source in binding.inputs_spec.field_sources.items():
            source_spec = node_spec.wiring.field_sources.get(field_name)
            if source_spec is None:
                continue  # defensive — should always exist
            _validate_source_into_spec(
                source,
                source_spec=source_spec,
                node_cls=node_cls,
                field_name=field_name,
                input_cls=input_cls,
                upstream=upstream,
            )

    # Binding-kind cross-check → node_spec.issues. Per-kind contract
    # checks (INPUTS/INSTRUCTIONS/MODEL/OUTPUT type + name conventions)
    # live on each node base's ``__init_subclass__`` and are stamped
    # onto ``node_spec.issues`` by ``_stamp_class_captures``.
    if isinstance(binding, Step):
        if not issubclass(node_cls, llm_step_base):
            node_spec.issues.append(ValidationIssue(
                severity="error", code="step_binding_wrong_kind",
                message=(
                    f"Step({node_cls.__name__}, ...): "
                    f"{node_cls.__name__} is not an LLMStepNode subclass."
                ),
                location=here,
                suggestion=(
                    f"Subclass LLMStepNode on {node_cls.__name__}, or "
                    f"use a different binding wrapper."
                ),
            ))
    elif isinstance(binding, Extraction):
        if not issubclass(node_cls, extraction_base):
            node_spec.issues.append(ValidationIssue(
                severity="error", code="extraction_binding_wrong_kind",
                message=(
                    f"Extraction({node_cls.__name__}, ...): "
                    f"{node_cls.__name__} is not an ExtractionNode subclass."
                ),
                location=here,
                suggestion=(
                    f"Subclass ExtractionNode on {node_cls.__name__}, or "
                    f"use a different binding wrapper."
                ),
            ))
    elif isinstance(binding, Review):
        if not issubclass(node_cls, review_base):
            node_spec.issues.append(ValidationIssue(
                severity="error", code="review_binding_wrong_kind",
                message=(
                    f"Review({node_cls.__name__}, ...): "
                    f"{node_cls.__name__} is not a ReviewNode subclass."
                ),
                location=here,
                suggestion=(
                    f"Subclass ReviewNode on {node_cls.__name__}, or "
                    f"use a different binding wrapper."
                ),
            ))


# ---------------------------------------------------------------------------
# Per-source walker → SourceSpec.issues
# ---------------------------------------------------------------------------


def _validate_source_into_spec(
    source: Source,
    *,
    source_spec: "SourceSpec",
    node_cls: type,
    field_name: str,
    input_cls: type[PipelineInputData] | None,
    upstream: set[type],
) -> None:
    """Validate a single source, appending to ``source_spec.issues``.

    Recurses into ``Computed`` sources, descending into
    ``source_spec.sources[i]`` for each inner source so issues stay
    localised to the precise input that's broken.
    """
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    here = ValidationLocation(node=node_cls.__name__, field=field_name)
    location_str = f"{node_cls.__name__} inputs_spec[{field_name!r}]"

    if isinstance(source, FromInput):
        if input_cls is None:
            source_spec.issues.append(ValidationIssue(
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
            return
        try:
            _validate_dotted_path(input_cls, source.path, location=location_str)
        except ValueError as exc:
            source_spec.issues.append(ValidationIssue(
                severity="error", code="from_input_unknown_path",
                message=str(exc),
                location=here,
                suggestion=(
                    f"Pick a path that exists on "
                    f"{input_cls.__name__}, or extend INPUT_DATA "
                    f"with the missing field."
                ),
            ))
    elif isinstance(source, FromOutput):
        if source.step_cls not in upstream:
            step_name = (
                source.step_cls.__name__
                if isinstance(source.step_cls, type)
                else repr(source.step_cls)
            )
            source_spec.issues.append(ValidationIssue(
                severity="error", code="from_output_not_upstream",
                message=(
                    f"{location_str}: FromOutput references node "
                    f"'{step_name}', which is not upstream of this "
                    f"node in the pipeline graph."
                ),
                location=here,
                suggestion=(
                    "Reorder nodes so the referenced node executes "
                    "before this one, or pick a different upstream "
                    "node."
                ),
            ))
            return
        if source.field is not None:
            try:
                _validate_instructions_field(
                    source.step_cls, source.field, location=location_str,
                )
            except ValueError as exc:
                source_spec.issues.append(ValidationIssue(
                    severity="error", code="from_output_unknown_field",
                    message=str(exc),
                    location=here,
                    suggestion=(
                        f"Pick a field that exists on "
                        f"{source.step_cls.__name__}'s output schema, "
                        f"or extend the schema with the missing field."
                    ),
                ))
    elif isinstance(source, FromPipeline):
        # PipelineDeps attrs are dynamic; skip static check.
        return
    elif isinstance(source, Computed):
        # Recurse into each inner source against its inner SourceSpec.
        inner_specs = source_spec.sources or []
        for inner_source, inner_spec in zip(source.sources, inner_specs):
            _validate_source_into_spec(
                inner_source,
                source_spec=inner_spec,
                node_cls=node_cls,
                field_name=field_name,
                input_cls=input_cls,
                upstream=upstream,
            )
    else:
        source_spec.issues.append(ValidationIssue(
            severity="error", code="unknown_source_type",
            message=(
                f"{location_str}: unknown Source subclass "
                f"{type(source).__name__}."
            ),
            location=here,
            suggestion=(
                "Use one of FromInput / FromOutput / FromPipeline / "
                "Computed."
            ),
        ))
