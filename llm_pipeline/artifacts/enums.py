"""``EnumSpec`` — Python ``Enum`` subclasses.

Enums are Level 2 artifacts (may reference Level 1 constants in
their member values). Each ``enums/foo.py`` file may declare any
number of Enum subclasses; the discovery walker registers each as
its own :class:`EnumSpec`.

The :class:`EnumMemberSpec` rows describe each member's
``(name, value)`` pair. Consumers (auto_generate expressions,
prompt-variable rendering, frontend selectors) use these rows
directly rather than going back to the runtime ``Enum`` class.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.base.kinds import KIND_ENUM


__all__ = ["EnumMemberSpec", "EnumSpec"]


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
