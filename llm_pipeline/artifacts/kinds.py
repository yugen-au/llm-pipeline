"""Kind constants for first-class artifacts.

Every editable artifact under ``llm_pipelines/`` belongs to exactly
one *kind*. Kinds are the dispatch unit on both backend (the
``app.state.registries`` index) and frontend (``COMPONENT_BY_KIND``).

This module declares ONLY the bare ``KIND_*`` string constants and
the :data:`ALL_KINDS` list. Per-kind metadata — dependency level,
subfolder name, walker, spec class, fields class — lives in
:mod:`llm_pipeline.discovery.manifest`'s :data:`KIND_MANIFESTS`,
the single source of truth. The ``LEVEL_BY_KIND`` derived view is
re-exported from :mod:`llm_pipeline.artifacts` for callers that only
need the level index.

``utilities/`` is walked at discovery for side-effects (raw-file
surfacing in the UI) but doesn't contribute a first-class kind —
it's a free-form Python escape hatch with no spec, no validation.

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
# Kept here (not in manifest) because it's a list of pure strings
# with no class deps — letting the manifest cycle-import this
# module's KIND_* constants stays clean.
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
