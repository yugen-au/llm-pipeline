"""Constants — module-level scalar / list / dict values.

Constants are Level 1 artifacts — they have no dependencies. Each
``constants/foo.py`` file declares one or more :class:`Constant`
subclasses with a ``value`` ClassVar. The walker picks them up,
the builder reads ``cls.value``, and the spec carries the simple
type name + JSON-serialisable value.

Editing a constant in the UI rewrites the module-level class
declaration via libcst codegen.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from llm_pipeline.artifacts.base import ArtifactSpec
from llm_pipeline.artifacts.base.builder import SpecBuilder
from llm_pipeline.artifacts.base.kinds import KIND_CONSTANT
from llm_pipeline.artifacts.base.manifest import ArtifactManifest
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _to_registry_key,
)


__all__ = ["MANIFEST", "ConstantBuilder", "ConstantSpec", "ConstantsWalker"]


class ConstantSpec(ArtifactSpec):
    """A module-level constant declared in ``llm_pipelines/constants/``."""

    kind: Literal[KIND_CONSTANT] = KIND_CONSTANT  # type: ignore[assignment]

    # Simple type name (``type(value).__name__``) — drives UI input
    # control selection. Common values: "int", "str", "float",
    # "bool", "list", "dict".
    value_type: str

    # JSON-serialisable representation read from the loaded module.
    value: Any = Field(default=None)


class ConstantBuilder(SpecBuilder):
    """Build a :class:`ConstantSpec` from a :class:`Constant` subclass."""

    SPEC_CLS = ConstantSpec

    def kind_fields(self) -> dict[str, Any]:
        value = self.cls.value  # type: ignore[union-attr]
        return {
            "value_type": type(value).__name__,
            "value": value,
        }


class ConstantsWalker(Walker):
    """Register :class:`Constant` subclasses from ``constants/``."""

    BUILDER = ConstantBuilder

    def qualifies(self, value, mod):
        from llm_pipeline.constants import Constant

        return _is_locally_defined_class(value, mod, Constant)

    def name_for(self, attr_name, value):
        return _to_registry_key(attr_name)


MANIFEST = ArtifactManifest(
    subfolder="constants",
    level=1,
    spec_cls=ConstantSpec,
    fields_cls=None,
    walker=ConstantsWalker(),
)
