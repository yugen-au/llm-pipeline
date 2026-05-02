"""``TableSpec`` — SQLModel-with-table=True persistent tables.

Tables are Level 3 artifacts (peer to schemas, tools,
prompt-variables). They differ from :class:`SchemaSpec` in that
they describe a *persistent* DB-backed shape — the discovery
walker classifies a SQLModel subclass as a table iff
``__table__`` is set (which SQLModel does only when
``table=True``).

Phase C.2.b TableSpec carries the spec-level info that's
extractable from the class without touching the database engine:

- ``definition`` — the JSON Schema + cross-artifact refs (same
  as :class:`SchemaSpec.definition`)
- ``table_name`` — ``cls.__tablename__``
- ``indices`` — column-list + unique flag for each declared index

Deferred for follow-up phases:
- Foreign-key relationships (need cross-table refs)
- Live engine binding / migration ops (DB-touching)
- Primary-key column callout (currently derivable from the JSON
  schema's required fields + SQLModel field metadata; add when
  the UI needs it explicitly)
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.base.blocks import JsonSchemaWithRefs
from llm_pipeline.artifacts.base.builder import SpecBuilder
from llm_pipeline.artifacts.base.kinds import KIND_TABLE
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.renderers import render_pydantic_class
from llm_pipeline.artifacts.base.template import ArtifactTemplate
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _is_table,
    _to_registry_key,
)
from llm_pipeline.artifacts.base.writer import Writer


__all__ = [
    "MANIFEST",
    "IndexSpec",
    "TableBuilder",
    "TableSpec",
    "TableWriter",
    "TablesWalker",
]


class IndexSpec(BaseModel):
    """One index declared on a SQLModel table.

    Captures what the frontend's TableEditor needs to render an
    index row: name, the columns covered, whether the index is
    unique. Not an :class:`ArtifactSpec` — sub-data of
    :class:`TableSpec`.
    """

    model_config = ConfigDict(extra="forbid")

    # SQLAlchemy auto-generates an index name (e.g.
    # ``ix_table_column``) when the user doesn't pin one. Empty
    # string is allowed but unusual.
    name: str

    # Columns covered by the index, in declaration order.
    columns: list[str]

    # Whether the index enforces uniqueness across the column set.
    unique: bool = False


class TableSpec(ArtifactSpec):
    """A SQLModel-with-table=True class declared in ``schemas/`` (or ``tables/``).

    The schemas/tables folder split is a separate planned phase;
    until it lands, both ``schemas/`` and ``tables/`` (when
    present) are walked and SQLModel-with-table classes are
    routed here regardless of source folder.
    """

    kind: Literal[KIND_TABLE] = KIND_TABLE  # type: ignore[assignment]

    # JSON Schema + per-location SymbolRefs. Built via the same
    # path as :class:`SchemaSpec.definition`.
    definition: JsonSchemaWithRefs

    # Database-side table name (``cls.__tablename__``).
    table_name: str

    # Declared indices in source order. Empty when the class has
    # only the implicit primary-key index.
    indices: list[IndexSpec] = Field(default_factory=list)


class TableBuilder(SpecBuilder):
    """Build a :class:`TableSpec` from a SQLModel-with-``table=True`` class.

    Reads ``__tablename__`` and ``__table__.indexes`` from the class
    — no DB engine required.
    """

    SPEC_CLS = TableSpec

    def kind_fields(self) -> dict[str, Any]:
        definition = self.json_schema(self.cls) or JsonSchemaWithRefs(
            json_schema={},
        )

        table_name = getattr(self.cls, "__tablename__", "") or ""

        indices: list[IndexSpec] = []
        table = getattr(self.cls, "__table__", None)
        if table is not None:
            for idx in getattr(table, "indexes", []) or []:
                try:
                    columns = [c.name for c in idx.columns]
                except Exception:  # noqa: BLE001 — defensive against odd backends
                    columns = []
                indices.append(IndexSpec(
                    name=getattr(idx, "name", "") or "",
                    columns=columns,
                    unique=bool(getattr(idx, "unique", False)),
                ))

        return {
            "definition": definition,
            "table_name": table_name,
            "indices": indices,
        }


class TablesWalker(Walker):
    """Register SQLModel-with-``table=True`` classes from ``tables/``.

    The ``__table__`` presence check is a defensive filter — only
    classes SQLModel marks as real tables get registered.
    """

    BUILDER = TableBuilder

    def qualifies(self, value, mod):
        from pydantic import BaseModel

        return (
            _is_locally_defined_class(value, mod, BaseModel)
            and _is_table(value)
        )

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


_TABLE_TEMPLATE = ArtifactTemplate(template="""\
from sqlmodel import SQLModel


{{ pydantic_class }}
""")


class TableWriter(Writer):
    """Render / edit a :class:`TableSpec` to/from source.

    - :meth:`write` produces a fresh ``SQLModel(..., table=True)``
      file. Imports are minimal (just ``SQLModel``); annotations
      referencing other artifacts need their imports hand-added in
      V1.
    - :meth:`edit` rebuilds the matching ``class X(SQLModel,
      table=True):`` block via :func:`replace_class`.

    Index declarations (``__table_args__``) are tracked on the spec
    but **not yet emitted by the writer** in V1 — round-tripping
    SQLAlchemy ``Index(...)`` constructs needs more design work
    around constraint-name preservation. Existing indexes on the
    source class survive edits because :func:`replace_class` only
    swaps the ``ClassDef`` body, not module-level scaffolding.
    """

    SPEC_CLS = TableSpec

    def write(self) -> str:
        return _TABLE_TEMPLATE.render(
            pydantic_class=self._render_class_with_tablename(),
        )

    def edit(self, original: str) -> str:
        import libcst as cst

        from llm_pipeline.codegen import replace_class

        module = cst.parse_module(original)
        try:
            updated = replace_class(
                module=module,
                class_name=self._class_name(),
                new_class_source=self._render_class_with_tablename(),
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
            base="SQLModel",
            class_kwargs="table=True",
        )

    def _render_class_with_tablename(self) -> str:
        """Add ``__tablename__`` line to the rendered class body."""
        rendered = self._render_class()
        if self.spec.table_name:
            rendered += f"\n    __tablename__ = {self.spec.table_name!r}"
        return rendered


MANIFEST = ArtifactManifest(
    subfolder="tables",
    level=3,
    spec_cls=TableSpec,
    walker=TablesWalker(),
)
