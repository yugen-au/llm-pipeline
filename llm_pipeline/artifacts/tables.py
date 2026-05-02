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

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.blocks import JsonSchemaWithRefs
from llm_pipeline.artifacts.kinds import KIND_TABLE


__all__ = ["IndexSpec", "TableSpec"]


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
