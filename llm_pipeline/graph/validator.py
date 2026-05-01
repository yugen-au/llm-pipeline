"""Compile-time validator for pydantic-graph-native pipelines.

Runs at ``Pipeline.__init_subclass__``. Enforces the
"if it compiles, it works" contract — but *captures* every violation
as a :class:`ValidationIssue` rather than raising. The class object
always constructs; ``Pipeline.__init_subclass__`` aggregates the
captures into ``cls._init_subclass_errors`` and ``derive_issues`` reads
them off the spec.

Checks performed:

1. Naming conventions: ``{Name}Pipeline``, ``{Name}Step``,
   ``{Name}Extraction``, ``{Name}Review``.
2. ``INPUT_DATA`` is a ``PipelineInputData`` subclass.
3. Every node binding's ``inputs_spec`` is a valid ``SourcesSpec``:
   - ``FromInput(path)`` resolves against ``INPUT_DATA``'s nested
     ``BaseModel`` fields.
   - ``FromOutput(NodeCls)`` references a node that appears
     **upstream** in the graph (topologically reachable from
     ``start_node`` and visited before this node).
   - ``FromOutput(NodeCls, field=X)`` resolves against the upstream
     node's output schema.
4. Per-kind contract: ``LLMStepNode`` declares INPUTS/INSTRUCTIONS
   with the matching ``{Name}Inputs`` / ``{Name}Instructions`` names
   and INSTRUCTIONS subclasses ``LLMResultMixin``;
   ``ExtractionNode`` declares ``MODEL`` (a SQLModel subclass);
   ``ReviewNode`` declares ``OUTPUT`` (a Pydantic ``BaseModel``).
5. The graph is acyclic.

The cross-check ``inputs_spec.inputs_cls`` vs ``cls.INPUTS`` is owned
by the wrapper's own ``__post_init__`` (captured into
``binding._init_post_errors``). Not duplicated here.

This module performs only structural checks. Phoenix-aware validation
(prompt existence, template-vs-PromptVariables drift) lives in a
separate routine that runs at discovery time.
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
    from llm_pipeline.graph.spec import ValidationIssue

__all__ = ["validate_pipeline"]


# Type alias: any per-node binding wrapper.
NodeBinding = Step | Extraction | Review


def validate_pipeline(
    pipeline_cls: type,
    *,
    nodes: list[NodeBinding],
    start_node: type | None,
    input_cls: type[PipelineInputData] | None,
) -> list["ValidationIssue"]:
    """Run every structural compile-time check; return captured issues.

    ``nodes`` is the list of valid (already-typechecked) ``Step |
    Extraction | Review`` wrappers declared on the pipeline.
    ``start_node`` may be ``None`` for the very-broken case where no
    node binding survived earlier filtering. Returns the list of
    captured issues — empty when the pipeline is structurally clean.
    """
    from llm_pipeline.graph.nodes import (
        ExtractionNode,
        LLMStepNode,
        ReviewNode,
    )

    errors: list[ValidationIssue] = []
    raw_nodes = [b.cls for b in nodes if isinstance(b.cls, type)]

    _validate_pipeline_naming(pipeline_cls, errors)
    _validate_input_data(pipeline_cls, input_cls, errors)
    _validate_node_naming(
        raw_nodes, LLMStepNode, ExtractionNode, ReviewNode, errors,
    )

    if start_node is not None and raw_nodes:
        _validate_start_node(pipeline_cls, raw_nodes, start_node, errors)
        upstream_per_node = _topological_upstream(raw_nodes, start_node)
        _assert_acyclic(pipeline_cls, raw_nodes, errors)
    else:
        upstream_per_node = {n: set() for n in raw_nodes}

    for binding in nodes:
        if not isinstance(binding.cls, type):
            continue  # binding wrapper already captured the issue
        upstream = upstream_per_node.get(binding.cls, set())
        _validate_binding(
            binding,
            upstream=upstream,
            input_cls=input_cls,
            llm_step_base=LLMStepNode,
            extraction_base=ExtractionNode,
            review_base=ReviewNode,
            errors=errors,
        )
    return errors


# ---------------------------------------------------------------------------
# Pipeline-level checks
# ---------------------------------------------------------------------------


def _validate_pipeline_naming(
    pipeline_cls: type, errors: list["ValidationIssue"],
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    if not pipeline_cls.__name__.endswith("Pipeline"):
        errors.append(ValidationIssue(
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
        ))


def _validate_input_data(
    pipeline_cls: type,
    input_cls: type[PipelineInputData] | None,
    errors: list["ValidationIssue"],
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    if input_cls is None:
        return
    if not (isinstance(input_cls, type) and issubclass(input_cls, PipelineInputData)):
        errors.append(ValidationIssue(
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


def _validate_node_naming(
    raw_nodes: list[type],
    llm_step_base: type,
    extraction_base: type,
    review_base: type,
    errors: list["ValidationIssue"],
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    for node in raw_nodes:
        if issubclass(node, llm_step_base):
            if not node.__name__.endswith("Step"):
                errors.append(ValidationIssue(
                    severity="error", code="step_name_suffix",
                    message=(
                        f"LLMStepNode subclass '{node.__name__}' must end "
                        f"with 'Step' suffix."
                    ),
                    location=ValidationLocation(node=node.__name__),
                    suggestion=(
                        f"Rename to '{node.__name__}Step' or similar."
                    ),
                ))
        elif issubclass(node, extraction_base):
            if not node.__name__.endswith("Extraction"):
                errors.append(ValidationIssue(
                    severity="error", code="extraction_name_suffix",
                    message=(
                        f"ExtractionNode subclass '{node.__name__}' must "
                        f"end with 'Extraction' suffix."
                    ),
                    location=ValidationLocation(node=node.__name__),
                    suggestion=(
                        f"Rename to '{node.__name__}Extraction' or similar."
                    ),
                ))
        elif issubclass(node, review_base):
            if not node.__name__.endswith("Review"):
                errors.append(ValidationIssue(
                    severity="error", code="review_name_suffix",
                    message=(
                        f"ReviewNode subclass '{node.__name__}' must end "
                        f"with 'Review' suffix."
                    ),
                    location=ValidationLocation(node=node.__name__),
                    suggestion=(
                        f"Rename to '{node.__name__}Review' or similar."
                    ),
                ))
        else:
            errors.append(ValidationIssue(
                severity="error", code="node_unknown_base",
                message=(
                    f"Node '{node.__name__}' is not a subclass of "
                    f"LLMStepNode, ExtractionNode, or ReviewNode."
                ),
                location=ValidationLocation(node=node.__name__),
                suggestion=(
                    "Subclass one of LLMStepNode / ExtractionNode / "
                    "ReviewNode."
                ),
            ))


def _validate_start_node(
    pipeline_cls: type,
    raw_nodes: list[type],
    start_node: type,
    errors: list["ValidationIssue"],
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    if start_node not in raw_nodes:
        start_repr = (
            start_node.__name__
            if isinstance(start_node, type) else repr(start_node)
        )
        errors.append(ValidationIssue(
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
    errors: list["ValidationIssue"],
) -> None:
    """Capture a ``pipeline_cycle`` issue for every cycle in the node graph."""
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
                    errors.append(ValidationIssue(
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
    errors: list["ValidationIssue"],
) -> None:
    """Validate a single ``Step | Extraction | Review`` binding."""
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    node_cls = binding.cls
    here = ValidationLocation(node=node_cls.__name__)

    # inputs_spec.inputs_cls vs cls.INPUTS is enforced by the wrapper's
    # __post_init__ (captured into binding._init_post_errors). Not
    # re-checked here to avoid double-reporting.

    _validate_inputs_spec(
        node_cls, binding.inputs_spec,
        upstream=upstream, input_cls=input_cls, errors=errors,
    )

    if isinstance(binding, Step):
        if not issubclass(node_cls, llm_step_base):
            errors.append(ValidationIssue(
                severity="error", code="step_binding_wrong_kind",
                message=(
                    f"Step({node_cls.__name__}, ...): {node_cls.__name__} "
                    f"is not an LLMStepNode subclass."
                ),
                location=here,
                suggestion=(
                    f"Subclass LLMStepNode on {node_cls.__name__}, or "
                    f"use a different binding wrapper."
                ),
            ))
            return
        _validate_llm_step(node_cls, errors)
    elif isinstance(binding, Extraction):
        if not issubclass(node_cls, extraction_base):
            errors.append(ValidationIssue(
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
            return
        _validate_extraction(node_cls, errors)
    elif isinstance(binding, Review):
        if not issubclass(node_cls, review_base):
            errors.append(ValidationIssue(
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
            return
        _validate_review(node_cls, errors)


def _validate_llm_step(
    node_cls: type, errors: list["ValidationIssue"],
) -> None:
    """Capture Step contract violations beyond what ``__init_subclass__`` caught.

    Bare ``INPUTS is None`` / ``INSTRUCTIONS is None`` are already on
    ``node_cls._init_subclass_errors`` (captured at
    ``LLMStepNode.__init_subclass__``). This function adds the
    cross-class checks: INSTRUCTIONS subclassing, naming conventions.
    """
    from llm_pipeline.graph.instructions import LLMResultMixin
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    inputs_cls = getattr(node_cls, "INPUTS", None)
    instructions_cls = getattr(node_cls, "INSTRUCTIONS", None)

    if (
        instructions_cls is not None
        and not (
            isinstance(instructions_cls, type)
            and issubclass(instructions_cls, LLMResultMixin)
        )
    ):
        errors.append(ValidationIssue(
            severity="error", code="step_instructions_not_llm_result_mixin",
            message=(
                f"{node_cls.__name__}.INSTRUCTIONS must subclass "
                f"LLMResultMixin so every output carries confidence_score "
                f"+ notes and gets example-validated at class-load time. "
                f"Got {instructions_cls!r}."
            ),
            location=ValidationLocation(
                node=node_cls.__name__, field="INSTRUCTIONS",
            ),
            suggestion=(
                f"Make {getattr(instructions_cls, '__name__', 'INSTRUCTIONS')} "
                f"subclass LLMResultMixin."
            ),
        ))

    # Naming: {Name}Inputs / {Name}Instructions. Only meaningful when the
    # node name ends with 'Step' (otherwise step_name_suffix already fired).
    if not node_cls.__name__.endswith("Step"):
        return
    prefix = node_cls.__name__[: -len("Step")]
    if inputs_cls is not None:
        expected_inputs = f"{prefix}Inputs"
        if inputs_cls.__name__ != expected_inputs:
            errors.append(ValidationIssue(
                severity="error", code="step_inputs_name_mismatch",
                message=(
                    f"{node_cls.__name__}.INPUTS must be named "
                    f"'{expected_inputs}', got '{inputs_cls.__name__}'."
                ),
                location=ValidationLocation(
                    node=node_cls.__name__, field="INPUTS",
                ),
                suggestion=(
                    f"Rename {inputs_cls.__name__} to {expected_inputs}."
                ),
            ))
    if instructions_cls is not None:
        expected_instructions = f"{prefix}Instructions"
        if instructions_cls.__name__ != expected_instructions:
            errors.append(ValidationIssue(
                severity="error", code="step_instructions_name_mismatch",
                message=(
                    f"{node_cls.__name__}.INSTRUCTIONS must be named "
                    f"'{expected_instructions}', got "
                    f"'{instructions_cls.__name__}'."
                ),
                location=ValidationLocation(
                    node=node_cls.__name__, field="INSTRUCTIONS",
                ),
                suggestion=(
                    f"Rename {instructions_cls.__name__} to "
                    f"{expected_instructions}."
                ),
            ))


def _validate_extraction(
    node_cls: type, errors: list["ValidationIssue"],
) -> None:
    """Capture Extraction-only contract violations beyond ``__init_subclass__``.

    ``MODEL is None`` is on ``node_cls._init_subclass_errors`` already.
    Here we only verify MODEL's type when present.
    """
    from sqlmodel import SQLModel

    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    model_cls = getattr(node_cls, "MODEL", None)
    if (
        model_cls is not None
        and not (
            isinstance(model_cls, type) and issubclass(model_cls, SQLModel)
        )
    ):
        errors.append(ValidationIssue(
            severity="error", code="extraction_model_not_sqlmodel",
            message=(
                f"{node_cls.__name__}.MODEL must be a SQLModel subclass, "
                f"got {model_cls!r}."
            ),
            location=ValidationLocation(
                node=node_cls.__name__, field="MODEL",
            ),
            suggestion=(
                "Subclass sqlmodel.SQLModel and set MODEL accordingly."
            ),
        ))


def _validate_review(
    node_cls: type, errors: list["ValidationIssue"],
) -> None:
    """Capture Review-only contract violations beyond ``__init_subclass__``.

    ``OUTPUT is None`` is on ``node_cls._init_subclass_errors`` already.
    Here we only verify OUTPUT's type when present.
    """
    from pydantic import BaseModel

    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    output_cls = getattr(node_cls, "OUTPUT", None)
    if (
        output_cls is not None
        and not (
            isinstance(output_cls, type) and issubclass(output_cls, BaseModel)
        )
    ):
        errors.append(ValidationIssue(
            severity="error", code="review_output_not_basemodel",
            message=(
                f"{node_cls.__name__}.OUTPUT must be a Pydantic BaseModel "
                f"subclass declaring the reviewer's response shape, got "
                f"{output_cls!r}."
            ),
            location=ValidationLocation(
                node=node_cls.__name__, field="OUTPUT",
            ),
            suggestion=(
                "Subclass pydantic.BaseModel and set OUTPUT accordingly."
            ),
        ))


# ---------------------------------------------------------------------------
# Source-spec walkers
# ---------------------------------------------------------------------------


def _validate_inputs_spec(
    node_cls: type,
    spec: SourcesSpec,
    *,
    upstream: set[type],
    input_cls: type[PipelineInputData] | None,
    errors: list["ValidationIssue"],
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    if not isinstance(spec, SourcesSpec):
        # Already captured by binding wrapper's __post_init__ as
        # binding_inputs_spec_wrong_type — skip to avoid double-reporting.
        return
    for field_name, source in spec.field_sources.items():
        _validate_source(
            source,
            node_cls=node_cls,
            field_name=field_name,
            input_cls=input_cls,
            upstream=upstream,
            errors=errors,
        )


def _validate_source(
    source: Source,
    *,
    node_cls: type,
    field_name: str,
    input_cls: type[PipelineInputData] | None,
    upstream: set[type],
    errors: list["ValidationIssue"],
) -> None:
    from llm_pipeline.graph.spec import ValidationIssue, ValidationLocation

    here = ValidationLocation(node=node_cls.__name__, field=field_name)
    location_str = f"{node_cls.__name__} inputs_spec[{field_name!r}]"

    if isinstance(source, FromInput):
        if input_cls is None:
            errors.append(ValidationIssue(
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
            errors.append(ValidationIssue(
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
            errors.append(ValidationIssue(
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
                errors.append(ValidationIssue(
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
        for inner in source.sources:
            _validate_source(
                inner,
                node_cls=node_cls,
                field_name=field_name,
                input_cls=input_cls,
                upstream=upstream,
                errors=errors,
            )
    else:
        errors.append(ValidationIssue(
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
