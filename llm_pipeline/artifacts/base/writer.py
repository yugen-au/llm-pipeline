"""``Writer`` ABC — per-kind ``ArtifactSpec`` ⇒ source code.

The inverse of :class:`SpecBuilder`. A Writer takes a populated
spec and produces the Python source text that, when loaded by the
discovery walker, would round-trip back to the same spec.

Used by codegen / sandbox / creator flows that mutate an artifact
through its spec and need to write the result back to disk.

Phase scope: this module ships the ABC contract only. Per-kind
:class:`Writer` subclasses (and the disk-write side) land alongside
each kind in subsequent commits, once the open questions below
are resolved.

Open questions (to settle before concrete subclasses):

* **Round-trip fidelity**: does the writer preserve hand edits in
  spec sub-components it doesn't itself populate (e.g. a step's
  ``prepare`` body when only the inputs schema changed), or is the
  spec always the single source of truth?
* **Refs vs literals**: a spec carries :class:`ArtifactRef`
  instances pointing at sibling artifacts — does the writer emit
  the original Python identifier (round-trip) or re-resolve
  through the registry?
* **Imports**: does the writer regenerate the import block from
  ``spec.imports``, or does it preserve the existing import order
  / commented imports / ``__future__`` lines from a prior pass?
* **Code body source**: :class:`CodeBodySpec` carries ``source``
  text plus refs — is ``source`` the single source of truth for
  the body, or do refs round-trip independently?

Until these are settled, :meth:`Writer.write` raises
:class:`NotImplementedError`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_pipeline.artifacts.base import ArtifactSpec


__all__ = ["Writer"]


class Writer(ABC):
    """Per-kind writer base — universal source-code generator.

    Subclasses pin :attr:`KIND` and :attr:`SPEC_CLS` and override
    :meth:`write`. The base ``__init__`` stashes the spec for the
    subclass to read.
    """

    KIND: ClassVar[str]
    SPEC_CLS: ClassVar[type]

    def __init__(self, *, spec: "ArtifactSpec") -> None:
        self.spec = spec

    @abstractmethod
    def write(self) -> str:
        """Render :attr:`spec` to Python source text.

        Returns the file's full contents (module docstring, imports,
        class declarations, function bodies). Caller decides where to
        put it on disk.
        """
