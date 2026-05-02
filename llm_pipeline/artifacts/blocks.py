"""Reusable building blocks for per-kind ``ArtifactSpec`` subclasses.

These types are *not* dispatch targets — they don't appear in
``COMPONENT_BY_KIND`` and have no registry slot of their own. They
exist to be embedded inside per-kind specs as named fields and
rendered by generic frontend components (Monaco wrappers,
JsonViewer / JsonEditor, etc.).

The set is deliberately small:

- ``ArtifactField`` — common base for any spec sub-component that
  carries localised validation issues. Subclassed by the three
  issue-bearing building blocks below. Lets per-kind specs attach
  issues at the exact field they describe without per-type
  boilerplate (every subclass inherits the ``issues`` slot).
- ``SymbolRef`` — a typed reference to another artifact. Carries
  ``(kind, name)`` for dispatch + position metadata for in-source
  highlighting. Leaf type — no issues field.
- ``CodeBodySpec`` — a Monaco-edited Python code body (prepare /
  run / extract / tool callable / eval scorer). Carries the source
  text plus the static-analysis-derived list of refs. Issue-bearing.
- ``JsonSchemaWithRefs`` — a JSON Schema plus per-location refs
  that produced its values. Used for any Pydantic-shaped data
  (INPUTS, INSTRUCTIONS, OUTPUT, prompt variable definitions, etc.).
  Issue-bearing.
- ``PromptData`` — sub-data of a step (variables + auto_vars +
  YAML-resolved templates). *Not* a first-class artifact. Embedded
  inside ``StepSpec.prompt`` and rendered via the existing
  ``PromptEditor`` component as a child of ``StepEditor``.
  Issue-bearing.

See ``.claude/plans/per-artifact-architecture.md`` (sections 4.2
and 5) for the full rationale, especially why ``PromptData`` is
embedded rather than a separate kind.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field

# ``SymbolRef`` is defined in ``base.py`` because
# :class:`llm_pipeline.artifacts.base.ImportBlock` (which lives there
# to break a base ↔ blocks cycle) carries
# ``refs: list[SymbolRef]``. Re-exported below so existing callers
# importing ``SymbolRef`` from this module keep working.
from llm_pipeline.artifacts.base import ArtifactField, SymbolRef
from llm_pipeline.artifacts.fields import FieldRef, FieldsBase


__all__ = [
    "CodeBodySpec",
    "JsonSchemaWithRefs",
    "PromptData",
    "PromptDataFields",
    "PromptVariableDefs",
    "SymbolRef",
]


class CodeBodySpec(ArtifactField):
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

    Inherits ``issues`` from :class:`ArtifactField` — body-specific
    issues (e.g. unresolved imports, syntax problems detected by
    the analyser) are populated by the libcst code-body analyser.
    """

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


class JsonSchemaWithRefs(ArtifactField):
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

    Inherits ``issues`` from :class:`ArtifactField` — schema-level
    issues (e.g. fields that couldn't be resolved to a valid JSON
    Schema, dependency cycles in $ref resolution) are populated by
    the schema generator.
    """

    # Standard JSON Schema (pydantic ``model_json_schema()``-style).
    # Typed as ``dict[str, Any]`` so we don't lock the shape to a
    # particular pydantic / JSON Schema draft.
    json_schema: dict[str, Any]

    # JSON Pointer (RFC 6901) -> the SymbolRefs whose evaluation
    # contributed to the value at that location.
    # e.g. ``{"/properties/retries/default":
    #         [SymbolRef(symbol="MAX_RETRIES", ...)]}``
    refs: dict[str, list[SymbolRef]] = Field(default_factory=dict)


class PromptVariableDefs(JsonSchemaWithRefs):
    """Unified view of a PromptVariables class's variable definitions.

    Phoenix treats a prompt's variables as one flat dict — every
    placeholder has a ``description``, an optional ``type``, and an
    optional ``auto_generate`` expression. The Python implementation
    splits them across two constructs (Pydantic fields for prepare-
    supplied values; a ``ClassVar[dict[str, str]]`` for
    auto_generate-supplied placeholders). This component is the
    Phoenix-shaped view: both kinds in one place.

    Extends :class:`JsonSchemaWithRefs` (Pydantic-fields portion +
    refs from defaults / type-hints) with the auto_vars portion
    (placeholder → expression + the refs each expression yields).
    PromptVariables-class captures (``missing_field_description``,
    ``auto_vars_*``) all live on the inherited ``issues`` slot —
    a single home for everything about the prompt's variable
    declarations.
    """

    # auto_generate expressions, keyed by placeholder name. Values
    # are source-level expressions like ``enum_names(Sentiment)``
    # which are parsed at render time to materialise concrete values.
    auto_vars: dict[str, str] = Field(default_factory=dict)

    # Per-placeholder refs derived from the auto_vars expressions —
    # e.g. the placeholder ``"sentiment_options"`` mapping to a
    # ``SymbolRef(kind=KIND_ENUM, name="sentiment", ...)``. Lets
    # the UI surface "this auto-generated placeholder depends on
    # the Sentiment enum" inline.
    auto_vars_refs: dict[str, list[SymbolRef]] = Field(default_factory=dict)


class PromptData(ArtifactField):
    """Sub-data of a step: variables + YAML-resolved templates.

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

    Inherits ``issues`` from :class:`ArtifactField`. Prompt-variable-
    class issues (auto_vars shape, missing field descriptions, etc.)
    live on ``self.variables.issues`` — :class:`PromptVariableDefs`
    is the unified home for everything about the variable
    declarations.
    """

    # Unified variable definitions — Pydantic-fields shape AND
    # auto_generate expressions in one ArtifactField. Captures from
    # PromptVariables.__pydantic_init_subclass__ route here via
    # ``PromptDataFields.VARIABLES``.
    variables: PromptVariableDefs

    # Filesystem path of the paired YAML prompt file (e.g.
    # ``llm-pipeline-prompts/sentiment_analysis.yaml``).
    yaml_path: str

    # Phoenix-resolved fields. ``None`` until the discovery-time
    # Phoenix validator runs; populated thereafter from whichever
    # source (YAML or Phoenix) wins per the existing sync rules.
    system_template: str | None = None
    user_template: str | None = None
    model: str | None = None


class PromptDataFields(FieldsBase):
    """Routing-key vocabulary for :class:`PromptData` issue captures.

    Captures from :class:`llm_pipeline.prompts.PromptVariables`
    (``missing_field_description``, ``auto_vars_*``,
    ``auto_vars_field_overlap``) describe problems with the prompt's
    variable declarations — they all route to ``PromptData.variables``
    (a :class:`PromptVariableDefs`, which is an
    :class:`ArtifactField`). The single constant here documents
    that boundary.

    Other PromptData fields are primitives (yaml_path, templates,
    model) — captures about them, if any, leave ``location.path``
    unset (or use ``None``) and land on top-level
    ``PromptData.issues``.
    """

    SPEC_CLS = PromptData

    VARIABLES = FieldRef("variables")
