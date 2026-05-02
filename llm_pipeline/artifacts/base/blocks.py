"""Reusable building blocks for per-kind ``ArtifactSpec`` subclasses.

These types are *not* dispatch targets — they don't appear in
``COMPONENT_BY_KIND`` and have no registry slot of their own. They
exist to be embedded inside per-kind specs as named fields and
rendered by generic frontend components (Monaco wrappers,
JsonViewer / JsonEditor, etc.).

- ``ArtifactField`` — common base for any spec sub-component that
  carries localised validation issues. Subclassed by the
  issue-bearing building blocks below.
- ``SymbolRef`` — a typed reference to another artifact. Leaf type
  (no issues field).
- ``CodeBodySpec`` — a Monaco-edited Python code body (prepare /
  run / extract / tool callable / eval scorer). Issue-bearing.
- ``JsonSchemaWithRefs`` — a JSON Schema plus per-location refs.
  Used for any Pydantic-shaped data (INPUTS, INSTRUCTIONS, OUTPUT,
  schema definitions, prompt variable definitions). Issue-bearing.

Step-specific sub-data — ``PromptData`` and
``PromptVariableDefs`` — lives in :mod:`llm_pipeline.artifacts.steps`
because it's only embedded inside ``StepSpec`` and is paired 1:1
with the step.
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


__all__ = [
    "CodeBodySpec",
    "JsonSchemaWithRefs",
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
