"""Typed introspection surface for pipelines.

``Pipeline.inspect()`` returns a fully-typed ``PipelineSpec`` carrying
everything known about a pipeline at compile time:

- Graph topology (nodes + edges).
- Each node's contract (INPUTS schema, output schema, tools, kind).
- Each binding's wiring (``inputs_spec`` serialised into source
  descriptors).
- For step nodes: prompt info (PromptVariables schema, INSTRUCTIONS
  schema, DEFAULT_TOOLS schema). Phoenix-aware fields (template
  text, model, sync status) are populated by the discovery-time
  Phoenix validator; they're ``None`` until that runs.

Reused by:

- ``/api/pipelines/*`` UI routes (typed JSON for the frontend).
- LLM-author tooling (the LLM consumes this spec to write/modify
  pipelines without running the framework).
- The future Phoenix-aware validator + sync routine, which fills in
  the placeholder fields.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from llm_pipeline.graph.pipeline import Pipeline


__all__ = [
    "EdgeSpec",
    "NodeSpec",
    "PipelineSpec",
    "PromptSpec",
    "SourceSpec",
    "ToolSpec",
    "ValidationIssue",
    "ValidationLocation",
    "ValidationSummary",
    "WiringSpec",
    "build_pipeline_spec",
    "derive_issues",
    "is_runnable",
]


# ---------------------------------------------------------------------------
# Source descriptors (FromInput / FromOutput / FromPipeline / Computed)
# ---------------------------------------------------------------------------


class SourceSpec(BaseModel):
    """Serialised view of a single ``Source`` adapter.

    ``kind`` is the discriminator. Each variant uses a subset of the
    optional fields:

    - ``from_input``: ``path``
    - ``from_output``: ``step_cls``, ``index``, ``field``
    - ``from_pipeline``: ``attr``
    - ``computed``: ``fn`` (function repr) + ``sources`` (recursive)

    ``issues`` carries any validation problems specific to this
    source adapter (e.g. ``from_input_unknown_path`` when the
    referenced INPUT_DATA path doesn't exist). The frontend reads
    ``node.wiring.field_sources[name].issues`` to render an inline
    error on that exact input.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["from_input", "from_output", "from_pipeline", "computed"]
    path: str | None = None
    step_cls: str | None = None
    index: int | None = None
    field: str | None = None
    attr: str | None = None
    fn: str | None = None
    sources: list["SourceSpec"] | None = None
    issues: list["ValidationIssue"] = Field(default_factory=list)


class WiringSpec(BaseModel):
    """A node's pipeline-level wiring (its ``inputs_spec`` serialised)."""

    model_config = ConfigDict(extra="forbid")

    inputs_cls: str  # fully-qualified class name
    field_sources: dict[str, SourceSpec]


# ---------------------------------------------------------------------------
# Validation issues (derived from the spec at read time)
# ---------------------------------------------------------------------------


class ValidationLocation(BaseModel):
    """Where in a pipeline a validation issue lives.

    Free-form: any combination of pipeline / node / field may be set.
    Empty values mean "scope not narrower than the parent". e.g.,
    a wiring drift on a step's INPUTS field has all three set; a
    pipeline-wide cycle issue has only ``pipeline``.
    """

    model_config = ConfigDict(extra="forbid")

    pipeline: str | None = None
    node: str | None = None  # node class name (e.g. "TopicExtractionStep")
    field: str | None = None  # attribute / member name within the node


class ValidationIssue(BaseModel):
    """A single thing wrong (or worth flagging) about a pipeline.

    Issues are localised onto the spec component they describe:
    pipeline-wide issues sit on ``PipelineSpec.issues``; node-level
    on ``NodeSpec.issues``; per-wiring-field on
    ``SourceSpec.issues``; prompt-class on ``PromptSpec.issues``.
    The frontend walks the spec and renders error styling on the
    component carrying the issue — no string-matching by location.

    :func:`derive_issues` returns a flat list across every level
    when callers need the full set (e.g. :func:`is_runnable`,
    ``ValidationSummary.issue_count``).

    Severity gates runnability: any ``error`` blocks the pipeline
    from running; ``warning`` is informational.

    The ``code`` is a stable machine-readable identifier (e.g.
    ``missing_inputs``, ``from_output_not_upstream``). Frontends
    can branch UX on it; humans read ``message`` and
    ``suggestion``. ``location`` retains pipeline / node / field
    pointers for human-readable context (logs, error messages),
    not for routing.
    """

    model_config = ConfigDict(extra="forbid")

    severity: Literal["error", "warning"]
    code: str
    message: str
    location: ValidationLocation
    suggestion: str | None = None


class ValidationSummary(BaseModel):
    """API-shaped digest of a pipeline's validation state.

    Computed from a ``PipelineEntry`` for the ``GET /api/pipelines``
    list response. The frontend renders ``severity`` as a badge; the
    ``issues`` list backs the detail panel.
    """

    model_config = ConfigDict(extra="forbid")

    runnable: bool
    severity: Literal["clean", "warnings", "errors", "import_error"]
    issue_count: int
    issues: list[ValidationIssue]


# ---------------------------------------------------------------------------
# Tool + Prompt
# ---------------------------------------------------------------------------


class ToolSpec(BaseModel):
    """A ``PipelineTool`` subclass's contract."""

    model_config = ConfigDict(extra="forbid")

    name: str  # snake_case tool name
    cls: str  # fully-qualified class name
    inputs_schema: dict[str, Any]  # tool.Inputs.model_json_schema()
    args_schema: dict[str, Any]  # tool.Args.model_json_schema()


class PromptSpec(BaseModel):
    """Per-step prompt info.

    Code-side fields are always populated. Phoenix-aware fields
    (``system_template``, ``user_template``, ``model``, ``in_sync``,
    ``drift``) are filled by the discovery-time Phoenix validator;
    ``None`` until that runs.

    ``issues`` carries any prompt-class problems
    (``missing_field_description``, ``auto_vars_*``). The frontend
    renders these on the prompt section of the node card.
    """

    model_config = ConfigDict(extra="forbid")

    name: str  # step_name() — 1:1 with the Phoenix prompt name
    prompt_variables_cls: str  # fully-qualified XxxPrompt class

    # Code-derived schemas (always available). variable_definitions is
    # message-agnostic — same flat shape Phoenix uses internally.
    variable_definitions: dict[str, Any]   # JSON Schema for the prompt's vars
    auto_vars: dict[str, str]              # framework-supplied placeholders
    response_format: dict[str, Any]        # INSTRUCTIONS schema
    tools: list[ToolSpec]                  # DEFAULT_TOOLS contract

    # Phoenix-aware (populated at discovery; None at __init_subclass__).
    system_template: str | None = None
    user_template: str | None = None
    model: str | None = None
    in_sync: bool | None = None
    drift: dict[str, str] | None = None

    issues: list["ValidationIssue"] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Node + Edge
# ---------------------------------------------------------------------------


class NodeSpec(BaseModel):
    """Per-node spec: contracts + wiring + (for steps) prompt info.

    ``inputs_schema`` / ``output_schema`` are ``None`` when the
    corresponding class attribute (INPUTS / INSTRUCTIONS / MODEL /
    OUTPUT) has not been set on the node class — the spec describes
    reality including incomplete reality.

    ``issues`` carries node-level validation problems (missing
    INPUTS / INSTRUCTIONS / MODEL / OUTPUT, naming mismatches,
    prepare-signature issues, binding-kind mismatches). Per-wiring-
    field issues live further down on each ``SourceSpec``;
    prompt-class issues live on ``self.prompt.issues``. The
    frontend renders ``node.issues`` as the node-card error
    indicator.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["step", "extraction", "review"]
    name: str  # snake_case (step_name() / extraction class snake)
    cls: str  # fully-qualified class name
    inputs_schema: dict[str, Any] | None  # INPUTS.model_json_schema()
    output_schema: dict[str, Any] | None  # INSTRUCTIONS / MODEL / OUTPUT
    wiring: WiringSpec
    prompt: PromptSpec | None = None  # only for steps
    issues: list["ValidationIssue"] = Field(default_factory=list)


class EdgeSpec(BaseModel):
    """A directed graph edge from one node to the next (or to End).

    ``branch`` is the optional label identifying which decision-branch
    this edge belongs to. Today's union-return-driven topology
    populates ``None`` (no labelled branches). Future binding-driven
    branching (where the pipeline binding declares a ``next: dict[str,
    NodeCls]`` mapping) populates the branch label per edge. The
    field is forward-compatible: a node with two return-type targets
    today renders as two ``EdgeSpec`` records both with ``branch=None``,
    same shape the runtime work will reuse with labels.
    """

    model_config = ConfigDict(extra="forbid")

    from_node: str
    to_node: str  # node name or "End"
    branch: str | None = None


# ---------------------------------------------------------------------------
# Pipeline (top-level)
# ---------------------------------------------------------------------------


class PipelineSpec(BaseModel):
    """Complete typed introspection surface for a pipeline.

    Issues are localised to the spec component they describe:

    - **Pipeline-level** (cycles, naming, ``input_data_wrong_type``,
      ``invalid_binding_type``, ``duplicate_node_class``, graph /
      spec build failures): ``self.issues``.
    - **Node-level** (missing INPUTS / INSTRUCTIONS / MODEL /
      OUTPUT, naming mismatches, prepare-signature issues, binding-
      kind mismatches): ``self.nodes[i].issues``.
    - **Per-wiring-field** (``from_input_unknown_path``,
      ``from_output_not_upstream``, etc.):
      ``self.nodes[i].wiring.field_sources[name].issues``.
    - **Prompt-class** (``missing_field_description``,
      ``auto_vars_*``): ``self.nodes[i].prompt.issues``.

    :func:`derive_issues` is the canonical recursive flatten — use
    it when you need the full list (e.g. for
    :func:`is_runnable` or ``ValidationSummary.issue_count``).
    """

    model_config = ConfigDict(extra="forbid")

    name: str  # snake_case pipeline_name()
    cls: str  # fully-qualified class name
    input_data_schema: dict[str, Any] | None
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    start_node: str | None  # name of the start node; None when no valid bindings
    issues: list[ValidationIssue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _qualname(cls: type) -> str:
    """Return a fully-qualified class name (module + qualname)."""
    module = getattr(cls, "__module__", "?")
    qual = getattr(cls, "__qualname__", cls.__name__)
    return f"{module}.{qual}"


def _serialise_source(source: Any) -> SourceSpec:
    """Convert a ``wiring.Source`` to a ``SourceSpec``."""
    from llm_pipeline.wiring import Computed, FromInput, FromOutput, FromPipeline

    if isinstance(source, FromInput):
        return SourceSpec(kind="from_input", path=source.path)
    if isinstance(source, FromOutput):
        return SourceSpec(
            kind="from_output",
            step_cls=source.step_cls.__name__,
            index=source.index,
            field=source.field,
        )
    if isinstance(source, FromPipeline):
        return SourceSpec(kind="from_pipeline", attr=source.attr)
    if isinstance(source, Computed):
        return SourceSpec(
            kind="computed",
            fn=getattr(source.fn, "__qualname__", repr(source.fn)),
            sources=[_serialise_source(s) for s in source.sources],
        )
    raise TypeError(
        f"Cannot serialise unknown Source subclass {type(source).__name__!r}",
    )


def _build_wiring_spec(binding: Any) -> WiringSpec:
    """Convert a Step / Extraction / Review binding to a ``WiringSpec``."""
    spec = binding.inputs_spec
    return WiringSpec(
        inputs_cls=_qualname(spec.inputs_cls),
        field_sources={
            name: _serialise_source(src)
            for name, src in spec.field_sources.items()
        },
    )


def _build_tool_spec(tool_cls: type) -> ToolSpec:
    """Convert a ``PipelineTool`` subclass to a ``ToolSpec``."""
    from llm_pipeline.naming import to_snake_case

    return ToolSpec(
        name=to_snake_case(tool_cls.__name__),
        cls=_qualname(tool_cls),
        inputs_schema=tool_cls.Inputs.model_json_schema(),
        args_schema=tool_cls.Args.model_json_schema(),
    )


def _build_prompt_spec(step_cls: type) -> PromptSpec | None:
    """Build a ``PromptSpec`` for an ``LLMStepNode`` subclass.

    Returns ``None`` when prerequisites are missing — the spec stays
    coherent and ``derive_issues`` will surface the underlying
    capture (missing INSTRUCTIONS, prepare-signature mismatch, etc.).
    Only code-side fields are populated; Phoenix-aware fields stay
    ``None`` and get filled in by the discovery-time Phoenix
    validator.
    """
    prompt_cls = step_cls.prompt_variables_cls  # cached at __init_subclass__
    if prompt_cls is None or step_cls.INSTRUCTIONS is None:
        return None
    return PromptSpec(
        name=step_cls.step_name(),
        prompt_variables_cls=_qualname(prompt_cls),
        variable_definitions=prompt_cls.model_json_schema(),
        auto_vars=dict(getattr(prompt_cls, "auto_vars", {})),
        response_format=step_cls.INSTRUCTIONS.model_json_schema(),
        tools=[_build_tool_spec(t) for t in step_cls.DEFAULT_TOOLS],
    )


def _node_kind(binding: Any) -> Literal["step", "extraction", "review"]:
    from llm_pipeline.wiring import Extraction, Review, Step

    if isinstance(binding, Step):
        return "step"
    if isinstance(binding, Extraction):
        return "extraction"
    if isinstance(binding, Review):
        return "review"
    raise TypeError(f"Unknown node binding type: {type(binding).__name__}")


def _node_name(binding: Any) -> str:
    """Snake-case name for a node binding, used as the spec key.

    Steps use ``step_name()`` directly. Extractions and reviews don't
    have a method for it; we derive from the class name (stripping
    the matching suffix when present).
    """
    from llm_pipeline.naming import to_snake_case

    cls = binding.cls
    name = cls.__name__
    if name.endswith("Step"):
        suffix = "Step"
    elif name.endswith("Extraction"):
        suffix = "Extraction"
    elif name.endswith("Review"):
        suffix = "Review"
    else:
        suffix = ""
    return to_snake_case(name, strip_suffix=suffix or None)


def _build_output_schema(binding: Any) -> dict[str, Any] | None:
    """Per-kind output schema for a node binding.

    Returns ``None`` when the class hasn't declared its output type
    yet (INSTRUCTIONS / MODEL / OUTPUT unset). The spec describes
    reality; ``derive_issues`` reads the None and surfaces the
    missing-attribute issue.
    """
    from llm_pipeline.wiring import Extraction, Review, Step

    cls = binding.cls
    if isinstance(binding, Step):
        return (
            cls.INSTRUCTIONS.model_json_schema()
            if cls.INSTRUCTIONS is not None else None
        )
    if isinstance(binding, Extraction):
        return (
            cls.MODEL.model_json_schema()
            if cls.MODEL is not None else None
        )
    if isinstance(binding, Review):
        return (
            cls.OUTPUT.model_json_schema()
            if cls.OUTPUT is not None else None
        )
    raise TypeError(f"Unknown node binding type: {type(binding).__name__}")


def _build_node_spec(binding: Any) -> NodeSpec:
    """Compose a NodeSpec from a pipeline binding.

    Tolerates partial class state: ``INPUTS`` unset → inputs_schema
    stays None; ``INSTRUCTIONS``/``MODEL``/``OUTPUT`` unset → output
    schema stays None; missing prompt prerequisites for a step →
    prompt stays None. The spec describes reality;
    :func:`derive_issues` walks it and surfaces what's missing.
    """
    cls = binding.cls
    kind = _node_kind(binding)
    inputs_schema = (
        cls.INPUTS.model_json_schema() if cls.INPUTS is not None else None
    )
    return NodeSpec(
        kind=kind,
        name=_node_name(binding),
        cls=_qualname(cls),
        inputs_schema=inputs_schema,
        output_schema=_build_output_schema(binding),
        wiring=_build_wiring_spec(binding),
        prompt=_build_prompt_spec(cls) if kind == "step" else None,
    )


def _build_edges(pipeline_cls: type["Pipeline"]) -> list[EdgeSpec]:
    """Walk each node's ``run()`` return annotation to enumerate edges.

    Skips bindings whose ``cls`` isn't a real class — those entries
    surface as ``invalid_binding_type`` issues elsewhere.
    """
    from llm_pipeline.graph.validator import _next_node_classes
    from llm_pipeline.wiring import Extraction, Review, Step

    raw_nodes = [
        b.cls for b in pipeline_cls.nodes
        if isinstance(b, (Step, Extraction, Review))
        and isinstance(b.cls, type)
    ]
    name_by_cls = {c: c.__name__ for c in raw_nodes}
    # Reuse the validator's edge-resolution; it already handles
    # forward refs + Union returns + the End sentinel.
    edges: list[EdgeSpec] = []
    seen: set[tuple[str, str]] = set()
    for node_cls in raw_nodes:
        from_name = name_by_cls[node_cls]
        targets = _next_node_classes(node_cls, raw_nodes)
        if not targets:
            # No node target — the only legal terminator is End.
            edge = (from_name, "End")
            if edge not in seen:
                edges.append(EdgeSpec(from_node=from_name, to_node="End"))
                seen.add(edge)
            continue
        for target in targets:
            edge = (from_name, target.__name__)
            if edge not in seen:
                edges.append(
                    EdgeSpec(from_node=from_name, to_node=target.__name__),
                )
                seen.add(edge)
    return edges


def build_pipeline_spec(pipeline_cls: type["Pipeline"]) -> PipelineSpec:
    """Build the empty-issues skeleton ``PipelineSpec`` for ``pipeline_cls``.

    Called at ``Pipeline.__init_subclass__`` time. The returned spec
    has every ``issues`` list empty — the caller is expected to
    stamp captured errors onto the right components and then run
    the structural validator that populates per-component issues
    in place. The result is cached at ``cls._spec`` and surfaced
    via ``Pipeline.inspect()``.

    Tolerates partial state — only bindings whose ``cls`` is a real
    class contribute a ``NodeSpec``; invalid binding entries
    surface via captured pipeline-level issues stamped by the
    caller.

    **Never raises.** On internal failure (rare framework-edge
    cases like Pydantic schema generation crashing on an unusual
    user model), returns a minimal shell spec with empty
    ``nodes`` / ``edges`` and a ``spec_build_failed`` issue on
    ``spec.issues``. The invariant is "if the class loaded, a spec
    exists" — consumers can always trust ``Pipeline.inspect()`` /
    ``cls._spec`` to be a usable shape.
    """
    from llm_pipeline.wiring import Extraction, Review, Step

    try:
        input_schema = (
            pipeline_cls.INPUT_DATA.model_json_schema()
            if pipeline_cls.INPUT_DATA is not None else None
        )
        valid_bindings = [
            b for b in pipeline_cls.nodes
            if isinstance(b, (Step, Extraction, Review))
            and isinstance(b.cls, type)
        ]
        nodes = [_build_node_spec(b) for b in valid_bindings]
        edges = _build_edges(pipeline_cls)
        start_node_name = (
            pipeline_cls.start_node.__name__
            if isinstance(pipeline_cls.start_node, type) else None
        )
        return PipelineSpec(
            name=pipeline_cls.pipeline_name(),
            cls=_qualname(pipeline_cls),
            input_data_schema=input_schema,
            nodes=nodes,
            edges=edges,
            start_node=start_node_name,
        )
    except Exception as exc:
        # Framework-edge fallback: return a minimal shell spec so
        # downstream consumers (UI, API, sandbox) never have to
        # branch on "spec might be None".
        try:
            name = pipeline_cls.pipeline_name()
        except Exception:
            name = pipeline_cls.__name__
        return PipelineSpec(
            name=name,
            cls=_qualname(pipeline_cls),
            input_data_schema=None,
            nodes=[],
            edges=[],
            start_node=None,
            issues=[ValidationIssue(
                severity="error", code="spec_build_failed",
                message=(
                    f"Could not build PipelineSpec for "
                    f"{pipeline_cls.__name__}: {exc!s}"
                ),
                location=ValidationLocation(pipeline=pipeline_cls.__name__),
                suggestion=(
                    "Check the pipeline's INPUT_DATA / node INPUTS / "
                    "INSTRUCTIONS / OUTPUT / MODEL classes for "
                    "schema-generation issues (custom validators, "
                    "self-references, malformed annotations)."
                ),
            )],
        )


# ---------------------------------------------------------------------------
# Issue derivation (read-time; spec is the truth, issues are computed)
# ---------------------------------------------------------------------------


def _collect_source_issues(source: SourceSpec) -> list[ValidationIssue]:
    """Recursively gather issues from a SourceSpec and any inner sources."""
    issues = list(source.issues)
    for inner in source.sources or []:
        issues.extend(_collect_source_issues(inner))
    return issues


def derive_issues(spec: PipelineSpec) -> list[ValidationIssue]:
    """Walk a pipeline spec and return every localised issue, flattened.

    The spec stores issues at the level they describe:

    - ``spec.issues`` — pipeline-level (cycles, naming,
      ``invalid_binding_type``, build failures, etc.).
    - ``spec.nodes[i].issues`` — node-level (contract violations,
      naming, prepare-signature issues).
    - ``spec.nodes[i].wiring.field_sources[name].issues`` — per-
      input drift (FromInput unknown path, FromOutput not
      upstream, etc.). Inner ``Computed`` sources are walked
      recursively.
    - ``spec.nodes[i].prompt.issues`` — prompt-class-level
      (auto_vars, missing field descriptions).

    This function is the canonical flatten — use it for runnability
    gating (:func:`is_runnable`), counting
    (``ValidationSummary.issue_count``), or any consumer that wants
    "give me everything wrong with this pipeline."

    Order is stable: pipeline → per-node (in spec order) → per-node
    sub-components (wiring → prompt). Empty list means the pipeline
    is structurally clean.
    """
    issues = list(spec.issues)
    for node in spec.nodes:
        issues.extend(node.issues)
        for source in node.wiring.field_sources.values():
            issues.extend(_collect_source_issues(source))
        if node.prompt is not None:
            issues.extend(node.prompt.issues)
    return issues


def is_runnable(spec: PipelineSpec) -> bool:
    """Return True iff no error-severity issues exist on ``spec``.

    Warning-severity issues do NOT block runnability — they're
    surfaced in the UI as caution flags only.
    """
    return not any(
        issue.severity == "error" for issue in derive_issues(spec)
    )
