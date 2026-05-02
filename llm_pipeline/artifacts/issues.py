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

from llm_pipeline.artifacts.base import ArtifactField

if TYPE_CHECKING:
    from llm_pipeline.graph.spec import ValidationIssue
    from llm_pipeline.artifacts.base import ArtifactSpec


__all__ = ["flatten_artifact_issues"]


def flatten_artifact_issues(spec: "ArtifactSpec") -> list["ValidationIssue"]:
    """Return every issue attached to ``spec`` and its sub-components.

    Walks polymorphically: any value that's an :class:`ArtifactField`
    contributes its ``issues`` plus issues nested in its own
    sub-component fields, recursively. Lists are traversed
    element-wise. Returns a fresh list — callers may mutate.

    Generic — adding a new ``ArtifactField`` subclass or wrapping
    primitive fields in one is automatically covered without
    touching this helper.
    """
    return _collect_issues(spec)


def _collect_issues(value: object) -> list:
    """Recursively gather issues from an ``ArtifactField``-typed
    tree, including ``list[ArtifactField]`` fields.

    Skips the ``issues`` field when recursing into an
    :class:`ArtifactField` to avoid double-counting (it's already
    captured at the parent level).
    """
    if isinstance(value, ArtifactField):
        out = list(value.issues)
        for sub_name in type(value).model_fields:
            if sub_name == "issues":
                continue
            sub = getattr(value, sub_name, None)
            out.extend(_collect_issues(sub))
        return out
    if isinstance(value, list):
        out: list = []
        for item in value:
            out.extend(_collect_issues(item))
        return out
    return []
