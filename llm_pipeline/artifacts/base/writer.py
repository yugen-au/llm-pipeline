"""``Writer`` ABC — per-kind ``ArtifactSpec`` ⇒ source code.

Two paths converge on a single sink:

- :meth:`edit` — start from existing source, apply spec changes
  (libcst surgery, targeted text replacement). Use when the UI
  saves a change to an existing artifact.
- :meth:`write` — start from nothing, render the spec from scratch
  via the kind's :class:`ArtifactTemplate`. Use when the creator
  generates a new artifact.
- :meth:`apply` — atomic write to disk. Same for every kind.

Both ``edit`` and ``write`` return a final source string; ``apply``
takes that string and writes it. Per-kind writers pick whichever
path makes sense for their input and produce the same string-shaped
output.

Per-sub-component renderers (in
:mod:`llm_pipeline.artifacts.base.renderers`) handle the granular
"this :class:`ArtifactField` ⇒ Python text" conversions; the
per-kind :class:`ArtifactTemplate` orchestrates them into the
overall file shape. libcst handles fine-grained surgical edits in
:meth:`edit`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, TYPE_CHECKING

if TYPE_CHECKING:
    from llm_pipeline.artifacts.base import ArtifactSpec


__all__ = ["Writer"]


class Writer(ABC):
    """Per-kind writer base.

    Subclasses pin :attr:`SPEC_CLS` and implement :meth:`edit` and
    :meth:`write`. :meth:`apply` is shared.
    """

    SPEC_CLS: ClassVar[type]

    def __init__(self, *, spec: "ArtifactSpec") -> None:
        self.spec = spec

    @abstractmethod
    def edit(self, original: str) -> str:
        """Apply the spec to existing source, return updated source.

        Implementations typically use libcst to parse ``original``,
        find the target nodes, replace them with renderer-produced
        fragments from :attr:`spec`, then serialise back.
        """

    @abstractmethod
    def write(self) -> str:
        """Render :attr:`spec` to a fresh source file.

        Implementations typically render the kind's
        :class:`ArtifactTemplate` against :attr:`spec`.
        """

    def apply(
        self,
        content: str,
        *,
        path: Path | None = None,
        root: Path | None = None,
    ) -> bool:
        """Write ``content`` to disk via the path-guarded codegen IO.

        Defaults to ``self.spec.source_path``. Parses the content
        string into a libcst ``Module`` first — catches malformed
        output before touching disk and lets us reuse the codegen
        atomic-write + dry-run + path-guard pipeline.

        Returns ``True`` if the file was written (or would be written
        in dry-run mode), ``False`` if the existing content already
        matched and no write was needed. Raises
        :class:`llm_pipeline.codegen.CodegenPathError` when the
        target falls outside the configured ``llm_pipelines/`` root.
        """
        import libcst as cst

        from llm_pipeline.codegen.io import write_module_if_changed

        target = Path(path) if path else Path(self.spec.source_path)
        module = cst.parse_module(content)
        return write_module_if_changed(target, module, root=root)
