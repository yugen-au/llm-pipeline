"""Generic per-kind artifact routes.

Two endpoints, both kind-parameterised so adding a new artifact
kind doesn't need a route change:

- ``GET /api/artifacts/{kind}`` — list every registered artifact
  in that kind's registry, with a small validation summary per
  row (used by the frontend list pages).
- ``GET /api/artifacts/{kind}/{name}`` — return the full typed
  ``ArtifactSpec`` for a single artifact (used by the frontend
  detail editors).

Both reach into ``app.state.registries`` (populated at boot by
the per-kind discovery walkers in
:mod:`llm_pipeline.discovery`). The ``kind`` path parameter is
validated against :data:`ALL_KINDS`; unknown kinds 404.

Phase D.1 — read-only. Edit ops (POST) and run-gating
(``POST /api/runs``) land in later sub-phases per the plan.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from llm_pipeline.artifacts import (
    ArtifactRegistration,
    flatten_artifact_issues,
)
from llm_pipeline.artifacts.base.kinds import ALL_KINDS


router = APIRouter(prefix="/artifacts", tags=["artifacts"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class ArtifactListItem(BaseModel):
    """One row in the per-kind list view.

    Carries identity + a small validation summary so the
    frontend list page can render a row + status badge without
    having to fetch the full spec for every artifact.
    """

    kind: str
    name: str
    cls: str
    source_path: str

    # Total count of issues across this artifact and every nested
    # sub-component (CodeBodySpec, JsonSchemaWithRefs, PromptData).
    issue_count: int

    # ``True`` iff any of those issues has severity ``"error"``.
    # The frontend uses this for the red-vs-yellow-vs-clean
    # status indicator.
    has_errors: bool


class ArtifactListResponse(BaseModel):
    """Response shape for ``GET /api/artifacts/{kind}``."""

    kind: str
    count: int
    artifacts: list[ArtifactListItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{kind}", response_model=ArtifactListResponse)
async def list_artifacts(kind: str, request: Request) -> ArtifactListResponse:
    """List every registered artifact for ``kind``.

    Returns ``ArtifactListItem`` rows in registry order (snake_case
    name asc, since registries are ``dict[name, ...]`` and
    Python preserves insertion order; discovery walkers sort their
    inputs).

    404 if ``kind`` is not a known artifact kind. An empty list
    is returned (200) when the kind is known but has no
    registered artifacts.
    """
    _assert_known_kind(kind)
    registries: dict = getattr(request.app.state, "registries", {})
    kind_reg: dict = registries.get(kind, {})

    items = [
        _to_list_item(reg) for _, reg in sorted(kind_reg.items())
    ]
    return ArtifactListResponse(
        kind=kind,
        count=len(items),
        artifacts=items,
    )


@router.get("/{kind}/{name}")
async def get_artifact(kind: str, name: str, request: Request) -> dict[str, Any]:
    """Return the full :class:`ArtifactSpec` for ``(kind, name)``.

    The body is the raw ``spec.model_dump(mode="json")`` — Pydantic
    serialises the per-kind subclass faithfully, so the frontend
    sees every kind-specific field (e.g.
    ``StepSpec.prepare.refs[*].line``,
    ``SchemaSpec.definition.refs``, etc.).

    404 if either the kind is unknown or no artifact exists at
    that registry slot.
    """
    _assert_known_kind(kind)
    registries: dict = getattr(request.app.state, "registries", {})
    reg: ArtifactRegistration | None = registries.get(kind, {}).get(name)
    if reg is None:
        raise HTTPException(
            status_code=404,
            detail=f"{kind} {name!r} not found",
        )
    return reg.spec.model_dump(mode="json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _assert_known_kind(kind: str) -> None:
    if kind not in ALL_KINDS:
        raise HTTPException(
            status_code=404,
            detail=(
                f"unknown artifact kind {kind!r}; expected one of: "
                f"{', '.join(sorted(ALL_KINDS))}"
            ),
        )


def _to_list_item(reg: ArtifactRegistration) -> ArtifactListItem:
    """Build an :class:`ArtifactListItem` from a registration.

    Counts issues across every nested sub-component via
    :func:`flatten_artifact_issues` so the frontend's "broken?"
    badge reflects deep state, not just top-level ``spec.issues``.
    """
    spec = reg.spec
    issues = flatten_artifact_issues(spec)
    return ArtifactListItem(
        kind=spec.kind,
        name=spec.name,
        cls=spec.cls,
        source_path=spec.source_path,
        issue_count=len(issues),
        has_errors=any(i.severity == "error" for i in issues),
    )
