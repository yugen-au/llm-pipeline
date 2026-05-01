"""Reusable building blocks for per-kind ``ArtifactSpec`` subclasses.

These types are *not* dispatch targets — they don't appear in
``COMPONENT_BY_KIND`` and have no registry slot of their own. They
exist to be embedded inside per-kind specs as named fields and
rendered by generic frontend components (Monaco wrappers,
JsonViewer / JsonEditor, etc.).

The set is deliberately small:

- ``SymbolRef`` — a typed reference to another artifact. Carries
  ``(kind, name)`` for dispatch + position metadata for in-source
  highlighting. Used inside code bodies (line/col) and inside JSON-
  shaped specs (the addressing scheme is the spec field's enclosing
  dict key — typically a JSON Pointer).
- ``CodeBodySpec`` — a Monaco-edited Python code body (prepare /
  run / extract / tool callable / eval scorer). Carries the source
  text plus the static-analysis-derived list of refs.
- ``JsonSchemaWithRefs`` — a JSON Schema plus per-location refs
  that produced its values. Used for any Pydantic-shaped data
  (INPUTS, INSTRUCTIONS, OUTPUT, prompt variable definitions, etc.).
- ``PromptData`` — sub-data of a step (variables + auto_vars +
  YAML-resolved templates). *Not* a first-class artifact. Embedded
  inside ``StepSpec.prompt`` and rendered via the existing
  ``PromptEditor`` component as a child of ``StepEditor``.

See ``.claude/plans/per-artifact-architecture.md`` (sections 4.2
and 5) for the full rationale, especially why ``PromptData`` is
embedded rather than a separate kind.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ValidationIssue must be imported at module level (not under
# TYPE_CHECKING) because Pydantic needs the runtime class to
# validate fields typed as ``list[ValidationIssue]``. Phase C
# moves the validation types into ``llm_pipeline.specs`` so this
# cross-package import goes away.
from llm_pipeline.graph.spec import ValidationIssue


__all__ = [
    "CodeBodySpec",
    "JsonSchemaWithRefs",
    "PromptData",
    "SymbolRef",
]


class SymbolRef(BaseModel):
    """A typed reference to another artifact.

    Used wherever the UI needs to make something clickable and
    resolvable — text positions inside Monaco code bodies, leaf
    values inside rendered schema trees, list entries on related
    artifacts, etc. The dispatch payload is always ``(kind,
    name)``; ``symbol`` is the original identifier as it appeared
    in source for display purposes.

    Position fields (``line`` / ``col_start`` / ``col_end``) only
    apply to refs inside a ``CodeBodySpec``; for tree-shaped
    consumers (``JsonSchemaWithRefs.refs``) the addressing happens
    via the enclosing dict key (typically a JSON Pointer). The
    fields default to ``-1`` / ``0`` when not applicable.
    """

    model_config = ConfigDict(extra="forbid")

    # Identifier as it appeared in source — what the UI shows in a
    # hover tooltip, code-lens, etc.
    symbol: str

    # Dispatch payload: ``(kind, name)`` resolves via
    # ``app.state.registries[kind][name]``.
    kind: str
    name: str

    # Position within the enclosing code body. ``-1`` means
    # "position not applicable" (used by refs that live inside
    # ``JsonSchemaWithRefs.refs`` keyed by JSON Pointer rather
    # than line/col).
    line: int = -1
    col_start: int = 0
    col_end: int = 0


class CodeBodySpec(BaseModel):
    """A Monaco-edited Python code body.

    Used for any function body the UI surfaces as a code editor:
    ``LLMStepNode.prepare``, ``LLMStepNode.run``,
    ``ExtractionNode.extract``, ``ReviewNode.run``, tool
    callables, eval scorer functions.

    Inside this body, every reference to another registered
    artifact (via an imported name) is captured as a ``SymbolRef``
    by the libcst static analyser at spec-build time. The frontend
    uses these to render hover previews, cmd-click navigation, and
    "find usages" behaviour without reparsing the source on the
    client.
    """

    model_config = ConfigDict(extra="forbid")

    # Raw source text the Monaco editor renders.
    source: str

    # 0-indexed line offset of ``source[0]`` within the file at
    # ``ArtifactSpec.source_path``. Lets consumers translate
    # body-local positions back into file-local positions when
    # navigating.
    line_offset_in_file: int = 0

    # Static-analysis output: every resolvable cross-artifact
    # reference inside this body, with line/col positions relative
    # to ``source``.
    refs: list[SymbolRef] = Field(default_factory=list)

    # Body-specific issues (e.g. unresolved imports, syntax
    # problems detected by the analyser).
    issues: list[ValidationIssue] = Field(default_factory=list)


class JsonSchemaWithRefs(BaseModel):
    """A JSON Schema plus per-location ``SymbolRef`` annotations.

    Used wherever a spec needs to carry Pydantic-shaped data — step
    INPUTS / INSTRUCTIONS, schema definitions, prompt variable
    definitions, table column shapes, etc. ``json_schema`` is the
    standard ``model_json_schema()`` output; ``refs`` is sidecar
    metadata keyed by JSON Pointer (RFC 6901) so JsonEditor /
    JsonViewer can render leaf values as clickable when they were
    produced by a reference to another artifact (e.g. a constant
    used as a default).

    Keeping refs as a sidecar dict (rather than embedded in the
    schema with custom ``x-`` extensions) means consumers that
    don't care about refs — pydantic itself, plain JSON Schema
    validators, OpenAPI tooling — see a clean standard schema.

    Note: the field is named ``json_schema`` (not just ``schema``)
    because ``schema`` shadows a Pydantic ``BaseModel`` attribute.
    """

    model_config = ConfigDict(extra="forbid")

    # Standard JSON Schema (pydantic ``model_json_schema()``-style).
    # Typed as ``dict[str, Any]`` so we don't lock the shape to a
    # particular pydantic / JSON Schema draft.
    json_schema: dict[str, Any]

    # JSON Pointer (RFC 6901) -> the SymbolRefs whose evaluation
    # contributed to the value at that location.
    # e.g. ``{"/properties/retries/default":
    #         [SymbolRef(symbol="MAX_RETRIES", ...)]}``
    refs: dict[str, list[SymbolRef]] = Field(default_factory=dict)

    # Schema-level issues (e.g. fields that couldn't be resolved
    # to a valid JSON Schema, dependency cycles in $ref
    # resolution).
    issues: list[ValidationIssue] = Field(default_factory=list)


class PromptData(BaseModel):
    """Sub-data of a step: variables + auto_vars + YAML-resolved templates.

    *Not* a first-class artifact. There is no ``KIND_PROMPT`` and
    no entry in ``COMPONENT_BY_KIND``. ``PromptData`` is embedded
    inside ``StepSpec.prompt`` and rendered by the existing
    ``PromptEditor`` component as a child of ``StepEditor``. This
    matches Phoenix's data model where a "prompt" *is* a step's
    LLM-call contract, not a separately-editable thing.

    The save flow when the user edits this section in
    ``StepEditor`` updates both the YAML prompt file *and*
    regenerates the paired ``_variables/_<step>.py`` (existing
    ``llm-pipeline generate`` flow).
    """

    model_config = ConfigDict(extra="forbid")

    # The PromptVariables Pydantic class shape — fields, types,
    # descriptions. Renders via JsonEditor / JsonViewer.
    variables: JsonSchemaWithRefs

    # auto_generate expressions, keyed by placeholder name. The
    # values are source-level expressions like ``enum_names(Sentiment)``
    # which are parsed at render time to materialise concrete values.
    auto_vars: dict[str, str] = Field(default_factory=dict)

    # Per-placeholder refs derived from the auto_vars expressions —
    # e.g. the placeholder ``"sentiment_options"`` mapping to a
    # ``SymbolRef(kind=KIND_ENUM, name="sentiment", ...)``. Lets
    # the UI surface "this auto-generated placeholder depends on
    # the Sentiment enum" inline.
    auto_vars_refs: dict[str, list[SymbolRef]] = Field(default_factory=dict)

    # Filesystem path of the paired YAML prompt file (e.g.
    # ``llm-pipeline-prompts/sentiment_analysis.yaml``).
    yaml_path: str

    # Phoenix-resolved fields. ``None`` until the discovery-time
    # Phoenix validator runs; populated thereafter from whichever
    # source (YAML or Phoenix) wins per the existing sync rules.
    system_template: str | None = None
    user_template: str | None = None
    model: str | None = None

    # Prompt-class-level issues (auto_vars shape errors, missing
    # field descriptions on the PromptVariables class, etc.).
    issues: list["ValidationIssue"] = Field(default_factory=list)
