"""Per-kind spec builders.

Each builder takes a loaded class/value plus its source-file
context and returns a populated per-kind :class:`ArtifactSpec`.
Builders introspect the runtime class/value and call into
:mod:`llm_pipeline.cst_analysis` for source-side metadata; they
don't touch disk.

Builders never raise — partial state surfaces via the spec's
``issues`` field on the relevant component. Schema-generation
failures, missing class state, and analyser parse errors are all
captured.

The :class:`SpecBuilder` ABC + shared helpers live in
:mod:`llm_pipeline.artifacts.base.builder`.
"""
from __future__ import annotations

from typing import Any

from llm_pipeline.cst_analysis import ResolverHook
from llm_pipeline.artifacts.base.blocks import (
    CodeBodySpec,
    JsonSchemaWithRefs,
    PromptData,
)
from llm_pipeline.artifacts.base.builder import (
    SpecBuilder,
    _class_to_artifact_ref,
    _docstring,
    _qualified,
    build_code_body,
    json_schema_with_refs,
)
from llm_pipeline.artifacts.constants import ConstantSpec
from llm_pipeline.artifacts.enums import EnumMemberSpec, EnumSpec
from llm_pipeline.artifacts.extractions import ExtractionSpec
from llm_pipeline.artifacts.base.kinds import (
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
from llm_pipeline.artifacts.pipelines import NodeBindingSpec, PipelineSpec
from llm_pipeline.artifacts.reviews import ReviewSpec
from llm_pipeline.artifacts.schemas import SchemaSpec
from llm_pipeline.artifacts.steps import StepSpec
from llm_pipeline.artifacts.tables import IndexSpec, TableSpec
from llm_pipeline.artifacts.tools import ToolSpec


__all__ = [
    # Re-exported from base.builder for back-compat
    "build_code_body",
    "json_schema_with_refs",
    "SpecBuilder",
    # Per-kind builders — every kind goes through SpecBuilder.
    "ConstantBuilder",
    "EnumBuilder",
    "ExtractionBuilder",
    "PipelineBuilder",
    "ReviewBuilder",
    "SchemaBuilder",
    "StepBuilder",
    "TableBuilder",
    "ToolBuilder",
]


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
    """Build a :class:`ToolSpec` from an :class:`AgentTool` subclass.

    Reads ``cls.Inputs`` / ``cls.Args`` / ``cls.run`` directly. Missing
    attrs produce ``None``-valued spec fields; the per-class capture
    model surfaces the contract violation.
    """

    KIND = KIND_TOOL
    SPEC_CLS = ToolSpec

    def kind_fields(self) -> dict[str, Any]:
        cls = self.cls
        inputs_cls = getattr(cls, "INPUTS", None)
        args_cls = getattr(cls, "ARGS", None)
        return {
            "inputs": self.json_schema(inputs_cls),
            "args": self.json_schema(args_cls),
            "body": self.code_body("run"),
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
        from llm_pipeline.artifacts.pipelines import (
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
    from llm_pipeline.artifacts.pipelines import SourceSpec, WiringSpec

    spec = binding.inputs_spec
    return WiringSpec(
        inputs_cls=f"{spec.inputs_cls.__module__}.{spec.inputs_cls.__qualname__}",
        field_sources={
            name: _serialise_source(src)
            for name, src in spec.field_sources.items()
        },
    )


def _serialise_source(source):
    from llm_pipeline.artifacts.pipelines import SourceSpec
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
    from llm_pipeline.artifacts.pipelines import EdgeSpec

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
