"""Typed routing keys for ArtifactSpec component captures.

Capture sites (``__init_subclass__`` validators in node / pipeline /
prompt-variables base classes) tag each :class:`ValidationIssue`
with a routing path — a typed reference to the ArtifactField sub-
component the issue is about. The framework's
:meth:`ArtifactField.attach_class_captures` walker uses the path
to land the issue on the right component.

:class:`FieldRef` is a path expression. Composes via attribute
access (``FieldRef("prompt").variables``) and key indexing
(``FieldRef("nodes")["topic_extraction"]``). Stringifies to a
dotted path with bracketed keys (``prompt.variables``,
``nodes[topic_extraction].wiring.field_sources[label]``).

UPPER_CASE FieldRef constants are auto-generated as class
attributes on every :class:`ArtifactField` subclass by
:meth:`ArtifactField.__pydantic_init_subclass__` — capture sites
reference them off the spec directly (``StepSpec.INPUTS``,
``ToolSpec.ARGS``, ``PromptData.VARIABLES``).

Dynamic paths (per-node, per-source, per-prompt-variable — keyed
by runtime values) are classmethods on the spec that return
:class:`FieldRef`. Those skip class-load validation; the
classmethod is responsible for producing a structurally correct
path.
"""
from __future__ import annotations

import re
import types
from typing import Any, Union, get_args, get_origin


__all__ = [
    "FieldRef",
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
# Annotation introspection — used by ArtifactField auto-gen
# ---------------------------------------------------------------------------


def _artifact_field_arg(annotation: Any) -> type | None:
    """Return the :class:`ArtifactField` subclass inside an annotation, or ``None``.

    Walks ``Optional[X]`` / ``X | None`` / ``list[X]`` / ``dict[K, X]``.
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
