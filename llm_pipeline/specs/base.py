"""Foundational bases — ``ArtifactField`` and ``ArtifactSpec``.

Two-tier base hierarchy:

- :class:`ArtifactField` — anything that carries localised validation
  issues. Sub-component types (``CodeBodySpec``, ``JsonSchemaWithRefs``,
  ``PromptData``) subclass this directly. Provides the ``issues`` slot
  and the auto-routing mechanism: pass ``source_cls=<class>`` at
  construction and any ``cls._init_subclass_errors`` get distributed
  onto the matching sub-component field by ``location.field``, with
  anything unmatched landing on ``self.issues``.

- :class:`ArtifactSpec` — top-level, dispatchable artifacts. Extends
  ``ArtifactField`` with the identity fields every kind needs
  (``kind``, ``name``, ``cls``, ``source_path``). Per-kind subclasses
  (``ConstantSpec``, ``StepSpec``, ``PipelineSpec``, etc.) subclass
  this. They inherit the auto-routing from ``ArtifactField``, so
  builders just pass ``source_cls=cls`` at construction and class-level
  captures land on the right component without any per-kind table.

The auto-routing is generic — it uses Pydantic's ``model_fields``
introspection to find the target sub-component by name. New issue-
bearing component types just need to subclass ``ArtifactField`` and
match ``location.field`` to a spec field on the parent; the routing
follows automatically.

JSON round-trip safety: ``source_cls`` is a construction-only kwarg,
not a model field. ``model_dump`` doesn't emit it; ``model_validate``
doesn't see it; routing is only triggered when builders explicitly
pass it.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ValidationIssue must be a runtime import (not under TYPE_CHECKING)
# because Pydantic needs the actual class to validate the ``issues``
# field. Phase C moves the validation types into ``llm_pipeline.specs``
# so this cross-package import goes away.
from llm_pipeline.graph.spec import ValidationIssue


__all__ = ["ArtifactField", "ArtifactSpec"]


class ArtifactField(BaseModel):
    """Common base for any issue-bearing spec sub-component.

    Every per-kind spec field whose value carries localised
    validation issues is an instance of an ``ArtifactField``
    subclass — ``CodeBodySpec`` for editable code bodies,
    ``JsonSchemaWithRefs`` for Pydantic-shaped data, ``PromptData``
    for embedded prompt info, plus ``ArtifactSpec`` itself for
    top-level artifacts. Anything that needs an ``issues`` slot
    inherits from this base.

    Auto-routes ``source_cls._init_subclass_errors`` at construction
    time when ``source_cls=<class>`` is passed as a kwarg. Each
    captured issue is dispatched onto the matching ``ArtifactField``
    sub-component (by ``location.field``) when one is present;
    otherwise lands on ``self.issues``.

    Not instantiated directly. The base provides only the shared
    ``issues`` slot, the strict ``extra="forbid"`` config, and the
    routing logic.
    """

    model_config = ConfigDict(extra="forbid")

    # Localised issues for this component. Builders that produce the
    # subclass populate this directly (libcst code-body analyser,
    # JSON schema generator, prompt resolver, etc.). Class-level
    # captures from ``source_cls._init_subclass_errors`` land here
    # too if their ``location.field`` doesn't match a sub-component
    # field on this spec.
    issues: list[ValidationIssue] = Field(default_factory=list)

    def __init__(self, **data: Any) -> None:
        # ``source_cls`` is a construction-only routing kwarg. Pop it
        # before Pydantic validates so ``extra="forbid"`` doesn't
        # reject it as an unknown field.
        source_cls = data.pop("source_cls", None)
        super().__init__(**data)
        if source_cls is not None:
            self._route_class_captures(source_cls)

    def _route_class_captures(self, source_cls: type) -> None:
        """Distribute ``source_cls._init_subclass_errors`` onto matching components.

        Each issue's ``location.field`` is looked up against this
        spec's Pydantic fields. When the matching field's value is
        an ``ArtifactField`` instance, the issue lands on its
        ``issues`` list (localised to the sub-component). Otherwise
        — no field set, no matching field, value isn't an
        ``ArtifactField`` (e.g. ``None``, a primitive, a list) —
        the issue lands on ``self.issues``.

        Generic — uses Pydantic's ``model_fields`` introspection;
        no per-kind routing tables.
        """
        spec_fields = type(self).model_fields
        for issue in getattr(source_cls, "_init_subclass_errors", []):
            field = issue.location.field
            if field and field in spec_fields:
                target = getattr(self, field, None)
                if isinstance(target, ArtifactField):
                    target.issues.append(issue)
                    continue
            self.issues.append(issue)


class ArtifactSpec(ArtifactField):
    """Common contract for any UI-editable code artifact.

    Subclassed per kind. The base intentionally carries no
    kind-specific data — that lives on each subclass — but every
    artifact, regardless of kind, exposes these fields so the
    generic resolver, list endpoints, and validation surfaces work
    uniformly.

    Inherits ``issues`` and the ``source_cls`` auto-routing from
    :class:`ArtifactField`. Builders pass ``source_cls=cls`` at
    construction; class-level captures land on the right sub-
    component automatically.

    JSON-serialisable end-to-end (Pydantic v2 ``model_dump(mode="json")``)
    so the spec can travel through the API without bespoke encoders.
    """

    # Dispatch key. Per-kind subclasses pin this with ``Literal[KIND_X]``.
    kind: str

    # snake_case identifier — the key under which this artifact is
    # registered in ``app.state.registries[kind][name]``.
    name: str

    # Fully-qualified Python identifier:
    # - Class artifacts (steps, schemas, etc.): the class's
    #   ``__module__.__qualname__``.
    # - Value artifacts (constants): the module path + symbol name,
    #   e.g. ``llm_pipelines.constants.retries.MAX_RETRIES``.
    cls: str

    # Filesystem path to the source file. Used by the UI for "open
    # the file" navigation and by libcst codegen as the hot-swap
    # target.
    source_path: str
