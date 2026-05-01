"""``ExtractionSpec`` — ``ExtractionNode`` subclasses (Level 4).

An extraction takes pathway inputs and produces rows that get
persisted to a SQLModel table. The extraction's ``MODEL`` ClassVar
points at the table; the ``extract(self, inputs)`` body shapes
rows; the ``run(self, ctx)`` body wires the extraction into the
graph.

The ``table_name`` field references the table by registry key
(``KIND_TABLE`` once the schemas/tables split lands; for now
the schema registry covers SQLModel content too — the ref still
resolves via the universal resolver).

Phase C.1 declares the spec shape. Phase C.2's walker populates
it: INPUTS schema via Pydantic introspection; ``extract`` /
``run`` bodies via :func:`analyze_code_body`; ``table_name`` from
``cls.MODEL.__qualname__`` -> snake_case lookup.
"""
from __future__ import annotations

from typing import Literal

from llm_pipeline.specs.base import ArtifactSpec
from llm_pipeline.specs.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.specs.kinds import KIND_EXTRACTION


__all__ = ["ExtractionFields", "ExtractionSpec"]


class ExtractionFields:
    """Routing-key constants for :class:`ExtractionSpec` issue captures.

    See :class:`llm_pipeline.specs.steps.StepFields` for the rationale.
    Each value must equal an :class:`ArtifactField`-typed field name
    on :class:`ExtractionSpec`.

    Note ``table_name`` is intentionally NOT here — it's a primitive
    ``str | None`` and can't carry sub-component issues. Captures
    about MODEL/table use ``location.field=None`` and live on
    top-level ``ExtractionSpec.issues``.
    """

    INPUTS = "inputs"


class ExtractionSpec(ArtifactSpec):
    """An ``ExtractionNode`` subclass declared in ``llm_pipelines/extractions/``."""

    kind: Literal[KIND_EXTRACTION] = KIND_EXTRACTION  # type: ignore[assignment]

    # The extraction's INPUTS class shape.
    inputs: JsonSchemaWithRefs | None = None

    # The MODEL (SQLModel table) referenced by registry name.
    # ``None`` when MODEL isn't set on the class (issue captured
    # on ``self.issues``).
    table_name: str | None = None

    # The body of ``extract(self, inputs)``. Returns a list of
    # MODEL instances; the framework persists + records them.
    extract: CodeBodySpec | None = None

    # The body of ``run(self, ctx)`` — graph wiring.
    run: CodeBodySpec | None = None
