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

    Issues are NOT stored on the spec. They are derived by walking
    the spec's state via :func:`derive_issues`. Severity gates
    runnability: any ``error`` blocks the pipeline from running;
    ``warning`` is informational.

    The ``code`` is a stable machine-readable identifier (e.g.
    ``missing_inputs``, ``dangling_from_output``). Frontends can
    branch UX on it; humans read ``message`` and ``suggestion``.
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


# ---------------------------------------------------------------------------
# Node + Edge
# ---------------------------------------------------------------------------


class NodeSpec(BaseModel):
    """Per-node spec: contracts + wiring + (for steps) prompt info."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["step", "extraction", "review"]
    name: str  # snake_case (step_name() / extraction class snake)
    cls: str  # fully-qualified class name
    inputs_schema: dict[str, Any]  # INPUTS.model_json_schema()
    output_schema: dict[str, Any]  # INSTRUCTIONS / MODEL fields / OUTPUT
    wiring: WiringSpec
    prompt: PromptSpec | None = None  # only for steps


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
    """Complete typed introspection surface for a pipeline."""

    model_config = ConfigDict(extra="forbid")

    name: str  # snake_case pipeline_name()
    cls: str  # fully-qualified class name
    input_data_schema: dict[str, Any] | None
    nodes: list[NodeSpec]
    edges: list[EdgeSpec]
    start_node: str  # name of the start node


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


def _build_prompt_spec(step_cls: type) -> PromptSpec:
    """Build a ``PromptSpec`` for an ``LLMStepNode`` subclass.

    Only code-side fields are populated; Phoenix-aware fields stay
    ``None`` and get filled in by the discovery-time Phoenix
    validator.
    """
    prompt_cls = step_cls.prompt_variables_cls  # cached at __init_subclass__
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


def _build_output_schema(binding: Any) -> dict[str, Any]:
    """Per-kind output schema for a node binding."""
    from llm_pipeline.wiring import Extraction, Review, Step

    cls = binding.cls
    if isinstance(binding, Step):
        return cls.INSTRUCTIONS.model_json_schema()
    if isinstance(binding, Extraction):
        return cls.MODEL.model_json_schema()
    if isinstance(binding, Review):
        return cls.OUTPUT.model_json_schema()
    raise TypeError(f"Unknown node binding type: {type(binding).__name__}")


def _build_node_spec(binding: Any) -> NodeSpec:
    cls = binding.cls
    kind = _node_kind(binding)
    return NodeSpec(
        kind=kind,
        name=_node_name(binding),
        cls=_qualname(cls),
        inputs_schema=cls.INPUTS.model_json_schema(),
        output_schema=_build_output_schema(binding),
        wiring=_build_wiring_spec(binding),
        prompt=_build_prompt_spec(cls) if kind == "step" else None,
    )


def _build_edges(pipeline_cls: type["Pipeline"]) -> list[EdgeSpec]:
    """Walk each node's ``run()`` return annotation to enumerate edges."""
    from llm_pipeline.graph.validator import _next_node_classes

    raw_nodes = [b.cls for b in pipeline_cls.nodes]
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
    """Build the full ``PipelineSpec`` for ``pipeline_cls``.

    Called at ``Pipeline.__init_subclass__`` time after structural
    validation has succeeded. The returned spec is cached at
    ``cls._spec`` and surfaced via ``Pipeline.inspect()``.
    """
    input_schema = (
        pipeline_cls.INPUT_DATA.model_json_schema()
        if pipeline_cls.INPUT_DATA is not None else None
    )
    nodes = [_build_node_spec(b) for b in pipeline_cls.nodes]
    edges = _build_edges(pipeline_cls)
    return PipelineSpec(
        name=pipeline_cls.pipeline_name(),
        cls=_qualname(pipeline_cls),
        input_data_schema=input_schema,
        nodes=nodes,
        edges=edges,
        start_node=pipeline_cls.start_node.__name__,
    )


# ---------------------------------------------------------------------------
# Issue derivation (read-time; spec is the truth, issues are computed)
# ---------------------------------------------------------------------------


def derive_issues(spec: PipelineSpec) -> list[ValidationIssue]:
    """Walk a pipeline spec and report everything wrong with it.

    The spec describes reality (including incomplete reality —
    ``inputs_schema=None`` means the node didn't declare INPUTS, etc.).
    This function is one possible reading of that reality: it returns
    a flat list of human-readable issues, ordered by location. Empty
    list means the pipeline is structurally clean.

    Composes from three sources:

    - **Captured ``__init_subclass__`` errors** — recorded on each
      class as ``_init_subclass_errors`` when the framework's
      contract validators fired against partial state.
    - **Coherence checks** — wiring ``field_sources`` reference real
      upstream nodes; required schemas present per node kind; etc.
    - **Pipeline-level validators** — cycle detection, start-node
      sanity, naming conventions.

    Stub: returns empty for now. Implementation lands in step 6 of
    the plan, after the framework's ``__init_subclass__`` validators
    have been refactored to capture rather than raise (steps 3-5).
    Callers can already wire this into ``PipelineEntry`` and the API
    surface — they'll see no issues yet because the captures don't
    exist yet, which matches today's "raises during discovery"
    behaviour from the consumer's point of view.
    """
    return []


def is_runnable(spec: PipelineSpec) -> bool:
    """Return True iff no error-severity issues exist on ``spec``.

    Warning-severity issues do NOT block runnability — they're
    surfaced in the UI as caution flags only.
    """
    return not any(
        issue.severity == "error" for issue in derive_issues(spec)
    )
