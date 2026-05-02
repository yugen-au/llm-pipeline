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
    # Helpers (used by walkers and a few specialised callers)
    "build_code_body",
    "json_schema_with_refs",
    # Per-kind builders — every kind goes through SpecBuilder.
    "ConstantBuilder",
    "EnumBuilder",
    "ExtractionBuilder",
    "PipelineBuilder",
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
# SpecBuilder base class — universal entrypoint for every kind
# ---------------------------------------------------------------------------


class SpecBuilder(ABC):
    """Per-kind builder base — universal entrypoint for every kind.

    Every kind goes through a :class:`SpecBuilder` subclass; the walker
    layer treats them uniformly via :meth:`build`. Every kind is
    class-based — schemas, tables, tools, steps, extractions, reviews,
    enums, pipelines all carry their declaring Python class. Constants
    (declared as :class:`llm_pipeline.constants.Constant` subclasses
    with a ``value`` ClassVar) sit on the same dispatch footing.

    The base ``build()`` does the same three things for everyone:

    1. Build kind-specific spec fields via :meth:`kind_fields`
       (subclass hook).
    2. Wrap in the per-kind :class:`ArtifactSpec` subclass with
       identity (``kind`` / ``name`` / ``cls`` qualname /
       ``source_path``) and ``description``.
    3. Chain :meth:`ArtifactSpec.attach_class_captures` to route
       any ``cls._init_subclass_errors`` onto the right
       :class:`ArtifactField` sub-component.

    Subclasses pin :attr:`KIND` and :attr:`SPEC_CLS` and override
    :meth:`kind_fields`. Convenience helpers :meth:`json_schema` and
    :meth:`code_body` pre-fill ``source_text`` + ``resolver`` so
    subclasses can shrink threaded-through-everything calls to a
    single argument.
    """

    KIND: ClassVar[str]
    SPEC_CLS: ClassVar[type]

    def __init__(
        self,
        *,
        name: str,
        cls: type,
        source_path: str,
        source_text: str = "",
        resolver: ResolverHook | None = None,
    ) -> None:
        self.name = name
        self.cls = cls
        self.source_path = source_path
        self.source_text = source_text
        # Default resolver is a null lookup — kinds that don't consult
        # cst_analysis (constants, enums) leave it alone.
        self.resolver: ResolverHook = resolver or (lambda _m, _s: None)

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
# Level 1: constants
# ---------------------------------------------------------------------------


class ConstantBuilder(SpecBuilder):
    """Build a :class:`ConstantSpec` from a :class:`llm_pipeline.constants.Constant` subclass.

    Each constant is declared as a ``Constant`` subclass with a
    ``value`` :data:`typing.ClassVar`. The class-based form puts
    constants on the same dispatch footing as every other kind —
    ``cls`` is the subclass, the dotted ``cls`` path falls out of
    ``module.qualname`` automatically, and
    :meth:`Constant.__init_subclass__` validates the value's runtime
    type at declaration time.
    """

    KIND = KIND_CONSTANT
    SPEC_CLS = ConstantSpec

    def kind_fields(self) -> dict[str, Any]:
        # ``cls`` is the Constant subclass; its ``value`` ClassVar is
        # the runtime value. ``__init_subclass__`` already validated
        # the type — read it directly.
        value = self.cls.value  # type: ignore[union-attr]  — cls non-None for constants
        return {
            "value_type": type(value).__name__,
            "value": value,
        }


# ---------------------------------------------------------------------------
# Level 2: enums (class-based — Enum subclasses fit the standard signature)
# ---------------------------------------------------------------------------


class EnumBuilder(SpecBuilder):
    """Build an :class:`EnumSpec` from an ``Enum`` subclass."""

    KIND = KIND_ENUM
    SPEC_CLS = EnumSpec

    def kind_fields(self) -> dict[str, Any]:
        members = [
            EnumMemberSpec(name=member.name, value=member.value)
            for member in self.cls  # type: ignore[union-attr]  — cls is non-None for enums
        ]
        # Most enums are homogeneous; pick the first member's value
        # type as the representative. Empty enums (rare) default to
        # ``"str"`` so the field always has a concrete value.
        if members:
            first_value = next(iter(self.cls)).value  # type: ignore[arg-type]
            value_type = type(first_value).__name__
        else:
            value_type = "str"
        return {"value_type": value_type, "members": members}


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


# ---------------------------------------------------------------------------
# Level 5: pipelines (custom ``build()`` — translates legacy ``cls._spec``)
# ---------------------------------------------------------------------------


class PipelineBuilder(SpecBuilder):
    """Build a :class:`PipelineSpec` directly from a ``Pipeline`` subclass.

    Reads ``cls._wiring`` (deduped bindings), ``cls.INPUT_DATA``,
    ``cls.start_node``, and the per-node ``run()`` return annotations
    to construct nodes / input_data / start_node / edges. Routes
    ``cls._init_subclass_errors`` onto matching components via
    :meth:`attach_class_captures`.

    Class-contract issues (missing INPUTS, prepare-signature
    mismatches, etc.) live canonically on the standalone per-kind
    spec (``registries[KIND_STEP][node_name]`` etc.) — not duplicated
    here. The frontend follows the ``node_name`` ref to find them.
    """

    KIND = KIND_PIPELINE
    SPEC_CLS = PipelineSpec

    def kind_fields(self) -> dict[str, Any]:
        from llm_pipeline.specs.pipelines import (
            EdgeSpec,
            NodeBindingSpec,
        )
        from llm_pipeline.wiring import Extraction, Review, Step

        cls = self.cls
        deduped_bindings = list(getattr(cls, "_wiring", {}).values())
        raw_nodes = [b.cls for b in deduped_bindings]

        node_bindings: list[NodeBindingSpec] = []
        for binding in deduped_bindings:
            if isinstance(binding, Step):
                binding_kind = "step"
            elif isinstance(binding, Extraction):
                binding_kind = "extraction"
            elif isinstance(binding, Review):
                binding_kind = "review"
            else:
                continue
            node_bindings.append(NodeBindingSpec(
                binding_kind=binding_kind,
                node_name=_node_name_for_binding(binding),
                wiring=_build_wiring_spec(binding),
            ))

        edges = _build_edges(raw_nodes)

        input_data_cls = getattr(cls, "INPUT_DATA", None)
        input_data = self.json_schema(input_data_cls)

        start_node_ref = _class_to_artifact_ref(
            getattr(cls, "start_node", None), self.resolver,
        )

        return {
            "input_data": input_data,
            "nodes": node_bindings,
            "edges": edges,
            "start_node": start_node_ref,
        }


def _node_name_for_binding(binding) -> str:
    """Snake_case registry key for ``binding.cls``."""
    from llm_pipeline.naming import to_snake_case
    from llm_pipeline.wiring import Extraction, Review, Step

    cls = binding.cls
    if isinstance(binding, Step):
        return cls.step_name()
    suffix = "Extraction" if isinstance(binding, Extraction) else "Review"
    return to_snake_case(cls.__name__, strip_suffix=suffix)


def _build_wiring_spec(binding):
    """Serialise a binding's ``inputs_spec`` into a WiringSpec."""
    from llm_pipeline.specs.pipelines import SourceSpec, WiringSpec

    spec = binding.inputs_spec
    return WiringSpec(
        inputs_cls=f"{spec.inputs_cls.__module__}.{spec.inputs_cls.__qualname__}",
        field_sources={
            name: _serialise_source(src)
            for name, src in spec.field_sources.items()
        },
    )


def _serialise_source(source):
    from llm_pipeline.specs.pipelines import SourceSpec
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
    raise TypeError(f"Unknown Source subclass {type(source).__name__!r}")


def _build_edges(raw_nodes: list[type]):
    """Build the EdgeSpec list from each node's ``run()`` return annotations."""
    from llm_pipeline.graph.validator import _next_node_classes
    from llm_pipeline.specs.pipelines import EdgeSpec

    edges = []
    for node in raw_nodes:
        targets = _next_node_classes(node, raw_nodes)
        if _run_returns_end(node, raw_nodes):
            edges.append(EdgeSpec(from_node=node.__name__, to_node="End"))
        for target in targets:
            edges.append(EdgeSpec(
                from_node=node.__name__, to_node=target.__name__,
            ))
    return edges


def _run_returns_end(node_cls: type, raw_nodes: list[type]) -> bool:
    """True if ``node_cls.run()``'s return annotation reaches ``End``."""
    import typing
    from types import UnionType
    from pydantic_graph import End

    return_annotation = node_cls.run.__annotations__.get("return")
    if return_annotation is None:
        return False
    if isinstance(return_annotation, str):
        try:
            name_to_node = {n.__name__: n for n in raw_nodes}
            return_annotation = eval(  # noqa: S307
                return_annotation,
                getattr(node_cls.run, "__globals__", {}),
                name_to_node | {"End": End},
            )
        except (NameError, SyntaxError):
            return False

    def _has_end(ann) -> bool:
        if ann is End:
            return True
        origin = typing.get_origin(ann)
        if origin is End:
            return True
        if origin is typing.Union or origin is UnionType:
            return any(_has_end(arg) for arg in typing.get_args(ann))
        return False

    return _has_end(return_annotation)
