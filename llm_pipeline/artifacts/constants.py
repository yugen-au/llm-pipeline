"""``ConstantSpec`` — module-level scalar / list / dict values.

Constants are Level 1 artifacts — they have no dependencies. Each
``constants/foo.py`` file may declare any number of module-level
assignments; the discovery walker registers each non-private,
JSON-serialisable value as a separate :class:`ConstantSpec`.

Editing a constant in the UI rewrites the module-level assignment
expression via libcst codegen (Phase D-onwards). The ``value_type``
field is the simple Python type name (``"int"``, ``"str"``,
``"list"``, etc.) — not a deep type description. The frontend uses
it to decide which input control to render (text / number / table /
etc.).

The ``value`` field holds the JSON-serialisable representation
read from the loaded module. Consumers should treat it as
read-only metadata — runtime callers always go through the
registry's ``obj`` field on :class:`ArtifactRegistration`.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.kinds import KIND_CONSTANT


__all__ = ["ConstantSpec"]


class ConstantSpec(ArtifactSpec):
    """A module-level constant declared in ``llm_pipelines/constants/``."""

    kind: Literal[KIND_CONSTANT] = KIND_CONSTANT  # type: ignore[assignment]

    # Simple type name (``type(value).__name__``) — drives UI input
    # control selection. Common values: "int", "str", "float",
    # "bool", "list", "dict".
    value_type: str

    # The actual value, as it lives in the module. Must be
    # JSON-serialisable (str/int/float/bool/list/dict of those).
    # Non-serialisable values fail at API-response time, not here.
    value: Any = Field(default=None)
