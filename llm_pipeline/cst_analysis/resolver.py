"""Import resolution: name-in-scope -> (module_path, original_symbol).

The :class:`ImportMap` walks a parsed module's top-level imports
and produces a lookup that says, for any imported name, what
module it came from and what symbol was imported. The static
analyser uses this to resolve ``Name`` references inside function
bodies and class field declarations to artifact registry entries
(via the :data:`ResolverHook` callback).

Limitations (acceptable for V1):

- **Star imports** (``from .foo import *``) are not expanded —
  names brought in this way will not resolve. Discovered files
  shouldn't typically use star imports anyway; if they do, the
  analyser silently misses those refs.
- **Conditional imports** (under ``if TYPE_CHECKING:``,
  ``try / except ImportError``, function-scoped imports) are
  skipped — only top-level, unconditional imports populate the
  map.
- **Local-variable shadowing** of imported names is detected at
  the visitor layer (see :mod:`.visitors`), not here.
"""
from __future__ import annotations

from typing import Callable

import libcst as cst


__all__ = ["ImportMap", "ResolverHook"]


# A resolver hook decides whether a (module_path, imported_symbol)
# pair refers to a registered artifact. Returns ``(kind, name)``
# if so, ``None`` otherwise.
#
# ``module_path`` is the fully-qualified dotted module path the
# symbol was imported FROM (e.g. ``"llm_pipelines.constants.retries"``).
# ``imported_symbol`` is the original name on that module — for
# ``from x import Y as Z``, it's ``"Y"``, not the local alias.
ResolverHook = Callable[[str, str], "tuple[str, str] | None"]


class ImportMap:
    """Map from local-scope name -> (module_path, original_symbol).

    Built once per module by walking the top-level
    ``from X import Y [as Z]`` and ``import X [as Z]`` statements.
    Construction is cheap; lookups are dict-fast.
    """

    __slots__ = ("_imports",)

    def __init__(self, imports: dict[str, tuple[str, str]] | None = None) -> None:
        self._imports = imports or {}

    @classmethod
    def from_module(cls, module: cst.Module) -> "ImportMap":
        """Walk ``module``'s top-level imports; return the populated map."""
        imports: dict[str, tuple[str, str]] = {}
        for stmt in module.body:
            if not isinstance(stmt, cst.SimpleStatementLine):
                continue
            for sub in stmt.body:
                if isinstance(sub, cst.ImportFrom):
                    cls._handle_import_from(sub, imports)
                elif isinstance(sub, cst.Import):
                    cls._handle_import(sub, imports)
        return cls(imports)

    @staticmethod
    def _handle_import_from(
        node: cst.ImportFrom, imports: dict[str, tuple[str, str]],
    ) -> None:
        """``from X import Y [as Z]`` -> map[Z or Y] = (X, Y)."""
        # ``module`` is None on relative-only imports like ``from . import x``.
        # We skip those — relative resolution would need package context
        # the analyser doesn't have at this layer. Phase C can layer that
        # in if needed.
        if node.module is None:
            return
        module_path = _dotted_to_str(node.module)
        if not module_path:
            return
        if isinstance(node.names, cst.ImportStar):
            # Star imports — bail (see module docstring).
            return
        for alias in node.names:
            if not isinstance(alias, cst.ImportAlias):
                continue
            original = _name_value(alias.name)
            if original is None:
                continue
            local = _name_value(alias.asname.name) if alias.asname else original
            if local is None:
                continue
            imports[local] = (module_path, original)

    @staticmethod
    def _handle_import(
        node: cst.Import, imports: dict[str, tuple[str, str]],
    ) -> None:
        """``import X.Y [as Z]`` -> map[Z or X] = (X.Y, X.Y).

        For plain ``import X.Y``, the name brought into scope is
        ``X`` (the leftmost component) and references through
        ``X.Y.symbol`` need attribute resolution that the visitor
        handles. We record ``(module_path, original_symbol)`` as
        the full dotted path on both sides — callers can decide
        how to interpret.
        """
        for alias in node.names:
            if not isinstance(alias, cst.ImportAlias):
                continue
            full = _dotted_to_str(alias.name)
            if not full:
                continue
            if alias.asname:
                local = _name_value(alias.asname.name)
                if local is None:
                    continue
                imports[local] = (full, full)
            else:
                # ``import X.Y`` brings ``X`` into scope; resolution
                # of ``X.Y.symbol`` happens via attribute walking at
                # the visitor layer.
                head = full.split(".", 1)[0]
                imports[head] = (full, full)

    def lookup(self, name: str) -> tuple[str, str] | None:
        """Return ``(module_path, original_symbol)`` for ``name``, or ``None``."""
        return self._imports.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self._imports

    def __len__(self) -> int:
        return len(self._imports)

    def names(self) -> list[str]:
        """For introspection / tests."""
        return list(self._imports.keys())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _name_value(node: cst.CSTNode) -> str | None:
    """Return ``node.value`` if ``node`` is a :class:`cst.Name`, else ``None``."""
    if isinstance(node, cst.Name):
        return node.value
    return None


def _dotted_to_str(node: cst.CSTNode) -> str:
    """Convert a libcst dotted-name expression to a flat ``a.b.c`` string.

    Handles ``Name`` and ``Attribute`` nodes; returns the empty
    string if the shape isn't a plain dotted name (e.g. relative-
    import dot-leaders, computed expressions).
    """
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        left = _dotted_to_str(node.value)
        if not left:
            return ""
        return f"{left}.{node.attr.value}"
    return ""
