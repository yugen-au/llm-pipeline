"""Per-kind spec builders.

Each builder takes a loaded class/value plus its source-file
context and returns a populated per-kind :class:`ArtifactSpec`.
Builders are pure functions — they introspect the runtime
class/value and call into :mod:`llm_pipeline.cst_analysis` for
source-side metadata; they don't touch disk.

Phase C.1 ships the builders. Phase C.2 wires them into
per-folder discovery walkers; that walker layer reads files via
``codegen.read_module`` (or the equivalent) and feeds the
``source_text`` + a registry-aware ``resolver`` into these
builders.

Builders never raise — partial state surfaces via the spec's
``issues`` field on the relevant component (per the localised-
issues design from the plan). Schema-generation failures, missing
class state, and analyser parse errors are all captured.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from llm_pipeline.cst_analysis import (
    AnalysisError,
    ResolverHook,
    analyze_class_fields,
    analyze_code_body,
)
from llm_pipeline.specs.blocks import (
    CodeBodySpec,
    JsonSchemaWithRefs,
    PromptData,
)
from llm_pipeline.specs.constants import ConstantSpec
from llm_pipeline.specs.enums import EnumMemberSpec, EnumSpec
from llm_pipeline.specs.extractions import ExtractionSpec
from llm_pipeline.specs.kinds import (
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_EXTRACTION,
    KIND_PIPELINE,
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TABLE,
    KIND_TOOL,
)
from llm_pipeline.specs.pipelines import NodeBindingSpec, PipelineSpec
from llm_pipeline.specs.reviews import ReviewSpec
from llm_pipeline.specs.schemas import SchemaSpec
from llm_pipeline.specs.steps import StepSpec
from llm_pipeline.specs.tables import IndexSpec, TableSpec
from llm_pipeline.specs.tools import ToolSpec


__all__ = [
    "build_code_body",
    "build_constant_spec",
    "build_enum_spec",
    "build_extraction_spec",
    "build_pipeline_spec",
    "build_review_spec",
    "build_schema_spec",
    "build_step_spec",
    "build_table_spec",
    "build_tool_spec",
    "json_schema_with_refs",
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _qualified(cls: type) -> str:
    """Return ``cls``'s fully-qualified ``module.qualname``."""
    return f"{cls.__module__}.{cls.__qualname__}"


def _safe_model_json_schema(cls: type) -> dict[str, Any] | None:
    """Call ``cls.model_json_schema()``; return ``None`` on any failure.

    Pydantic schema generation can blow up on unusual user models
    (custom validators, self-references, etc.). Builders treat
    those as "no schema available" and let the spec-level issue
    surfacing convey the partial state.
    """
    try:
        return cls.model_json_schema()  # type: ignore[no-any-return,attr-defined]
    except Exception:  # noqa: BLE001 — uniform fallback
        return None


def json_schema_with_refs(
    *,
    cls: type | None,
    source_text: str,
    resolver: ResolverHook,
) -> JsonSchemaWithRefs | None:
    """Build a :class:`JsonSchemaWithRefs` for a Pydantic-shaped class.

    Returns ``None`` when ``cls`` is None or its schema can't be
    generated. Source-side ref analysis is best-effort: a parse
    failure or "class not found in source" yields an empty refs
    dict, not an error — the schema half stays valid.
    """
    if cls is None:
        return None
    schema = _safe_model_json_schema(cls)
    if schema is None:
        return None
    refs: dict[str, list] = {}
    try:
        refs = analyze_class_fields(
            source=source_text,
            class_qualname=cls.__qualname__,
            resolver=resolver,
        )
    except AnalysisError:
        refs = {}
    return JsonSchemaWithRefs(json_schema=schema, refs=refs)


def build_code_body(
    *,
    function_qualname: str,
    source_text: str,
    resolver: ResolverHook,
) -> CodeBodySpec | None:
    """Analyse a function body and return a populated :class:`CodeBodySpec`.

    Returns ``None`` if the function isn't found in ``source_text``
    (caller should treat this as "no body to render" rather than
    an error — the missing function is surfaced by the per-kind
    capture model elsewhere).
    """
    try:
        return analyze_code_body(
            source=source_text,
            function_qualname=function_qualname,
            resolver=resolver,
        )
    except AnalysisError:
        return None


# ---------------------------------------------------------------------------
# Level 1-2: constants + enums (no cst_analysis needed)
# ---------------------------------------------------------------------------


def build_constant_spec(
    *,
    name: str,
    value: Any,
    cls_path: str,
    source_path: str,
) -> ConstantSpec:
    """Build a :class:`ConstantSpec` from a module-level value.

    ``cls_path`` is the dotted Python identifier
    (``"llm_pipelines.constants.retries.MAX_RETRIES"``) — what
    the resolver hook receives when another artifact imports it.
    """
    return ConstantSpec(
        kind=KIND_CONSTANT,
        name=name,
        cls=cls_path,
        source_path=source_path,
        value_type=type(value).__name__,
        value=value,
    )


def build_enum_spec(
    *,
    name: str,
    enum_cls: type[Enum],
    source_path: str,
) -> EnumSpec:
    """Build an :class:`EnumSpec` from an Enum subclass."""
    members = [
        EnumMemberSpec(name=member.name, value=member.value)
        for member in enum_cls
    ]
    # Most enums are homogeneous; pick the first member's value
    # type as the representative. Empty enums (rare) default to
    # ``"str"`` so the field always has a concrete value.
    if members:
        first_value = next(iter(enum_cls)).value
        value_type = type(first_value).__name__
    else:
        value_type = "str"
    return EnumSpec(
        kind=KIND_ENUM,
        name=name,
        cls=_qualified(enum_cls),
        source_path=source_path,
        value_type=value_type,
        members=members,
    )


# ---------------------------------------------------------------------------
# Level 3: schemas, tools (cst_analysis-aware)
# ---------------------------------------------------------------------------


def build_schema_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> SchemaSpec:
    """Build a :class:`SchemaSpec` from a Pydantic ``BaseModel`` subclass."""
    definition = json_schema_with_refs(
        cls=cls,
        source_text=source_text,
        resolver=resolver,
    )
    # Schema generation never produces None for a valid BaseModel
    # subclass; if it does, hand back an empty placeholder so
    # consumers don't have to branch on None at every site.
    if definition is None:
        definition = JsonSchemaWithRefs(json_schema={})
    return SchemaSpec(
        kind=KIND_SCHEMA,
        name=name,
        cls=_qualified(cls),
        source_path=source_path,
        definition=definition,
    )


def build_table_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> TableSpec:
    """Build a :class:`TableSpec` from a SQLModel-with-table=True class.

    Caller is expected to have already classified ``cls`` as a
    table (via the discovery walker's ``__table__``-presence
    check). Reads ``__tablename__`` and ``__table__.indexes``
    from the class — no DB engine required.

    The JSON-schema-side analysis is shared with
    :func:`build_schema_spec` (both go through
    :func:`json_schema_with_refs`); only the table-specific
    metadata is pulled separately here.
    """
    definition = json_schema_with_refs(
        cls=cls,
        source_text=source_text,
        resolver=resolver,
    )
    if definition is None:
        definition = JsonSchemaWithRefs(json_schema={})

    table_name = getattr(cls, "__tablename__", "") or ""

    indices: list[IndexSpec] = []
    table = getattr(cls, "__table__", None)
    if table is not None:
        for idx in getattr(table, "indexes", []) or []:
            try:
                columns = [c.name for c in idx.columns]
            except Exception:  # noqa: BLE001 — defensive against odd backends
                columns = []
            indices.append(IndexSpec(
                name=getattr(idx, "name", "") or "",
                columns=columns,
                unique=bool(getattr(idx, "unique", False)),
            ))

    return TableSpec(
        kind=KIND_TABLE,
        name=name,
        cls=_qualified(cls),
        source_path=source_path,
        definition=definition,
        table_name=table_name,
        indices=indices,
    )


def build_tool_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
    inputs_cls: type | None = None,
    args_cls: type | None = None,
    body_qualname: str | None = None,
) -> ToolSpec:
    """Build a :class:`ToolSpec` for an agent tool.

    Phase C.1 skeleton — the call signature here is provisional,
    matching the spec subclass shape. Phase C.2's tool walker
    decides which classes count as Inputs/Args and which qualname
    addresses the tool's callable body. For now ``inputs_cls`` /
    ``args_cls`` / ``body_qualname`` are passed in by the walker
    or the test.
    """
    return ToolSpec(
        kind=KIND_TOOL,
        name=name,
        cls=_qualified(cls),
        source_path=source_path,
        inputs=json_schema_with_refs(
            cls=inputs_cls, source_text=source_text, resolver=resolver,
        ),
        args=json_schema_with_refs(
            cls=args_cls, source_text=source_text, resolver=resolver,
        ),
        body=(
            build_code_body(
                function_qualname=body_qualname,
                source_text=source_text,
                resolver=resolver,
            )
            if body_qualname
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Level 4: nodes (steps, extractions, reviews)
# ---------------------------------------------------------------------------


def build_step_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
    prompt: PromptData | None = None,
) -> StepSpec:
    """Build a :class:`StepSpec` from an ``LLMStepNode`` subclass.

    The ``prompt`` argument is provided by the walker — it
    constructs ``PromptData`` from the paired YAML + ``_variables/``
    PromptVariables class outside this builder. Builders stay
    pure (no YAML reading, no Phoenix calls).
    """
    inputs_cls = getattr(cls, "INPUTS", None)
    instructions_cls = getattr(cls, "INSTRUCTIONS", None)
    default_tools = getattr(cls, "DEFAULT_TOOLS", None) or []

    tool_names: list[str] = []
    for tool in default_tools:
        # Each tool is expected to be a class with a registry-key
        # property/attribute. Fall back to its qualname if no
        # ``name``/``step_name`` is set.
        tool_name = (
            getattr(tool, "name", None)
            or getattr(tool, "tool_name", None)
            or getattr(tool, "__name__", None)
        )
        if isinstance(tool_name, str) and tool_name:
            tool_names.append(tool_name)

    # ``attach_class_captures`` routes ``cls._init_subclass_errors``
    # onto the matching ArtifactField sub-component (``inputs.issues``
    # / ``instructions.issues`` / ``prepare.issues`` / ``run.issues``)
    # by ``location.field`` (set to ``StepFields.X`` constants at
    # the capture site); anything that doesn't match a routable
    # ArtifactField falls back to the top-level ``StepSpec.issues``.
    return StepSpec(
        kind=KIND_STEP,
        name=name,
        cls=_qualified(cls),
        source_path=source_path,
        inputs=json_schema_with_refs(
            cls=inputs_cls, source_text=source_text, resolver=resolver,
        ),
        instructions=json_schema_with_refs(
            cls=instructions_cls, source_text=source_text, resolver=resolver,
        ),
        prepare=build_code_body(
            function_qualname=f"{cls.__qualname__}.prepare",
            source_text=source_text,
            resolver=resolver,
        ),
        run=build_code_body(
            function_qualname=f"{cls.__qualname__}.run",
            source_text=source_text,
            resolver=resolver,
        ),
        prompt=prompt,
        tool_names=tool_names,
    ).attach_class_captures(cls)


def build_extraction_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> ExtractionSpec:
    """Build an :class:`ExtractionSpec` from an ``ExtractionNode`` subclass."""
    inputs_cls = getattr(cls, "INPUTS", None)
    model_cls = getattr(cls, "MODEL", None)

    # MODEL class -> registry-key (snake_case derived from class
    # name). The actual SchemaSpec lookup happens at consumer
    # side via the universal resolver.
    table_name = None
    if model_cls is not None:
        from llm_pipeline.naming import to_snake_case

        table_name = to_snake_case(model_cls.__name__)

    # See ``build_step_spec`` for the routing rationale.
    # ``ExtractionFields.TABLE_NAME`` captures land on top-level
    # ``ExtractionSpec.issues`` because the spec's ``table_name``
    # is a primitive ``str | None`` (not an ArtifactField).
    return ExtractionSpec(
        kind=KIND_EXTRACTION,
        name=name,
        cls=_qualified(cls),
        source_path=source_path,
        inputs=json_schema_with_refs(
            cls=inputs_cls, source_text=source_text, resolver=resolver,
        ),
        table_name=table_name,
        extract=build_code_body(
            function_qualname=f"{cls.__qualname__}.extract",
            source_text=source_text,
            resolver=resolver,
        ),
        run=build_code_body(
            function_qualname=f"{cls.__qualname__}.run",
            source_text=source_text,
            resolver=resolver,
        ),
    ).attach_class_captures(cls)


def build_review_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> ReviewSpec:
    """Build a :class:`ReviewSpec` from a ``ReviewNode`` subclass."""
    inputs_cls = getattr(cls, "INPUTS", None)
    output_cls = getattr(cls, "OUTPUT", None)
    webhook_url = getattr(cls, "webhook_url", None)
    if not isinstance(webhook_url, str):
        webhook_url = None

    # See ``build_step_spec`` for the routing rationale.
    return ReviewSpec(
        kind=KIND_REVIEW,
        name=name,
        cls=_qualified(cls),
        source_path=source_path,
        inputs=json_schema_with_refs(
            cls=inputs_cls, source_text=source_text, resolver=resolver,
        ),
        output=json_schema_with_refs(
            cls=output_cls, source_text=source_text, resolver=resolver,
        ),
        webhook_url=webhook_url,
        run=build_code_body(
            function_qualname=f"{cls.__qualname__}.run",
            source_text=source_text,
            resolver=resolver,
        ),
    ).attach_class_captures(cls)


# ---------------------------------------------------------------------------
# Level 5: pipelines
# ---------------------------------------------------------------------------


def build_pipeline_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> PipelineSpec:
    """Build a :class:`PipelineSpec` for a ``Pipeline`` subclass.

    The legacy :class:`llm_pipeline.graph.spec.PipelineSpec` is
    already built and validated at ``Pipeline.__init_subclass__``
    time (cached on ``cls._spec``). This builder TRANSLATES that
    legacy spec into the new per-artifact shape:

    - Pipeline-level issues (cycles, naming, ``input_data_wrong_type``,
      ``invalid_binding_type``, ``duplicate_node_class``, etc.) are
      copied from ``cls._spec.issues`` to the new spec's
      ``self.issues``. The legacy validator already placed them
      correctly; we just preserve placement.
    - Per-binding rows: one :class:`NodeBindingSpec` per deduped
      binding, carrying ``binding_kind`` (wrapper type),
      ``node_name`` (snake_case registry key), the wiring (reused
      :class:`WiringSpec` from the legacy spec — already validator-
      populated with per-source issues), and per-binding-wrapper
      issues from ``binding._init_post_errors``.
    - Class-contract issues (missing INPUTS, prepare-signature
      mismatches, etc.) are NOT copied here — they live canonically
      on the standalone per-kind spec
      (``registries[KIND_STEP][node_name]`` etc.). The frontend
      follows the ``node_name`` ref to find them.

    ``input_data`` is built fresh via :func:`json_schema_with_refs`
    over ``cls.INPUT_DATA``, so its refs reflect cross-artifact
    references in the pipeline file. The legacy spec only carried
    the schema; this version captures refs too.

    Tolerates partial state: if ``cls._spec`` is missing (rare —
    ``Pipeline.__init_subclass__`` always builds it, even on
    framework-edge failures it returns a shell), returns a minimal
    :class:`PipelineSpec` so consumers don't have to branch on None.
    """
    from llm_pipeline.wiring import Extraction, Review, Step

    legacy = getattr(cls, "_spec", None)
    if legacy is None:
        return PipelineSpec(
            kind=KIND_PIPELINE,
            name=name,
            cls=_qualified(cls),
            source_path=source_path,
        )

    # Per-binding rows. ``cls._wiring`` is the deduped binding map
    # in the same order as ``legacy.nodes`` (both built from the
    # filtered+deduped binding list at __init_subclass__ time).
    deduped_bindings = list(getattr(cls, "_wiring", {}).values())

    node_bindings: list[NodeBindingSpec] = []
    for binding, legacy_node in zip(deduped_bindings, legacy.nodes):
        if isinstance(binding, Step):
            binding_kind = "step"
        elif isinstance(binding, Extraction):
            binding_kind = "extraction"
        elif isinstance(binding, Review):
            binding_kind = "review"
        else:
            # Pipeline.__init_subclass__ filters non-Step/Extraction/Review
            # bindings out before building _wiring; this shouldn't
            # happen but stay defensive.
            continue
        node_bindings.append(NodeBindingSpec(
            binding_kind=binding_kind,
            node_name=legacy_node.name,
            wiring=legacy_node.wiring,
            issues=list(getattr(binding, "_init_post_errors", [])),
        ))

    input_data_cls = getattr(cls, "INPUT_DATA", None)
    input_data = json_schema_with_refs(
        cls=input_data_cls, source_text=source_text, resolver=resolver,
    )

    return PipelineSpec(
        kind=KIND_PIPELINE,
        name=name,
        cls=_qualified(cls),
        source_path=source_path,
        input_data=input_data,
        nodes=node_bindings,
        edges=list(legacy.edges),
        start_node=legacy.start_node,
        issues=list(legacy.issues),
    )
