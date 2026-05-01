"""Per-artifact spec primitives.

This package defines the typed contracts used by the code <-> UI
translation layer. Per-kind ``ArtifactSpec`` subclasses (added in
later phases) carry everything the UI needs to render an artifact
and everything the libcst hot-swap needs to translate UI edits back
into code.

Phase A (this module): foundational types only — no behaviour change
to existing pipeline code.

- ``ArtifactSpec`` (base.py): common base for every per-kind subclass.
- Building blocks (blocks.py): ``SymbolRef``, ``CodeBodySpec``,
  ``JsonSchemaWithRefs``, ``PromptData``. Reusable across specs.
- Kind constants (kinds.py): ``KIND_*`` strings and ``LEVEL_BY_KIND``
  mapping for dependency-tier ordering.

See ``.claude/plans/per-artifact-architecture.md`` for the full design.
"""
from llm_pipeline.specs.base import ArtifactSpec
from llm_pipeline.specs.blocks import (
    CodeBodySpec,
    JsonSchemaWithRefs,
    PromptData,
    SymbolRef,
)
from llm_pipeline.specs.kinds import (
    ALL_KINDS,
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_EXTRACTION,
    KIND_PIPELINE,
    KIND_REVIEW,
    KIND_SCHEMA,
    KIND_STEP,
    KIND_TABLE,
    KIND_TOOL,
    LEVEL_BY_KIND,
)

__all__ = [
    "ALL_KINDS",
    "ArtifactSpec",
    "CodeBodySpec",
    "JsonSchemaWithRefs",
    "KIND_CONSTANT",
    "KIND_ENUM",
    "KIND_EXTRACTION",
    "KIND_PIPELINE",
    "KIND_REVIEW",
    "KIND_SCHEMA",
    "KIND_STEP",
    "KIND_TABLE",
    "KIND_TOOL",
    "LEVEL_BY_KIND",
    "PromptData",
    "SymbolRef",
]
