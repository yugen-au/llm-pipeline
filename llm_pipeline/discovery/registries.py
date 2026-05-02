"""Per-kind registry shape + initialisation helpers.

Phase C.2.a defines the structural target of the per-artifact
discovery flow:

    app.state.registries: dict[str, dict[str, ArtifactRegistration]]

Keys are :data:`KIND_*` constants from
:mod:`llm_pipeline.artifacts.kinds`. Inner keys are snake_case
artifact names. Values are :class:`ArtifactRegistration` records
pairing a typed spec with the runtime class/value.

Phase C.2.b adds the per-kind walkers that populate this
structure during discovery. Phase C.2.a (this commit) only
plumbs the empty shape into ``app.state`` so consumers can be
migrated incrementally without disturbing existing
``pipeline_registry`` / ``_AUTO_GENERATE_REGISTRY`` paths.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

from llm_pipeline.artifacts.kinds import ALL_KINDS

if TYPE_CHECKING:
    from llm_pipeline.artifacts import ArtifactRegistration


__all__ = ["init_empty_registries"]


def init_empty_registries() -> dict[str, dict[str, "ArtifactRegistration"]]:
    """Return a fresh per-kind registry container with every kind keyed empty.

    Used by app boot to seed ``app.state.registries`` before
    discovery walkers populate per-kind entries. Keying every
    kind upfront means consumers can iterate ``ALL_KINDS`` without
    KeyError on kinds that happen to have no registered artifacts
    yet.

    Returns a brand-new dict each call — callers (notably
    ``create_app``) should hold the reference if they want
    mutations to persist.
    """
    return {kind: {} for kind in ALL_KINDS}
