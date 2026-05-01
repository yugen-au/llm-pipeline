"""``ReviewSpec`` — ``ReviewNode`` subclasses (Level 4).

A review pauses the pipeline for human input. The reviewer sees
the INPUTS class's data and submits a response shaped by the
OUTPUT class. An optional webhook URL fires when the review is
opened.

The ``output`` schema is what the reviewer's response gets
validated against. The ``run(self, ctx)`` body wires the review
into the graph (typically calls ``self._begin_review(ctx)`` and
returns the post-review next node).

Phase C.1 declares the spec shape. Phase C.2's walker populates
it: INPUTS / OUTPUT schemas via Pydantic introspection; ``run``
body via :func:`analyze_code_body`; ``webhook_url`` from the
class's ClassVar.
"""
from __future__ import annotations

from typing import Literal

from llm_pipeline.specs.base import ArtifactSpec
from llm_pipeline.specs.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.specs.kinds import KIND_REVIEW


__all__ = ["ReviewFields", "ReviewSpec"]


class ReviewFields:
    """Routing-key constants for :class:`ReviewSpec` issue captures.

    See :class:`llm_pipeline.specs.steps.StepFields` for the rationale.
    Each value must equal a field name on :class:`ReviewSpec`.
    """

    INPUTS = "inputs"
    OUTPUT = "output"


class ReviewSpec(ArtifactSpec):
    """A ``ReviewNode`` subclass declared in ``llm_pipelines/reviews/``."""

    kind: Literal[KIND_REVIEW] = KIND_REVIEW  # type: ignore[assignment]

    # The review's INPUTS class shape — what the reviewer sees.
    inputs: JsonSchemaWithRefs | None = None

    # The reviewer's response shape — Pydantic class the
    # webhook payload gets validated against.
    output: JsonSchemaWithRefs | None = None

    # Optional webhook URL fired when the review is opened. Read
    # from the class's ``webhook_url`` ClassVar; ``None`` when
    # unset (the framework falls back to the env var at runtime).
    webhook_url: str | None = None

    # The body of ``run(self, ctx)`` — graph wiring.
    run: CodeBodySpec | None = None
