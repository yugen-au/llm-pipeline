"""Resolver-hook factory for cross-artifact reference resolution.

The static analyser (:mod:`llm_pipeline.cst_analysis`) emits a
``SymbolRef`` whenever an import-resolved name in a code body or
class-field expression matches a *registered* artifact. The
matching is driven by a :data:`ResolverHook` callable that says,
for ``(module_path, imported_symbol)`` pairs:

    "Is this a known artifact? If so, what is its (kind, name)?"

This module wires that callable up against the per-kind
:class:`ArtifactRegistration` registries on ``app.state.registries``.
The reverse index is rebuilt on each :func:`make_resolver` call,
so callers using the two-pass discovery pattern (Phase C.2.b)
just call ``make_resolver(registries)`` again after pass 1 to
get a resolver that knows the full set.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from llm_pipeline.cst_analysis import ResolverHook

if TYPE_CHECKING:
    from llm_pipeline.artifacts import ArtifactRegistration


__all__ = ["make_resolver"]


def make_resolver(
    registries: dict[str, dict[str, "ArtifactRegistration"]],
) -> ResolverHook:
    """Build a :data:`ResolverHook` closured over ``registries``.

    Internally builds a reverse index ``cls_qualname -> (kind, name)``
    so each lookup is dict-fast (a per-call linear scan over all
    registries would otherwise be O(N*M) and the resolver is hit
    once per imported symbol per file at discovery time).

    The index is captured at call time — mutations to ``registries``
    after this returns are NOT reflected. Callers using the two-
    pass discovery pattern call :func:`make_resolver` once before
    each pass.
    """
    # Reverse index: fully-qualified Python identifier
    # ("module.path.SYMBOL") -> (kind, name).
    index: dict[str, tuple[str, str]] = {}
    for kind, kind_registrations in registries.items():
        for artifact_name, registration in kind_registrations.items():
            index[registration.spec.cls] = (kind, artifact_name)

    def resolver(module_path: str, imported_symbol: str) -> tuple[str, str] | None:
        # ``module_path`` is the dotted source of the import
        # (``"llm_pipelines.constants.retries"``). ``imported_symbol``
        # is the original symbol on that module
        # (``"MAX_RETRIES"`` — already de-aliased by ImportMap).
        # The registered ``spec.cls`` is the same flat dotted form,
        # so we just concat and look up.
        return index.get(f"{module_path}.{imported_symbol}")

    return resolver
