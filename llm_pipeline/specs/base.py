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

import types
from typing import Any, Self, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field

# ValidationIssue must be a runtime import (not under TYPE_CHECKING)
# because Pydantic needs the actual class to validate the ``issues``
# field. Phase C moves the validation types into ``llm_pipeline.specs``
# so this cross-package import goes away.
from llm_pipeline.graph.spec import ValidationIssue


__all__ = [
    "ArtifactField",
    "ArtifactSpec",
    "ImportArtifact",
    "ImportBlock",
    "SymbolRef",
]


def _is_artifact_field_type(annotation: Any) -> bool:
    """True if ``annotation`` declares an :class:`ArtifactField` slot.

    Walks ``Union``/``Optional`` arms — ``ArtifactField | None``,
    ``Optional[CodeBodySpec]`` etc. all qualify. Anything that
    doesn't have ``ArtifactField`` somewhere in its type tree
    (``str``, ``list[str]``, ``int | None``, etc.) returns False —
    that's the "primitive field, can't carry issues" case.

    Used by :meth:`ArtifactField.attach_class_captures` to enforce
    the routing contract: ``ValidationLocation.field`` must name a
    spec field whose annotation references ``ArtifactField``, or
    be ``None`` for top-level issues. Anything else is a broken
    constant and raises.
    """
    if isinstance(annotation, type) and issubclass(annotation, ArtifactField):
        return True
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return any(_is_artifact_field_type(arg) for arg in get_args(annotation))
    return False


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

        Each issue's ``ValidationLocation.field`` is interpreted as a
        routing key:

        - ``None`` → ``self.issues`` (intentional top-level issue;
          e.g. naming-convention violations on the artifact itself).
        - A spec field name whose annotation declares an
          :class:`ArtifactField` slot → ``getattr(self, field).issues``
          when the runtime value is populated, falling back to
          ``self.issues`` when the value is ``None`` (graceful: the
          slot is typed for routing but the artifact's source class
          hasn't populated it — common for "missing INPUTS" style
          captures).
        - Anything else (unknown field, or field annotated with a
          non-``ArtifactField`` type like ``str`` / ``list[str]``)
          → :class:`RuntimeError`. Capture sites must use a
          constant from the per-kind fields class
          (``StepFields.INPUTS`` etc.) or ``None``; mismatches are
          a broken contract and surface immediately rather than
          silently routing to top-level.

        Generic — uses Pydantic's ``model_fields`` introspection,
        no per-kind routing tables.

        Returns ``self`` for builder chaining::

            return StepSpec(...).attach_class_captures(cls)
        """
        spec_fields = type(self).model_fields
        for issue in getattr(source_cls, "_init_subclass_errors", []):
            field = issue.location.field
            if field is None:
                self.issues.append(issue)
                continue
            if field not in spec_fields:
                raise RuntimeError(
                    f"{type(self).__name__}: ValidationIssue "
                    f"{issue.code!r} sets location.field={field!r}, "
                    f"but {type(self).__name__} has no such field. "
                    f"Use a constant from the per-kind fields class "
                    f"(e.g. StepFields.INPUTS) or set field=None for "
                    f"top-level issues."
                )
            if not _is_artifact_field_type(spec_fields[field].annotation):
                raise RuntimeError(
                    f"{type(self).__name__}: ValidationIssue "
                    f"{issue.code!r} sets location.field={field!r}, "
                    f"but {type(self).__name__}.{field} is not an "
                    f"ArtifactField sub-component (annotation: "
                    f"{spec_fields[field].annotation!r}). Routing "
                    f"keys must point at ArtifactField sub-components; "
                    f"use field=None for issues about primitive fields."
                )
            target = getattr(self, field, None)
            if target is None:
                # Field is typed for routing but the runtime value
                # isn't populated (e.g. ``StepSpec.inputs=None`` when
                # the source class's ``INPUTS`` is missing). The
                # issue is ABOUT the missing slot, so top-level is
                # the right home — there's literally no sub-component
                # to attach to.
                self.issues.append(issue)
            else:
                target.issues.append(issue)
        return self


class SymbolRef(BaseModel):
    """A typed reference to another artifact.

    Used wherever the UI needs to make something clickable and
    resolvable — text positions inside Monaco code bodies, leaf
    values inside rendered schema trees, list entries on related
    artifacts, etc. The dispatch payload is always ``(kind,
    name)``; ``symbol`` is the original identifier as it appeared
    in source for display purposes.

    Position fields (``line`` / ``col_start`` / ``col_end``) only
    apply to refs inside a code-body block; for tree-shaped
    consumers (``JsonSchemaWithRefs.refs``) the addressing happens
    via the enclosing dict key (typically a JSON Pointer). The
    fields default to ``-1`` / ``0`` when not applicable.

    Lives in :mod:`llm_pipeline.specs.base` (alongside
    :class:`ImportBlock`) because :class:`ArtifactSpec` references
    it transitively via :attr:`ArtifactSpec.imports`. Per-kind
    building blocks in :mod:`llm_pipeline.specs.blocks`
    (:class:`CodeBodySpec` etc.) re-import it from here.
    """

    model_config = ConfigDict(extra="forbid")

    # Identifier as it appeared in source — what the UI shows in a
    # hover tooltip, code-lens, etc.
    symbol: str

    # Dispatch payload: ``(kind, name)`` resolves via
    # ``app.state.registries[kind][name]``.
    kind: str
    name: str

    # Position within the enclosing code body. ``-1`` means
    # "position not applicable" (used by refs that live inside
    # ``JsonSchemaWithRefs.refs`` keyed by JSON Pointer rather
    # than line/col).
    line: int = -1
    col_start: int = 0
    col_end: int = 0


class ImportArtifact(ArtifactField):
    """One name brought in by an :class:`ImportBlock`.

    Examples::

        from llm_pipeline.graph import LLMStepNode
            -> ImportArtifact(name="LLMStepNode", alias=None,
                              ref=SymbolRef(kind="...", name="..."))

        from llm_pipeline.graph import LLMStepNode as Step
            -> ImportArtifact(name="LLMStepNode", alias="Step",
                              ref=SymbolRef(...))

        import os
            -> ImportArtifact(name="os", alias=None, ref=None)

        import llm_pipeline.graph as g
            -> ImportArtifact(name="llm_pipeline.graph", alias="g",
                              ref=...)

    Inherits ``issues`` from :class:`ArtifactField` — per-name
    issues land here (e.g. "imported name doesn't resolve to a
    registered artifact in the project"). Statement-level issues
    live on the parent :class:`ImportBlock.issues`.
    """

    # The name as written on the source side of the import. For
    # ``from X import Y``, this is ``Y``. For ``import X.Y``, this
    # is the full dotted path ``X.Y``.
    name: str

    # Local alias if present (the ``Z`` in ``... as Z``). ``None``
    # when the imported name is used directly.
    alias: str | None = None

    # Registered-artifact dispatch payload — populated when
    # :data:`name` resolves via the analyser's :data:`ResolverHook`.
    # ``None`` for stdlib / third-party / not-yet-registered names.
    ref: SymbolRef | None = None


class ImportBlock(ArtifactField):
    """One import statement at the top of an artifact's source file.

    Every ``import X`` and ``from X import a, b`` statement in the
    file's import section produces one :class:`ImportBlock` —
    populated by :func:`llm_pipeline.cst_analysis.analyze_imports`,
    kept in source order on :attr:`ArtifactSpec.imports`.

    **Structured, not verbatim.** Unlike
    :class:`llm_pipeline.specs.blocks.CodeBodySpec` (which carries
    the body's exact source text for byte-equal round-trip), this
    block decomposes the import into ``module`` + ``artifacts``.
    Spec → code regenerates the statement in canonical form
    (``from X import a, b, c\\n``), normalising idiosyncratic
    formatting on the way. Pipeline files end up consistently
    formatted — one of the explicit goals of the per-artifact
    architecture.

    Lives in :mod:`llm_pipeline.specs.base` because
    :class:`ArtifactSpec` carries a ``list[ImportBlock]`` field —
    putting it in :mod:`llm_pipeline.specs.blocks` would create an
    import cycle (blocks → base → blocks).

    Inherits ``issues`` from :class:`ArtifactField` — statement-level
    issues (e.g. unresolved module path) land here; per-name
    issues land on the relevant :class:`ImportArtifact.issues`.
    """

    # The module path on the LHS of ``from X import``. ``None`` for
    # bare ``import X`` statements — in that case the imported name
    # itself carries the (possibly dotted) path on the artifact.
    module: str | None = None

    # What this statement brings into scope, in source order. Always
    # at least one entry on a valid import; an empty list signals a
    # malformed statement (analyser would surface that on
    # :attr:`issues`).
    artifacts: list[ImportArtifact] = Field(default_factory=list)

    # 0-indexed start line in the source file. Lets the UI render
    # line numbers in the imports table and lets edit ops splice
    # this statement at the right location when replacing it.
    line_offset_in_file: int = 0


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

    # Top-of-module import statements, in source order. One
    # :class:`ImportBlock` per ``Import`` / ``ImportFrom`` node —
    # populated by ``analyze_imports`` from the same source text
    # the per-kind builder uses. Per-import refs let the UI render
    # cmd-click navigation on each imported symbol; per-import
    # issues land on the offending statement (not on a section
    # list).
    imports: list[ImportBlock] = Field(default_factory=list)
