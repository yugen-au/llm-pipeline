"""Foundational bases — ``ArtifactField`` and ``ArtifactSpec``.

Two-tier base hierarchy:

- :class:`ArtifactField` — anything that carries localised validation
  issues. Sub-component types (``CodeBodySpec``, ``JsonSchemaWithRefs``,
  ``PromptData``) subclass this directly. Provides the ``issues`` slot
  and the :meth:`attach_class_captures` routing method.

- :class:`ArtifactSpec` — top-level, dispatchable artifacts. Extends
  ``ArtifactField`` with the identity fields every kind needs
  (``kind``, ``name``, ``cls``, ``source_path``). Per-kind subclasses
  (``ConstantSpec``, ``StepSpec``, ``PipelineSpec``, etc.) subclass
  this.

Capture routing is opt-in and explicit — builders construct the spec,
then call :meth:`attach_class_captures` on it. The router uses
Pydantic's ``model_fields`` introspection to route each captured
issue onto the matching ``ArtifactField`` sub-component (by
``location.field``), with anything unmatched falling back to
``self.issues``.

The routing keys (the values that capture sites set as
``ValidationLocation.field``) are declared as constants on per-kind
"fields" classes — :class:`llm_pipeline.specs.steps.StepFields`,
:class:`llm_pipeline.specs.extractions.ExtractionFields`, etc. —
so capture sites import a typed constant (``StepFields.INPUTS``)
instead of writing a bare string. Typos become ``AttributeError``
at class-load time rather than silent fall-throughs at runtime.

JSON round-trip safety: routing is a runtime call on a method, not
hidden in ``__init__``. ``model_dump``/``model_validate`` don't
trigger routing.
"""
from __future__ import annotations

from typing import Self

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

    Capture routing happens via :meth:`attach_class_captures` —
    builders construct the spec, then invoke the method to
    distribute ``cls._init_subclass_errors`` onto the right
    sub-components. Routing is explicit (not in ``__init__``), so
    JSON round-trip stays clean and the call site documents itself.

    Not instantiated directly. The base provides only the shared
    ``issues`` slot, the strict ``extra="forbid"`` config, and the
    routing method.
    """

    model_config = ConfigDict(extra="forbid")

    # Localised issues for this component. Builders that produce the
    # subclass populate this directly (libcst code-body analyser,
    # JSON schema generator, prompt resolver, etc.). Class-level
    # captures from ``source_cls._init_subclass_errors`` land here
    # too via :meth:`attach_class_captures` if their ``location.field``
    # doesn't match a sub-component field on this spec.
    issues: list[ValidationIssue] = Field(default_factory=list)

    def attach_class_captures(self, source_cls: type) -> Self:
        """Distribute ``source_cls._init_subclass_errors`` onto matching components.

        Each issue's ``location.field`` is looked up against this
        spec's Pydantic fields. When the matching field's value is
        an :class:`ArtifactField` instance, the issue lands on its
        ``issues`` list (localised to the sub-component). Otherwise
        — no field set, no matching field, value isn't an
        :class:`ArtifactField` (e.g. ``None``, a primitive, a list)
        — the issue lands on ``self.issues``.

        Generic — uses Pydantic's ``model_fields`` introspection; no
        per-kind routing tables. Capture sites set
        ``ValidationLocation.field`` to a constant from the per-kind
        fields class (``StepFields.INPUTS`` etc.); the router
        validates by lookup, not by string equality, so any typo
        falls back to top-level instead of silently dropping.

        Returns ``self`` for builder chaining::

            return StepSpec(...).attach_class_captures(cls)
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
        return self


class ArtifactSpec(ArtifactField):
    """Common contract for any UI-editable code artifact.

    Subclassed per kind. The base intentionally carries no
    kind-specific data — that lives on each subclass — but every
    artifact, regardless of kind, exposes these fields so the
    generic resolver, list endpoints, and validation surfaces work
    uniformly.

    Inherits ``issues`` and the :meth:`ArtifactField.attach_class_captures`
    routing method. Builders construct the spec then call the
    method to attach class-level captures.

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
