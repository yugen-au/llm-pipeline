"""``SchemaSpec`` — Pydantic ``BaseModel`` data shapes.

Schemas are Level 3 artifacts. They're shared data shapes used
across multiple artifacts (Review OUTPUT, shared INPUTS, Tool
Inputs/Args, etc.) — distinct from per-artifact INPUTS /
INSTRUCTIONS classes which live embedded in their owner.

The current ``schemas/`` folder contains both BaseModel and
SQLModel content; that split is deferred to a later phase. For now
``SchemaSpec`` covers any Pydantic-shaped class found there.
SQLModel-typed extractions (Extraction.MODEL) reference these by
name from the same registry.

The ``definition`` field carries the full
:class:`JsonSchemaWithRefs` — JSON Schema body plus per-location
SymbolRefs produced by the static analyser at spec-build time.
The frontend renders via ``JsonViewer`` / ``JsonEditor``; refs
attach to clickable values for cross-artifact navigation.

(The field is named ``definition`` rather than ``schema`` because
``schema`` shadows a Pydantic ``BaseModel`` attribute; same
reason ``JsonSchemaWithRefs.json_schema`` is named explicitly.)
"""
from __future__ import annotations

from typing import Any, Literal

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.base.blocks import JsonSchemaWithRefs
from llm_pipeline.artifacts.base.builder import SpecBuilder
from llm_pipeline.artifacts.base.kinds import KIND_SCHEMA
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.renderers import render_pydantic_class
from llm_pipeline.artifacts.base.template import ArtifactTemplate
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _to_registry_key,
)
from llm_pipeline.artifacts.base.writer import Writer


__all__ = [
    "MANIFEST",
    "SchemaBuilder",
    "SchemaSpec",
    "SchemaWriter",
    "SchemasWalker",
]


class SchemaSpec(ArtifactSpec):
    """A Pydantic data shape declared in ``llm_pipelines/schemas/``."""

    kind: Literal[KIND_SCHEMA] = KIND_SCHEMA  # type: ignore[assignment]

    # Full JSON Schema + JSON-Pointer-keyed refs sidecar. Built
    # from ``cls.model_json_schema()`` + ``analyze_class_fields``
    # at spec-build time.
    definition: JsonSchemaWithRefs


class SchemaBuilder(SpecBuilder):
    """Build a :class:`SchemaSpec` from a Pydantic ``BaseModel`` subclass."""

    SPEC_CLS = SchemaSpec

    def kind_fields(self) -> dict[str, Any]:
        # Schema generation never produces None for a valid BaseModel
        # subclass; if it does, hand back an empty placeholder.
        definition = self.json_schema(self.cls) or JsonSchemaWithRefs(
            json_schema={},
        )
        return {"definition": definition}


class SchemasWalker(Walker):
    """Register Pydantic ``BaseModel`` subclasses from ``schemas/``.

    Pure data shapes only. SQLModel-with-table classes belong in
    ``llm_pipelines/tables/`` — folder layout is the source-of-truth.
    """

    BUILDER = SchemaBuilder

    def qualifies(self, value, mod):
        from pydantic import BaseModel

        return _is_locally_defined_class(value, mod, BaseModel)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


_SCHEMA_TEMPLATE = ArtifactTemplate(template="""\
from pydantic import BaseModel


{{ pydantic_class }}
""")


class SchemaWriter(Writer):
    """Render / edit a :class:`SchemaSpec` to/from source.

    - :meth:`write` produces a fresh Pydantic-class file. Imports
      cover ``BaseModel`` only — annotations referencing other
      registered artifacts (constants, schemas) need their imports
      hand-added in V1; an import-derivation pass is a follow-up.
    - :meth:`edit` rebuilds the matching ``class X(BaseModel):``
      block via :func:`replace_class`. ``JsonSchemaWithRefs.field_source``
      preserves the user's exact annotation syntax for fields they
      didn't modify.
    """

    SPEC_CLS = SchemaSpec

    def write(self) -> str:
        return _SCHEMA_TEMPLATE.render(
            pydantic_class=self._render_class(),
        )

    def edit(self, original: str) -> str:
        import libcst as cst

        from llm_pipeline.codegen import replace_class

        module = cst.parse_module(original)
        try:
            updated = replace_class(
                module=module,
                class_name=self._class_name(),
                new_class_source=self._render_class(),
            )
        except Exception:
            return original
        return updated.code

    def _class_name(self) -> str:
        return self.spec.cls.rsplit(".", 1)[-1]

    def _render_class(self) -> str:
        return render_pydantic_class(
            name=self._class_name(),
            schema=self.spec.definition,
            base="BaseModel",
        )


MANIFEST = ArtifactManifest(
    subfolder="schemas",
    level=3,
    spec_cls=SchemaSpec,
    walker=SchemasWalker(),
)
