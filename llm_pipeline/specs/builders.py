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
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TOOL,
)
from llm_pipeline.specs.reviews import ReviewSpec
from llm_pipeline.specs.schemas import SchemaSpec
from llm_pipeline.specs.steps import StepSpec
from llm_pipeline.specs.tools import ToolSpec


__all__ = [
    "build_code_body",
    "build_constant_spec",
    "build_enum_spec",
    "build_extraction_spec",
    "build_review_spec",
    "build_schema_spec",
    "build_step_spec",
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
    )


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
    )


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
    )
