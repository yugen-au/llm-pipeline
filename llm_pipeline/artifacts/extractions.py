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

from typing import Literal

from llm_pipeline.artifacts.base import ArtifactRef, ArtifactSpec
from llm_pipeline.artifacts.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.artifacts.fields import FieldRef, FieldsBase
from llm_pipeline.artifacts.kinds import KIND_EXTRACTION


__all__ = ["ExtractionFields", "ExtractionSpec"]


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
