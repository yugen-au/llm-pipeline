"""Kind constants and dependency levels for first-class artifacts.

Every editable artifact under ``llm_pipelines/`` belongs to exactly
one *kind*. Kinds are the dispatch unit on both backend (the
``app.state.registries`` index) and frontend (``COMPONENT_BY_KIND``).
Kinds also have a *level* that establishes the dependency tier — a
kind may reference any kind at a strictly lower level (within-level
peer references are allowed too, so long as no cycle).

``utilities/`` and ``_variables/`` are walked at discovery for
side-effects (file imports, generated-file presence) but do *not*
contribute first-class kinds:

- ``utilities/``: free-form Python escape hatch. Surfaced as raw
  files in the UI, no spec, no validation.
- ``_variables/``: generated PromptVariables files. Their data
  flows into the owning step's ``StepSpec.prompt`` (a
  ``PromptData`` building block), not into a separate registry.

See ``.claude/plans/per-artifact-architecture.md`` for the full
artifact catalogue and dependency-level rationale.
"""
from __future__ import annotations

__all__ = [
    "ALL_KINDS",
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
]


# Kind constants. Use these everywhere instead of bare strings —
# typo-on-import errors loudly, vs. typo-on-string fails silently.
KIND_CONSTANT = "constant"
KIND_ENUM = "enum"
KIND_SCHEMA = "schema"
KIND_TABLE = "table"
KIND_TOOL = "tool"
KIND_STEP = "step"
KIND_EXTRACTION = "extraction"
KIND_REVIEW = "review"
KIND_PIPELINE = "pipeline"


# Single source of truth for "is this a known kind?" and iteration.
ALL_KINDS: list[str] = [
    KIND_CONSTANT,
    KIND_ENUM,
    KIND_SCHEMA,
    KIND_TABLE,
    KIND_TOOL,
    KIND_STEP,
    KIND_EXTRACTION,
    KIND_REVIEW,
    KIND_PIPELINE,
]


# Level encodes the dependency tier. A kind at level N may reference
# kinds at levels < N (and peer-level references where no cycle).
# Used by:
#   - discovery's load order (lower levels load first)
#   - UI selectors filtering "what can I reference here?"
#   - dependency-cycle prevention at validation time
LEVEL_BY_KIND: dict[str, int] = {
    KIND_CONSTANT: 1,
    KIND_ENUM: 2,
    KIND_SCHEMA: 3,
    KIND_TABLE: 3,
    KIND_TOOL: 3,
    KIND_STEP: 4,
    KIND_EXTRACTION: 4,
    KIND_REVIEW: 4,
    KIND_PIPELINE: 5,
}
