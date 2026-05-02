"""``ArtifactManifest`` — per-kind metadata dataclass.

Each ``llm_pipeline.artifacts.{kind}`` module exports a module-level
``MANIFEST: ArtifactManifest`` constant. :mod:`llm_pipeline.artifacts`
collects them into ``ARTIFACT_MANIFESTS``, so adding a new kind =
create the kind file (with its spec / walker / builder / fields /
MANIFEST), then add one import in :mod:`llm_pipeline.artifacts`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llm_pipeline.artifacts.base.walker import Walker


__all__ = ["ArtifactManifest"]


@dataclass(frozen=True)
class ArtifactManifest:
    """Per-kind metadata. One entry per first-class artifact kind.

    The discriminator value (``KIND_*`` constant) and routing-key
    constants live on the spec class itself
    (:attr:`ArtifactSpec.KIND` + auto-generated UPPER_CASE
    :class:`FieldRef` attributes) — the manifest derives :attr:`kind`
    from the spec rather than carrying duplicates.

    - ``subfolder``: directory under ``llm_pipelines/`` holding
      this kind's files.
    - ``level``: dependency tier. A kind at level N may reference
      kinds at level < N. Drives module load order and walker
      resolver visibility.
    - ``spec_cls``: the per-kind :class:`ArtifactSpec` subclass.
    - ``walker``: the per-kind :class:`Walker` instance.
    """

    subfolder: str
    level: int
    spec_cls: type
    walker: "Walker"

    @property
    def kind(self) -> str:
        """Discriminator value, read from ``spec_cls.KIND``."""
        return self.spec_cls.KIND
