"""Typed routing keys for ArtifactSpec component captures.

Capture sites (``__init_subclass__`` validators in node / pipeline /
prompt-variables base classes) tag each :class:`ValidationIssue`
with a routing path — a typed reference to the ArtifactField sub-
component the issue is about. The framework's
:meth:`ArtifactField.attach_class_captures` walker uses the path
to land the issue on the right component.

Two pieces:

- :class:`FieldRef`: a path expression. Composes via attribute
  access (``FieldRef("prompt").variables``) and key indexing
  (``FieldRef("nodes")["topic_extraction"]``). Stringifies to a
  dotted path with bracketed keys (``prompt.variables``,
  ``nodes[topic_extraction].wiring.field_sources[label]``).
- :class:`FieldsBase`: per-kind constants vocabulary base.
  Subclasses pin :attr:`SPEC_CLS` and declare each routing slot
  as a class-level :class:`FieldRef`. ``__init_subclass__``
  validates each FieldRef against the spec's ArtifactField
  hierarchy at class-load time — typos / stale slot names raise
  immediately on import rather than failing silently at routing
  time.

Dynamic paths (per-node, per-source, per-prompt-variable — keyed
by runtime values) are exposed as classmethods that return
:class:`FieldRef`. Those skip class-load validation; the classmethod
is responsible for producing a structurally correct path.
"""
from __future__ import annotations

import re
import types
from typing import Any, ClassVar, Union, get_args, get_origin


__all__ = [
    "FieldRef",
    "FieldsBase",
    "parse_path",
]


# ---------------------------------------------------------------------------
# FieldRef
# ---------------------------------------------------------------------------


class FieldRef:
    """A typed path expression to an ArtifactField slot.

    Build paths via attribute access and key indexing::

        FieldRef("prompt").variables
        # → "prompt.variables"

        FieldRef("nodes")["topic_extraction"]
        # → "nodes[topic_extraction]"

        FieldRef("nodes")["x"].wiring.field_sources["y"]
        # → "nodes[x].wiring.field_sources[y]"

    Stringifies to the path; :class:`ValidationLocation` accepts
    ``FieldRef | str`` for ``path`` (coerced via a Pydantic
    validator).
    """

    __slots__ = ("_path",)

    def __init__(self, path: str) -> None:
        self._path = path

    def __getattr__(self, name: str) -> "FieldRef":
        # Anything starting with ``_`` is suspect (Python internals
        # or our own ``_path`` slot — though that's an instance attr,
        # not routed through __getattr__). Refuse rather than silently
        # generating a path segment with a leading underscore.
        if name.startswith("_"):
            raise AttributeError(name)
        return FieldRef(f"{self._path}.{name}")

    def __getitem__(self, key: str) -> "FieldRef":
        return FieldRef(f"{self._path}[{key}]")

    def __str__(self) -> str:
        return self._path

    def __repr__(self) -> str:
        return f"FieldRef({self._path!r})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, FieldRef):
            return self._path == other._path
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._path)


# ---------------------------------------------------------------------------
# Path parsing
# ---------------------------------------------------------------------------


# A path segment is either ``attr`` (plain attribute access) or
# ``attr[key]`` (dict / identity-list lookup). The key body may
# contain anything except brackets — for runtime-keyed paths the
# key is typically a snake_case registry key or a free-form name.
_PATH_SEGMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[([^\[\]]+)\])?$")


def parse_path(path: str) -> list[tuple[str, str | None]]:
    """Parse ``"a.b[c].d"`` → ``[("a", None), ("b", "c"), ("d", None)]``.

    Each segment becomes ``(attr_name, key)`` where ``key`` is the
    bracketed lookup key (``None`` for plain attribute access).
    Raises :class:`ValueError` on malformed segments.
    """
    if not path:
        return []
    out: list[tuple[str, str | None]] = []
    for segment in path.split("."):
        match = _PATH_SEGMENT_RE.match(segment)
        if match is None:
            raise ValueError(f"malformed path segment: {segment!r} in {path!r}")
        attr, key = match.group(1), match.group(2)
        out.append((attr, key))
    return out


# ---------------------------------------------------------------------------
# FieldsBase
# ---------------------------------------------------------------------------


class FieldsBase:
    """Per-kind routing-key vocabulary base.

    Subclasses pin :attr:`SPEC_CLS` and declare each routing slot as
    a class-level :class:`FieldRef`. ``__init_subclass__`` validates
    every static FieldRef against ``SPEC_CLS`` at class-load time:

    - Each segment must address an :class:`ArtifactField` slot in
      the (nested) spec structure.
    - Bracketed segments (``foo[name]``) require the parent slot to
      be a ``dict[str, ArtifactField]`` or a ``list[ArtifactField]``
      whose element type declares ``IDENTITY_FIELD``.
    - Typos / stale slot names raise :class:`TypeError` immediately
      at import rather than failing silently at routing time.

    Dynamic paths are exposed as classmethods that return
    :class:`FieldRef`. Those skip class-load validation — the
    classmethod is responsible for producing a structurally correct
    path. (At capture time the path is well-formed; the runtime
    walker tolerates stale paths gracefully by landing on the
    deepest reachable ancestor.)
    """

    SPEC_CLS: ClassVar[type]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        spec_cls = cls.__dict__.get("SPEC_CLS")
        if spec_cls is None:
            # Intermediate base class (no SPEC_CLS pinned) — skip
            # validation. Concrete subclasses MUST pin SPEC_CLS.
            return
        for attr_name, value in vars(cls).items():
            if attr_name.startswith("_") or not isinstance(value, FieldRef):
                continue
            try:
                _validate_field_ref(spec_cls, value)
            except ValueError as exc:
                raise TypeError(
                    f"{cls.__name__}.{attr_name} = {value!r}: {exc}"
                ) from None


# ---------------------------------------------------------------------------
# Path validation against an ArtifactSpec subclass
# ---------------------------------------------------------------------------


def _artifact_field_arg(annotation: Any) -> type | None:
    """Return the :class:`ArtifactField` subclass inside an annotation, or ``None``.

    Walks ``Optional[X]`` / ``X | None`` / ``list[X]`` / ``dict[K, X]``.
    The returned class is the ArtifactField subclass at the inner
    position; the outer container shape is encoded by
    :func:`_container_kind`.
    """
    from llm_pipeline.artifacts.base import ArtifactField

    if isinstance(annotation, type) and issubclass(annotation, ArtifactField):
        return annotation
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
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
    """Return ``"list"`` / ``"dict"`` / ``"plain"`` for an ArtifactField slot.

    Used by :func:`_validate_field_ref` to decide whether a bracketed
    segment is required, allowed, or rejected.
    """
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        # Peel off ``None`` from ``X | None``; pick the first
        # container-or-plain answer from the remaining arms.
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


def _validate_field_ref(spec_cls: type, ref: FieldRef) -> None:
    """Walk a :class:`FieldRef` path against ``spec_cls``'s field structure.

    Each segment must address an :class:`ArtifactField` slot in the
    nested type. Bracketed segments require list/dict containers;
    list elements must declare ``IDENTITY_FIELD`` for the lookup
    to be meaningful. Raises :class:`ValueError` on the first
    invalid segment.
    """
    current = spec_cls
    for attr, key in parse_path(str(ref)):
        if not hasattr(current, "model_fields"):
            raise ValueError(
                f"segment {attr!r}: parent {current.__name__} is not a "
                f"Pydantic model — can't descend further"
            )
        fields = current.model_fields
        if attr not in fields:
            raise ValueError(
                f"segment {attr!r}: {current.__name__} has no field "
                f"{attr!r}"
            )
        annotation = fields[attr].annotation
        artifact_cls = _artifact_field_arg(annotation)
        if artifact_cls is None:
            raise ValueError(
                f"segment {attr!r}: {current.__name__}.{attr} is not "
                f"an ArtifactField (annotation: {annotation!r})"
            )
        kind = _container_kind(annotation)
        if key is not None:
            if kind == "plain":
                raise ValueError(
                    f"segment {attr}[{key}]: {current.__name__}.{attr} "
                    f"is a single ArtifactField, not a list/dict — "
                    f"don't use bracketed key access here"
                )
            if kind == "list" and not getattr(artifact_cls, "IDENTITY_FIELD", None):
                raise ValueError(
                    f"segment {attr}[{key}]: list element type "
                    f"{artifact_cls.__name__} has no IDENTITY_FIELD "
                    f"ClassVar — can't look up by key"
                )
        else:
            if kind == "list":
                raise ValueError(
                    f"segment {attr!r}: {current.__name__}.{attr} is "
                    f"a list — must use bracketed key access (e.g. "
                    f"{attr}[<key>])"
                )
            if kind == "dict":
                raise ValueError(
                    f"segment {attr!r}: {current.__name__}.{attr} is "
                    f"a dict — must use bracketed key access"
                )
        current = artifact_cls
