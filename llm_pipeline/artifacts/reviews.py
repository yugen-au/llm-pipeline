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

from typing import Any, Literal

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.base.blocks import CodeBodySpec, JsonSchemaWithRefs
from llm_pipeline.artifacts.base.builder import SpecBuilder
from llm_pipeline.artifacts.base.fields import FieldRef, FieldsBase
from llm_pipeline.artifacts.base.kinds import KIND_REVIEW
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _to_registry_key,
)


__all__ = ["MANIFEST", "ReviewBuilder", "ReviewFields", "ReviewSpec", "ReviewsWalker"]


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


class ReviewFields(FieldsBase):
    """Routing-key vocabulary for :class:`ReviewSpec` issue captures.

    See :class:`llm_pipeline.artifacts.steps.StepFields` for the routing
    pattern. Path validity is checked at class-load time against
    :class:`ReviewSpec`.
    """

    SPEC_CLS = ReviewSpec

    INPUTS = FieldRef("inputs")
    OUTPUT = FieldRef("output")


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


class ReviewsWalker(Walker):
    """Register ``ReviewNode`` subclasses from ``reviews/``."""

    KIND = KIND_REVIEW
    BUILDER = ReviewBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.graph.nodes import ReviewNode

        return _is_locally_defined_class(value, mod, ReviewNode)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name, strip_suffix="Review")


MANIFEST = ArtifactManifest(
    kind=KIND_REVIEW,
    subfolder="reviews",
    level=4,
    spec_cls=ReviewSpec,
    fields_cls=ReviewFields,
    walker=ReviewsWalker(),
)
