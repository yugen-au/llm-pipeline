"""Validation issue types — bottom of the spec dependency graph.

``ArtifactField`` (in :mod:`llm_pipeline.artifacts.base`) carries
``issues: list[ValidationIssue]``; many other spec components also
reference these types. Defining them here, with no spec imports,
keeps the import graph acyclic — :mod:`specs.base` imports from
this module; everything else imports from either.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


__all__ = [
    "ValidationIssue",
    "ValidationLocation",
    "ValidationSummary",
]


class ValidationLocation(BaseModel):
    """Where a validation issue lives.

    ``pipeline`` and ``node`` are display-only context.

    ``path`` is the typed routing path; the
    :meth:`ArtifactField.attach_class_captures` walker uses it to
    land each issue on the right sub-component. Constructed via
    :class:`llm_pipeline.artifacts.base.fields.FieldRef`.

    ``field`` is the legacy single-segment key, kept for back-compat.

    ``subfield`` is free-form UI metadata for finer-than-routing
    granularity (per-prompt-variable name etc.). The router ignores
    it; the UI uses it to attach indicators below the routing target.
    """

    model_config = ConfigDict(extra="forbid")

    pipeline: str | None = None
    node: str | None = None
    field: str | None = None
    path: str | None = None
    subfield: str | None = None

    @field_validator("path", "field", mode="before")
    @classmethod
    def _coerce_to_str(cls, v: object) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            return v
        return str(v)


class ValidationIssue(BaseModel):
    """One thing wrong (or worth flagging) about a spec component.

    ``severity`` gates runnability — ``error`` blocks; ``warning``
    is informational. ``code`` is a stable machine-readable id;
    frontends branch UX on it. ``location`` carries display +
    routing info; the routing walker reads ``location.path``.
    """

    model_config = ConfigDict(extra="forbid")

    severity: Literal["error", "warning"]
    code: str
    message: str
    location: ValidationLocation
    suggestion: str | None = None


class ValidationSummary(BaseModel):
    """API digest of a pipeline's validation state."""

    model_config = ConfigDict(extra="forbid")

    runnable: bool
    severity: Literal["clean", "warnings", "errors", "import_error"]
    issue_count: int
    issues: list[ValidationIssue]
