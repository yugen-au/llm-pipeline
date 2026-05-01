"""Helpers for collecting issues from per-kind ``ArtifactSpec`` instances.

Per the per-artifact architecture, each spec's :attr:`issues`
list is the *direct* (top-level) issues for the artifact. Issues
attached to sub-components — :class:`CodeBodySpec` (prepare /
run / extract bodies), :class:`JsonSchemaWithRefs` (inputs /
instructions / output / definition), :class:`PromptData` — live
on those sub-components.

For "is this artifact broken at all?" queries (the API list
endpoint, UI badges, run-time gates), callers want a flat union
across every level. :func:`flatten_artifact_issues` provides
that — generically, by walking the spec's typed sub-component
fields rather than enumerating per-kind combinations.

Order of returned issues is stable: top-level
(:attr:`spec.issues`) first, then sub-component issues in the
order Pydantic enumerates the fields (declaration order on the
subclass).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_pipeline.specs.blocks import (
    CodeBodySpec,
    JsonSchemaWithRefs,
    PromptData,
)

if TYPE_CHECKING:
    from llm_pipeline.graph.spec import ValidationIssue
    from llm_pipeline.specs.base import ArtifactSpec


__all__ = ["flatten_artifact_issues"]


def flatten_artifact_issues(spec: "ArtifactSpec") -> list["ValidationIssue"]:
    """Return every issue attached to ``spec`` and its sub-components.

    Walks the known issue-bearing sub-component types
    (:class:`CodeBodySpec`, :class:`JsonSchemaWithRefs`,
    :class:`PromptData`) declared as fields on the per-kind
    subclass. Returns a fresh list — callers may mutate.

    The walker recognises sub-components by *type*, not by field
    name, so adding a new spec field that uses one of these
    building blocks is automatically covered. Adding a new
    issue-bearing building block requires updating this helper.
    """
    issues: list = list(spec.issues)
    for field_name in type(spec).model_fields:
        value = getattr(spec, field_name, None)
        issues.extend(_collect_component_issues(value))
    return issues


def _collect_component_issues(value: object) -> list:
    """Return issues from a sub-component value, or empty list."""
    if isinstance(value, CodeBodySpec):
        return list(value.issues)
    if isinstance(value, JsonSchemaWithRefs):
        return list(value.issues)
    if isinstance(value, PromptData):
        # PromptData carries its own issues plus a nested
        # JsonSchemaWithRefs for variables — collect both.
        out = list(value.issues)
        out.extend(value.variables.issues)
        return out
    return []
