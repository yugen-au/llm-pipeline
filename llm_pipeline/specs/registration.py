"""``ArtifactRegistration`` — pairs a typed spec with its runtime object.

Used as the value type in ``app.state.registries[kind][name]`` so
consumers can pick the right side per concern:

- UI / introspection / API serialisation: read ``.spec``
- Ops / runtime (running pipelines, instantiating tools,
  reading constants): read ``.obj``

The split makes the heterogeneous nature of artifact kinds
explicit. Some kinds register a class (``Step``, ``Pipeline``,
``Schema``, ``Tool``, ``Enum``); others register a plain value
(``Constant``). The ``obj`` field carries whichever it is — the
spec carries the typed UI/API contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm_pipeline.specs.base import ArtifactSpec


__all__ = ["ArtifactRegistration"]


@dataclass(frozen=True)
class ArtifactRegistration:
    """Pairs an artifact's contract (spec) with its runtime object.

    Frozen so registry entries are hash-stable and immutable —
    discovery populates them once at boot and downstream consumers
    only read.
    """

    spec: ArtifactSpec
    obj: Any

    @property
    def kind(self) -> str:
        return self.spec.kind

    @property
    def name(self) -> str:
        return self.spec.name
