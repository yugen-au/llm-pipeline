"""``ExtractionSpec`` — ``ExtractionNode`` subclasses (Level 4).

An extraction takes pathway inputs and produces rows that get
persisted to a SQLModel table. The extraction's ``MODEL`` ClassVar
points at the table; the ``extract(self, inputs)`` body shapes
rows; the ``run(self, ctx)`` body wires the extraction into the
graph.

The ``table`` field is an :class:`ArtifactRef` — the source-side
class name (``cls.MODEL.__name__``) plus a resolved
:class:`SymbolRef` when the resolver matches the registered table.
Same shape used wherever a spec references another registered
artifact (``StepSpec.tools``, ``PipelineSpec.start_node``, etc.).
"""
from __future__ import annotations

from typing import Any, Literal

from llm_pipeline.artifacts.base import ArtifactRef, ArtifactSpec
from llm_pipeline.artifacts.base.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.artifacts.base.builder import SpecBuilder, _class_to_artifact_ref
from llm_pipeline.artifacts.base.fields import FieldRef, FieldsBase
from llm_pipeline.artifacts.base.kinds import KIND_EXTRACTION
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _to_registry_key,
)


__all__ = [
    "MANIFEST",
    "ExtractionBuilder",
    "ExtractionFields",
    "ExtractionSpec",
    "ExtractionsWalker",
]


class ExtractionSpec(ArtifactSpec):
    """An ``ExtractionNode`` subclass declared in ``llm_pipelines/extractions/``."""

    kind: Literal[KIND_EXTRACTION] = KIND_EXTRACTION  # type: ignore[assignment]

    # The extraction's INPUTS class shape.
    inputs: JsonSchemaWithRefs | None = None

    # The MODEL (SQLModel table) — wrapped as :class:`ArtifactRef`
    # carrying the source-side class name + resolved (kind, name)
    # ref when available. ``None`` when MODEL isn't set on the
    # class (the missing-MODEL issue lives on ``self.issues``).
    # Per-reference issues (e.g. unresolved table) land on
    # ``self.table.issues``.
    table: ArtifactRef | None = None

    # The body of ``extract(self, inputs)``. Returns a list of
    # MODEL instances; the framework persists + records them.
    extract: CodeBodySpec | None = None

    # The body of ``run(self, ctx)`` — graph wiring.
    run: CodeBodySpec | None = None


class ExtractionFields(FieldsBase):
    """Routing-key vocabulary for :class:`ExtractionSpec` issue captures.

    See :class:`llm_pipeline.artifacts.steps.StepFields` for the routing
    pattern. Path validity is checked at class-load time against
    :class:`ExtractionSpec`.
    """

    SPEC_CLS = ExtractionSpec

    INPUTS = FieldRef("inputs")
    TABLE = FieldRef("table")


class ExtractionBuilder(SpecBuilder):
    """Build an :class:`ExtractionSpec` from an ``ExtractionNode`` subclass."""

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


class ExtractionsWalker(Walker):
    """Register ``ExtractionNode`` subclasses from ``extractions/``."""

    BUILDER = ExtractionBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import ExtractionNode

        return _is_locally_defined_class(value, mod, ExtractionNode)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Extraction")


MANIFEST = ArtifactManifest(
    subfolder="extractions",
    level=4,
    spec_cls=ExtractionSpec,
    fields_cls=ExtractionFields,
    walker=ExtractionsWalker(),
)
