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

from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field

from llm_pipeline.specs.fields import parse_path
from llm_pipeline.specs.validation import ValidationIssue


__all__ = [
    "ArtifactField",
    "ArtifactRef",
    "ArtifactSpec",
    "ImportArtifact",
    "ImportBlock",
    "SymbolRef",
]


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

    # Human-readable description of this component. Populated where
    # there's a natural source — class / value docstrings on
    # :class:`ArtifactSpec` subclasses, the wrapped Pydantic class's
    # ``__doc__`` on :class:`JsonSchemaWithRefs`, the Phoenix
    # prompt description on :class:`PromptData`. Empty by default
    # for components without a natural docstring source
    # (:class:`CodeBodySpec` — docstring already lives inside the
    # body ``source``; :class:`ImportBlock` / :class:`ImportArtifact`
    # — imports don't carry docstrings).
    description: str = ""

    # Localised issues for this component. Builders that produce the
    # subclass populate this directly (libcst code-body analyser,
    # JSON schema generator, prompt resolver, etc.). Class-level
    # captures from ``source_cls._init_subclass_errors`` land here
    # too via :meth:`attach_class_captures` if their ``location.field``
    # doesn't match a sub-component field on this spec.
    issues: list[ValidationIssue] = Field(default_factory=list)

    # Lookup key for ``list[ArtifactField]`` slots. When a routing
    # path uses bracketed access on a list-typed slot
    # (``nodes[topic_extraction]``), the walker iterates the list
    # and matches the bracketed key against
    # ``getattr(item, IDENTITY_FIELD)``. Subclasses that appear
    # as list elements pin this to the field name carrying the
    # element's stable identity (``NodeBindingSpec.IDENTITY_FIELD =
    # "node_name"``, ``ArtifactRef.IDENTITY_FIELD = "name"``,
    # etc.). Defaults to ``None`` — list-as-element types that
    # don't pin it can't be routed to by key.
    IDENTITY_FIELD: ClassVar[str | None] = None

    def attach_class_captures(self, source_cls: type | None) -> Self:
        """Distribute ``source_cls._init_subclass_errors`` onto matching components.

        ``source_cls`` is allowed to be ``None`` (value-based artifact
        kinds — constants — pass ``None`` because there's no class
        carrying ``_init_subclass_errors``). The routing loop is a
        no-op in that case via the ``getattr(...,  [])`` fallback.

        Each issue's ``ValidationLocation.path`` (or legacy ``field``)
        is interpreted as a typed routing path — see
        :class:`llm_pipeline.specs.fields.FieldRef` for the
        construction surface and
        :func:`llm_pipeline.specs.fields.parse_path` for the syntax.

        Routing is **strict on structural mistakes** and permissive
        only on runtime gaps:

        - Empty path / ``None`` → ``self.issues`` (intentional top-
          level issue; naming violations etc.).
        - Walks each path segment against the current ArtifactField's
          ``model_fields``. The attribute MUST exist; the annotation
          MUST be ArtifactField-typed; bracketed access MUST match
          the container shape. Any structural mismatch raises
          :class:`RuntimeError` immediately — capture sites should
          use :class:`FieldRef` constants from a per-kind ``Fields``
          class which validate paths at class load time.
        - **Permissive only on runtime gaps**: when the runtime value
          at a structurally-valid attribute is ``None`` (slot not
          populated — e.g. ``StepSpec.inputs=None`` when the source
          class didn't declare INPUTS), or when a bracketed key
          doesn't match any element in the list / dict (the keyed
          element wasn't created — e.g. a node was filtered before
          spec construction), the walker stops at the parent and
          lands the issue there. These are real "the spec wasn't
          populated" cases, not bugs.

        Sub-component context **finer than the ArtifactField hierarchy**
        (per-variable detail, JSON Pointer into a schema, etc.) lives
        on ``ValidationLocation.subfield`` — free-form metadata the
        router ignores; the UI uses it to attach indicators at
        finer granularity than routing.

        Returns ``self`` for builder chaining::

            return StepSpec(...).attach_class_captures(cls)
        """
        for issue in getattr(source_cls, "_init_subclass_errors", []):
            path = issue.location.path or issue.location.field
            target = self if not path else _navigate_to_artifact_field(
                self, path, issue=issue,
            )
            target.issues.append(issue)
        return self


def _navigate_to_artifact_field(
    root: "ArtifactField",
    path: str,
    *,
    issue: object = None,
) -> "ArtifactField":
    """Walk ``path`` from ``root`` to the targeted :class:`ArtifactField`.

    Strict on structural mistakes — raises :class:`RuntimeError` when
    a segment names an attribute that doesn't exist on the parent's
    ArtifactField type, when the attribute isn't ArtifactField-typed,
    or when bracket usage doesn't match container shape. Capture
    sites should use :class:`FieldRef` constants from a per-kind
    ``Fields`` class so these mistakes get caught at class load time
    rather than reaching the walker.

    Permissive only on runtime gaps:

    - Slot value is ``None`` (typed for routing but not populated)
      → land on parent.
    - Bracketed key doesn't match any list element / dict entry
      → land on parent.

    The ``issue`` kwarg is the :class:`ValidationIssue` whose path
    is being walked — passed only for error-message context if the
    walk raises.
    """
    issue_code = getattr(getattr(issue, "code", None), "__str__", lambda: "?")()
    try:
        segments = parse_path(path)
    except ValueError as exc:
        raise RuntimeError(
            f"{type(root).__name__}: ValidationIssue {issue_code!r} "
            f"sets malformed path={path!r}: {exc}"
        ) from None

    current = root
    for attr, key in segments:
        # --- structural check: attribute exists on the current type
        spec_fields = type(current).model_fields
        if attr not in spec_fields:
            raise RuntimeError(
                f"{type(root).__name__}: ValidationIssue {issue_code!r} "
                f"sets path={path!r}, but {type(current).__name__} has "
                f"no field {attr!r}. Use a FieldRef constant from the "
                f"per-kind Fields class so structural mistakes get "
                f"caught at class-load time."
            )
        annotation = spec_fields[attr].annotation
        if _artifact_field_arg(annotation) is None:
            raise RuntimeError(
                f"{type(root).__name__}: ValidationIssue {issue_code!r} "
                f"sets path={path!r}, but {type(current).__name__}.{attr} "
                f"is not ArtifactField-typed (annotation: {annotation!r}). "
                f"Routing keys must point at ArtifactField sub-components; "
                f"use ``ValidationLocation.subfield`` for sub-component "
                f"context the router shouldn't descend into."
            )
        kind = _container_kind(annotation)

        # --- structural check: bracket usage matches container shape
        if key is not None and kind == "plain":
            raise RuntimeError(
                f"{type(root).__name__}: ValidationIssue {issue_code!r} "
                f"sets path={path!r}, but {type(current).__name__}.{attr} "
                f"is a single ArtifactField — don't use bracketed key "
                f"access here."
            )
        if key is None and kind in ("list", "dict"):
            raise RuntimeError(
                f"{type(root).__name__}: ValidationIssue {issue_code!r} "
                f"sets path={path!r}, but {type(current).__name__}.{attr} "
                f"is a {kind} — must use bracketed key access."
            )

        # --- runtime descent (permissive on gaps)
        next_obj = getattr(current, attr, None)
        if next_obj is None:
            # Slot typed for routing but not populated. Land on parent.
            return current
        if key is not None:
            if isinstance(next_obj, dict):
                next_obj = next_obj.get(key)
            elif isinstance(next_obj, list):
                next_obj = _lookup_in_list(next_obj, key)
            else:
                # Shouldn't happen given the structural check above,
                # but stay defensive.
                return current
            if next_obj is None:
                # Key not present in the runtime container — the
                # element wasn't created. Land on parent.
                return current
        if not isinstance(next_obj, ArtifactField):
            # Static type said ArtifactField but runtime says
            # otherwise — corrupt spec; raise loudly.
            raise RuntimeError(
                f"{type(root).__name__}: ValidationIssue {issue_code!r} "
                f"path={path!r}: descended into {type(next_obj).__name__} "
                f"which isn't an ArtifactField — internal inconsistency."
            )
        current = next_obj
    return current


def _artifact_field_arg(annotation: Any) -> "type | None":
    """Return the ArtifactField subclass inside an annotation, or ``None``.

    Walks ``Optional[X]`` / ``X | None`` / ``list[X]`` / ``dict[K, X]``.
    """
    import types as _types
    from typing import Union, get_args, get_origin

    if isinstance(annotation, type) and issubclass(annotation, ArtifactField):
        return annotation
    origin = get_origin(annotation)
    if origin is Union or origin is _types.UnionType:
        for arg in get_args(annotation):
            inner = _artifact_field_arg(arg)
            if inner is not None:
                return inner
    elif origin is list:
        args = get_args(annotation)
        if args:
            return _artifact_field_arg(args[0])
    elif origin is dict:
        args = get_args(annotation)
        if len(args) >= 2:
            return _artifact_field_arg(args[1])
    return None


def _container_kind(annotation: Any) -> str:
    """Return ``"list"`` / ``"dict"`` / ``"plain"`` for an ArtifactField slot."""
    import types as _types
    from typing import Union, get_args, get_origin

    origin = get_origin(annotation)
    if origin is Union or origin is _types.UnionType:
        for arg in get_args(annotation):
            if arg is type(None):
                continue
            kind = _container_kind(arg)
            if kind != "plain":
                return kind
        return "plain"
    if origin is list:
        return "list"
    if origin is dict:
        return "dict"
    return "plain"


def _lookup_in_list(items: list, key: str) -> "ArtifactField | None":
    """Find the first item where ``IDENTITY_FIELD`` matches ``key``."""
    for item in items:
        if not isinstance(item, ArtifactField):
            continue
        identity = type(item).IDENTITY_FIELD
        if identity is None:
            continue
        if getattr(item, identity, None) == key:
            return item
    return None


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


class ArtifactRef(ArtifactField):
    """A reference to a registered artifact by source-side name.

    Used wherever a spec field's value is a name that the
    resolver can map to a registered artifact (a step's
    ``DEFAULT_TOOLS`` entry, an extraction's ``MODEL`` slot, a
    pipeline's ``start_node``, etc.). Carries:

    - ``name``: the source-side spelling (typically the Python
      identifier or qualname as it appears in code).
    - ``ref``: the resolved :class:`SymbolRef` (kind + registry
      key) when the resolver matches; ``None`` for unresolved /
      stale / out-of-tree references.

    Inherits ``issues`` from :class:`ArtifactField` — per-reference
    problems (e.g. "table not found in registry", "tool ref
    points at the wrong kind") land here, localised to the offending
    reference rather than the parent spec's top-level issues.

    :class:`ImportArtifact` extends this with an optional ``alias``
    for ``from X import Y as Z`` shapes — the same primitive
    underneath, plus the rename slot.
    """

    # ``name`` is the lookup key when ArtifactRef appears in a
    # ``list[ArtifactRef]`` slot (``StepSpec.tools[name]``).
    IDENTITY_FIELD: ClassVar[str | None] = "name"

    # Source-side name as written. For ``table: ArtifactRef``,
    # typically the snake_case registry key (e.g. ``"topic"``);
    # for ``tools[i]: ArtifactRef``, the tool's class name or
    # registry key.
    name: str

    # Resolved registered-artifact ref. Populated when the
    # resolver returns a (kind, name) pair for ``self.name``;
    # ``None`` otherwise. Frontend cmd-click uses this to dispatch.
    ref: SymbolRef | None = None


class ImportArtifact(ArtifactRef):
    """One name brought in by an :class:`ImportBlock`.

    Extends :class:`ArtifactRef` (the ``name + ref`` core) with an
    optional ``alias`` slot for the ``from X import Y as Z`` /
    ``import X as Y`` rename shapes.

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
    """

    # Local alias if present (the ``Z`` in ``... as Z``). ``None``
    # when the imported name is used directly. Inherited
    # :attr:`name` and :attr:`ref` carry the source-side spelling
    # and resolved dispatch payload.
    alias: str | None = None


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
