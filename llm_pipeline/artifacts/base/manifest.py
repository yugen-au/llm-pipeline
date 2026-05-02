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

    The discriminator value (``KIND_*`` constant) lives on the spec
    class as :attr:`ArtifactSpec.KIND` — the manifest derives it
    via :attr:`kind` rather than carrying it as a duplicate field.

    - ``subfolder``: directory under ``llm_pipelines/`` holding
      this kind's files.
    - ``level``: dependency tier. A kind at level N may reference
      kinds at level < N. Drives module load order and walker
      resolver visibility.
    - ``spec_cls``: the per-kind :class:`ArtifactSpec` subclass.
    - ``fields_cls``: the per-kind ``Fields`` constants class
      (routing keys for ``__init_subclass__`` captures), or
      ``None`` for kinds without capture sites.
    - ``walker``: the per-kind :class:`Walker` instance.
    """

    subfolder: str
    level: int
    spec_cls: type
    fields_cls: type | None
    walker: "Walker"

    @property
    def kind(self) -> str:
        """Discriminator value, read from ``spec_cls.KIND``."""
        return self.spec_cls.KIND
