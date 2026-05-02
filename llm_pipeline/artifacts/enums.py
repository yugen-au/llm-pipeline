"""Enums — Python ``Enum`` subclasses.

Enums are Level 2 artifacts (may reference Level 1 constants in
their member values). The walker picks up every ``Enum`` subclass
in ``enums/foo.py`` and the builder records each member's
``(name, value)`` pair.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.base.builder import SpecBuilder
from llm_pipeline.artifacts.base.kinds import KIND_ENUM
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _to_registry_key,
)


__all__ = ["MANIFEST", "EnumBuilder", "EnumMemberSpec", "EnumSpec", "EnumsWalker"]


class EnumMemberSpec(BaseModel):
    """One member of an Enum: its identifier name and its underlying value.

    Not an :class:`ArtifactSpec` — purely sub-data of
    :class:`EnumSpec`, rendered as a row in the frontend's enum
    editor.
    """

    model_config = ConfigDict(extra="forbid")

    # Identifier as written in the source: ``Sentiment.POSITIVE`` -> "POSITIVE".
    name: str

    # The member's underlying value — the right-hand side of
    # ``POSITIVE = "pos"``. Stays as ``Any`` so str / int / float
    # / etc. enums all round-trip cleanly through JSON.
    value: Any


class EnumSpec(ArtifactSpec):
    """A Python ``Enum`` subclass declared in ``llm_pipelines/enums/``."""

    kind: Literal[KIND_ENUM] = KIND_ENUM  # type: ignore[assignment]

    # Simple type name of the member values (``str`` / ``int`` /
    # ``float`` / ...). Enums with mixed-type values default to
    # the type of the first member; truly heterogeneous enums are
    # rare and out of scope for V1.
    value_type: str

    # Member rows in declaration order.
    members: list[EnumMemberSpec]


class EnumBuilder(SpecBuilder):
    """Build an :class:`EnumSpec` from an ``Enum`` subclass."""

    SPEC_CLS = EnumSpec

    def kind_fields(self) -> dict[str, Any]:
        members = [
            EnumMemberSpec(name=member.name, value=member.value)
            for member in self.cls  # type: ignore[union-attr]
        ]
        # Pick the first member's value type as the representative;
        # empty enums (rare) default to "str".
        if members:
            first_value = next(iter(self.cls)).value  # type: ignore[arg-type]
            value_type = type(first_value).__name__
        else:
            value_type = "str"
        return {"value_type": value_type, "members": members}


class EnumsWalker(Walker):
    """Register ``Enum`` subclasses from ``enums/``."""

    BUILDER = EnumBuilder

    def qualifies(self, value, mod):
        from enum import Enum

        return _is_locally_defined_class(value, mod, Enum)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)


MANIFEST = ArtifactManifest(
    subfolder="enums",
    level=2,
    spec_cls=EnumSpec,
    fields_cls=None,
    walker=EnumsWalker(),
)
