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

import inspect
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar

from llm_pipeline.cst_analysis import (
    AnalysisError,
    ResolverHook,
    analyze_class_fields,
    analyze_code_body,
)
from llm_pipeline.specs.base import ArtifactRef, SymbolRef
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
    # Standalone builders (constants, enums, pipelines)
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
    # Class-based builders (the ABC + per-kind subclasses)
    "ExtractionBuilder",
    "ReviewBuilder",
    "SchemaBuilder",
    "SpecBuilder",
    "StepBuilder",
    "TableBuilder",
    "ToolBuilder",
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _qualified(cls: type) -> str:
    """Return ``cls``'s fully-qualified ``module.qualname``."""
    return f"{cls.__module__}.{cls.__qualname__}"


def _docstring(cls: type | None) -> str:
    """Return ``cls``'s cleaned docstring, or empty string.

    Uses :func:`inspect.getdoc` (handles indent stripping and walks
    base classes appropriately for inherited docstrings). Empty
    string when ``cls`` is None or has no docstring.
    """
    if cls is None:
        return ""
    return inspect.getdoc(cls) or ""


def _class_to_artifact_ref(
    cls: type | None,
    resolver: ResolverHook,
) -> ArtifactRef | None:
    """Build an :class:`ArtifactRef` from a Python class.

    Used wherever a per-kind spec carries a reference to another
    registered artifact via a class attribute (``ExtractionNode.MODEL``,
    ``LLMStepNode.DEFAULT_TOOLS`` entries, ``Pipeline.start_node``,
    etc.). The :attr:`ArtifactRef.name` is the source-side Python
    identifier (``cls.__name__``); the :attr:`ArtifactRef.ref` is
    populated when the resolver maps ``(cls.__module__,
    cls.__name__)`` to a registered ``(kind, registry_key)``.

    Returns ``None`` when ``cls`` is None.
    """
    if cls is None:
        return None
    module_path = getattr(cls, "__module__", "") or ""
    symbol = cls.__name__
    resolved = resolver(module_path, symbol) if module_path else None
    ref = (
        SymbolRef(symbol=symbol, kind=resolved[0], name=resolved[1])
        if resolved is not None else None
    )
    return ArtifactRef(name=symbol, ref=ref)


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
    return JsonSchemaWithRefs(
        json_schema=schema,
        refs=refs,
        description=_docstring(cls),
    )


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
        description=_docstring(enum_cls),
        value_type=value_type,
        members=members,
    ).attach_class_captures(enum_cls)


# ---------------------------------------------------------------------------
# SpecBuilder base class — for the class-based artifact kinds
# ---------------------------------------------------------------------------


class SpecBuilder(ABC):
    """Per-kind builder base for class-based artifacts.

    Encapsulates construction shared by every class-based kind
    (schemas, tables, tools, steps, extractions, reviews):

    1. Build kind-specific spec fields via :meth:`kind_fields`
       (subclass hook).
    2. Wrap in the per-kind :class:`ArtifactSpec` subclass with
       identity (``kind`` / ``name`` / ``cls`` qualname /
       ``source_path``) and ``description`` extracted from the
       class's ``__doc__``.
    3. Chain :meth:`ArtifactSpec.attach_class_captures` to route
       any ``cls._init_subclass_errors`` onto the right
       :class:`ArtifactField` sub-component.

    Subclasses pin :attr:`KIND` and :attr:`SPEC_CLS`, and override
    :meth:`kind_fields`. Convenience helpers :meth:`json_schema`
    and :meth:`code_body` pre-fill ``source_text`` + ``resolver``
    so the threaded-through-everything pattern shrinks to one-arg
    calls per field.

    Constants, enums, and pipelines have different signatures
    (no ``cls`` to introspect, or special read-from-``cls._spec``
    flow) and stay as standalone ``build_*`` functions.
    """

    KIND: ClassVar[str]
    SPEC_CLS: ClassVar[type]

    def __init__(
        self,
        *,
        name: str,
        cls: type,
        source_path: str,
        source_text: str,
        resolver: ResolverHook,
    ) -> None:
        self.name = name
        self.cls = cls
        self.source_path = source_path
        self.source_text = source_text
        self.resolver = resolver

    def json_schema(self, cls: type | None) -> JsonSchemaWithRefs | None:
        """Convenience wrapper: pre-fills ``source_text`` + ``resolver``."""
        return json_schema_with_refs(
            cls=cls,
            source_text=self.source_text,
            resolver=self.resolver,
        )

    def code_body(self, method_name: str) -> CodeBodySpec | None:
        """Convenience wrapper: builds the function qualname from
        ``self.cls`` + ``method_name`` and pre-fills source/resolver."""
        return build_code_body(
            function_qualname=f"{self.cls.__qualname__}.{method_name}",
            source_text=self.source_text,
            resolver=self.resolver,
        )

    @abstractmethod
    def kind_fields(self) -> dict[str, Any]:
        """Return per-kind keyword arguments for the spec constructor."""

    def build(self):
        return self.SPEC_CLS(
            kind=self.KIND,
            name=self.name,
            cls=_qualified(self.cls),
            source_path=self.source_path,
            description=_docstring(self.cls),
            **self.kind_fields(),
        ).attach_class_captures(self.cls)


# ---------------------------------------------------------------------------
# Level 3: schemas, tables, tools (cst_analysis-aware)
# ---------------------------------------------------------------------------


class SchemaBuilder(SpecBuilder):
    """Build a :class:`SchemaSpec` from a Pydantic ``BaseModel`` subclass."""

    KIND = KIND_SCHEMA
    SPEC_CLS = SchemaSpec

    def kind_fields(self) -> dict[str, Any]:
        # Schema generation never produces None for a valid BaseModel
        # subclass; if it does, hand back an empty placeholder so
        # consumers don't have to branch on None at every site.
        definition = self.json_schema(self.cls) or JsonSchemaWithRefs(
            json_schema={},
        )
        return {"definition": definition}


def build_schema_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> SchemaSpec:
    return SchemaBuilder(
        name=name, cls=cls, source_path=source_path,
        source_text=source_text, resolver=resolver,
    ).build()


class TableBuilder(SpecBuilder):
    """Build a :class:`TableSpec` from a SQLModel-with-``table=True`` class.

    Caller is expected to have already classified ``cls`` as a
    table (via the discovery walker's ``__table__``-presence
    check). Reads ``__tablename__`` and ``__table__.indexes``
    from the class — no DB engine required.
    """

    KIND = KIND_TABLE
    SPEC_CLS = TableSpec

    def kind_fields(self) -> dict[str, Any]:
        definition = self.json_schema(self.cls) or JsonSchemaWithRefs(
            json_schema={},
        )

        table_name = getattr(self.cls, "__tablename__", "") or ""

        indices: list[IndexSpec] = []
        table = getattr(self.cls, "__table__", None)
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

        return {
            "definition": definition,
            "table_name": table_name,
            "indices": indices,
        }


def build_table_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> TableSpec:
    return TableBuilder(
        name=name, cls=cls, source_path=source_path,
        source_text=source_text, resolver=resolver,
    ).build()


class ToolBuilder(SpecBuilder):
    """Build a :class:`ToolSpec` for an agent tool.

    Phase C.1 skeleton — the call signature here is provisional,
    matching the spec subclass shape. Phase C.2's tool walker
    decides which classes count as Inputs/Args and which qualname
    addresses the tool's callable body.
    """

    KIND = KIND_TOOL
    SPEC_CLS = ToolSpec

    def __init__(
        self,
        *,
        inputs_cls: type | None = None,
        args_cls: type | None = None,
        body_qualname: str | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.inputs_cls = inputs_cls
        self.args_cls = args_cls
        self.body_qualname = body_qualname

    def kind_fields(self) -> dict[str, Any]:
        return {
            "inputs": self.json_schema(self.inputs_cls),
            "args": self.json_schema(self.args_cls),
            "body": (
                build_code_body(
                    function_qualname=self.body_qualname,
                    source_text=self.source_text,
                    resolver=self.resolver,
                )
                if self.body_qualname else None
            ),
        }


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
    return ToolBuilder(
        name=name, cls=cls, source_path=source_path,
        source_text=source_text, resolver=resolver,
        inputs_cls=inputs_cls, args_cls=args_cls,
        body_qualname=body_qualname,
    ).build()


# ---------------------------------------------------------------------------
# Level 4: nodes (steps, extractions, reviews)
# ---------------------------------------------------------------------------


class StepBuilder(SpecBuilder):
    """Build a :class:`StepSpec` from an ``LLMStepNode`` subclass.

    The ``prompt`` argument is provided by the walker — it
    constructs :class:`PromptData` from the paired YAML +
    ``_variables/`` PromptVariables class outside this builder.
    Builders stay pure (no YAML reading, no Phoenix calls).
    """

    KIND = KIND_STEP
    SPEC_CLS = StepSpec

    def __init__(
        self,
        *,
        prompt: PromptData | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.prompt = prompt

    def kind_fields(self) -> dict[str, Any]:
        cls = self.cls
        inputs_cls = getattr(cls, "INPUTS", None)
        instructions_cls = getattr(cls, "INSTRUCTIONS", None)
        default_tools = getattr(cls, "DEFAULT_TOOLS", None) or []

        # One ArtifactRef per DEFAULT_TOOLS entry. Source-side name
        # is the tool's Python class name; ``ref`` is populated when
        # the resolver maps that to a registered tool.
        tools = [
            ref for ref in (
                _class_to_artifact_ref(tool, self.resolver)
                for tool in default_tools
            ) if ref is not None
        ]

        return {
            "inputs": self.json_schema(inputs_cls),
            "instructions": self.json_schema(instructions_cls),
            "prepare": self.code_body("prepare"),
            "run": self.code_body("run"),
            "prompt": self.prompt,
            "tools": tools,
        }


def build_step_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
    prompt: PromptData | None = None,
) -> StepSpec:
    return StepBuilder(
        name=name, cls=cls, source_path=source_path,
        source_text=source_text, resolver=resolver,
        prompt=prompt,
    ).build()


class ExtractionBuilder(SpecBuilder):
    """Build an :class:`ExtractionSpec` from an ``ExtractionNode`` subclass."""

    KIND = KIND_EXTRACTION
    SPEC_CLS = ExtractionSpec

    def kind_fields(self) -> dict[str, Any]:
        cls = self.cls
        inputs_cls = getattr(cls, "INPUTS", None)
        model_cls = getattr(cls, "MODEL", None)

        return {
            "inputs": self.json_schema(inputs_cls),
            "table": _class_to_artifact_ref(model_cls, self.resolver),
            "extract": self.code_body("extract"),
            "run": self.code_body("run"),
        }


def build_extraction_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> ExtractionSpec:
    return ExtractionBuilder(
        name=name, cls=cls, source_path=source_path,
        source_text=source_text, resolver=resolver,
    ).build()


class ReviewBuilder(SpecBuilder):
    """Build a :class:`ReviewSpec` from a ``ReviewNode`` subclass."""

    KIND = KIND_REVIEW
    SPEC_CLS = ReviewSpec

    def kind_fields(self) -> dict[str, Any]:
        cls = self.cls
        inputs_cls = getattr(cls, "INPUTS", None)
        output_cls = getattr(cls, "OUTPUT", None)
        webhook_url = getattr(cls, "webhook_url", None)
        if not isinstance(webhook_url, str):
            webhook_url = None

        return {
            "inputs": self.json_schema(inputs_cls),
            "output": self.json_schema(output_cls),
            "webhook_url": webhook_url,
            "run": self.code_body("run"),
        }


def build_review_spec(
    *,
    name: str,
    cls: type,
    source_path: str,
    source_text: str,
    resolver: ResolverHook,
) -> ReviewSpec:
    return ReviewBuilder(
        name=name, cls=cls, source_path=source_path,
        source_text=source_text, resolver=resolver,
    ).build()


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
            description=_docstring(cls),
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

    # ``cls.start_node`` is the Python class (e.g. ``ClassifyStep``);
    # ``_class_to_artifact_ref`` produces an ArtifactRef whose
    # ``name`` is the source-side class name and ``ref`` is the
    # resolved (kind, registry-key) pair when the resolver matches.
    # Returns ``None`` when ``cls.start_node`` is unset.
    start_node_ref = _class_to_artifact_ref(
        getattr(cls, "start_node", None), resolver,
    )

    return PipelineSpec(
        kind=KIND_PIPELINE,
        name=name,
        cls=_qualified(cls),
        source_path=source_path,
        description=_docstring(cls),
        input_data=input_data,
        nodes=node_bindings,
        edges=list(legacy.edges),
        start_node=start_node_ref,
        issues=list(legacy.issues),
    )
