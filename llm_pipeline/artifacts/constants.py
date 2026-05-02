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
from llm_pipeline.artifacts.base.template import ArtifactTemplate
from llm_pipeline.artifacts.base.walker import (
    Walker,
    _is_locally_defined_class,
    _to_registry_key,
)
from llm_pipeline.artifacts.base.writer import Writer


__all__ = [
    "MANIFEST",
    "ConstantBuilder",
    "ConstantSpec",
    "ConstantWriter",
    "ConstantsWalker",
]


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


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------


_CONSTANT_TEMPLATE = ArtifactTemplate(template="""\
from llm_pipeline.constants import Constant


class {{ class_name }}(Constant):
    value = {{ value_literal }}
""")


class ConstantWriter(Writer):
    """Render / edit a :class:`ConstantSpec` to/from source.

    - :meth:`write` produces a fresh single-class file.
    - :meth:`edit` finds the matching ``class X(Constant):`` block in
      the existing source and replaces its ``value = ...`` line.

    Multi-constant files (more than one ``Constant`` subclass per
    file) are supported on the edit path — each spec only touches
    its own class. ``write`` always produces a single-class file;
    callers building multi-constant files should ``write`` the first
    spec then ``edit`` subsequent specs into the resulting source.
    """

    SPEC_CLS = ConstantSpec

    def write(self) -> str:
        return _CONSTANT_TEMPLATE.render(
            class_name=self._class_name(),
            value_literal=repr(self.spec.value),
        )

    def edit(self, original: str) -> str:
        import libcst as cst

        class_name = self._class_name()
        new_value_literal = repr(self.spec.value)

        class _Replacer(cst.CSTTransformer):
            def leave_ClassDef(self, _original, updated):
                if updated.name.value != class_name:
                    return updated
                return _replace_value_assignment(updated, new_value_literal)

        module = cst.parse_module(original)
        return module.visit(_Replacer()).code

    def _class_name(self) -> str:
        """Source-side class name from the spec's qualname."""
        return self.spec.cls.rsplit(".", 1)[-1]


def _replace_value_assignment(class_def, new_value_literal: str):
    """Replace ``value = ...`` (or ``value: T = ...``) inside a ClassDef body.

    Returns the updated :class:`cst.ClassDef`. Appends a fresh
    ``value = <literal>`` line when no existing assignment is found
    (covers the ``class X: pass`` shape).
    """
    import libcst as cst

    body = class_def.body
    if not isinstance(body, cst.IndentedBlock):
        return class_def

    found = False
    new_inner: list = []
    for inner in body.body:
        if isinstance(inner, cst.SimpleStatementLine):
            new_subs: list = []
            for sub in inner.body:
                if isinstance(sub, cst.Assign):
                    if (
                        len(sub.targets) == 1
                        and isinstance(sub.targets[0].target, cst.Name)
                        and sub.targets[0].target.value == "value"
                    ):
                        sub = sub.with_changes(
                            value=cst.parse_expression(new_value_literal),
                        )
                        found = True
                elif isinstance(sub, cst.AnnAssign):
                    if (
                        isinstance(sub.target, cst.Name)
                        and sub.target.value == "value"
                        and sub.value is not None
                    ):
                        sub = sub.with_changes(
                            value=cst.parse_expression(new_value_literal),
                        )
                        found = True
                new_subs.append(sub)
            inner = inner.with_changes(body=new_subs)
        new_inner.append(inner)

    if not found:
        new_inner.append(cst.SimpleStatementLine(body=[
            cst.Assign(
                targets=[cst.AssignTarget(target=cst.Name("value"))],
                value=cst.parse_expression(new_value_literal),
            )
        ]))

    return class_def.with_changes(body=body.with_changes(body=new_inner))


MANIFEST = ArtifactManifest(
    subfolder="constants",
    level=1,
    spec_cls=ConstantSpec,
    walker=ConstantsWalker(),
)
