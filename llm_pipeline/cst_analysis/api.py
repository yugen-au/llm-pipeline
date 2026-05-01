"""Public static-analysis API.

Two entry points, both pure functions taking a ``source`` string
and a :data:`ResolverHook` callable:

- :func:`analyze_code_body` returns a fully-populated
  :class:`CodeBodySpec` for the named function's body
  (line/col-positioned :class:`SymbolRef`s).
- :func:`analyze_class_fields` returns a
  ``{json_pointer: [SymbolRef, ...]}`` map for the named class's
  Pydantic-style field declarations.

Both raise :class:`AnalysisError` on parse failures or when the
target function/class is not found in ``source``. Targets are
identified by qualname (``"FooStep.prepare"``,
``"FooSchema"``, etc.).

The analyser does not reach into the runtime — it only inspects
``source`` plus the resolver. This means it can run before any
artifact registration takes place (Phase C wires the resolver to
the per-kind registries; Phase B uses fakes for testing).
"""
from __future__ import annotations

import libcst as cst
from libcst.metadata import MetadataWrapper

from llm_pipeline.cst_analysis.resolver import ImportMap, ResolverHook
from llm_pipeline.cst_analysis.visitors import (
    CodeBodyVisitor,
    FieldDefaultVisitor,
    FunctionLocation,
)
# Import directly from the submodule (not the package __init__) to
# avoid a circular import: ``llm_pipeline.specs.builders`` imports
# back into ``cst_analysis``.
from llm_pipeline.specs.blocks import CodeBodySpec, SymbolRef


__all__ = [
    "AnalysisError",
    "ResolverHook",
    "analyze_class_fields",
    "analyze_code_body",
]


class AnalysisError(Exception):
    """Top-level error for static-analysis failures.

    Raised on parse failures and missing targets. Visitor-internal
    issues (e.g. an import we couldn't resolve) are recorded as
    issues on the returned :class:`CodeBodySpec` rather than
    raised — analysis is permissive within a parsed file so
    partial results still flow.
    """


def analyze_code_body(
    *,
    source: str,
    function_qualname: str,
    resolver: ResolverHook,
) -> CodeBodySpec:
    """Return a populated :class:`CodeBodySpec` for the named function.

    ``function_qualname`` is dotted: ``"prepare"`` for a module-
    level function, ``"FooStep.prepare"`` for a method, with
    extra dots for nested classes.

    The returned spec's ``source`` field is the function's *body*
    text (excluding the ``def`` signature line) and
    ``line_offset_in_file`` is the 0-indexed line where the body
    starts in the original ``source`` string. ``refs`` carries
    body-local positions.

    Raises :class:`AnalysisError` if ``source`` does not parse or
    if ``function_qualname`` is not found.
    """
    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001 — uniform surface
        raise AnalysisError(f"failed to parse source: {exc}") from exc

    import_map = ImportMap.from_module(module)
    location = FunctionLocation()
    visitor = CodeBodyVisitor(
        target_qualname=function_qualname,
        import_map=import_map,
        resolver=resolver,
        location=location,
    )
    wrapper = MetadataWrapper(module)
    wrapper.visit(visitor)

    if not location.found:
        raise AnalysisError(
            f"function {function_qualname!r} not found in source"
        )

    body_source = _slice_body_source(source, location)
    return CodeBodySpec(
        source=body_source,
        # Convert from 1-indexed (libcst) to 0-indexed (our convention).
        line_offset_in_file=location.body_start_line - 1,
        refs=visitor.refs,
    )


def analyze_class_fields(
    *,
    source: str,
    class_qualname: str,
    resolver: ResolverHook,
) -> dict[str, list[SymbolRef]]:
    """Return a JSON-Pointer-keyed map of refs from the named class's fields.

    For a Pydantic-style class, walks each ``field: type = value``
    declaration and produces refs at:

    - ``/properties/<field>/$ref`` — when the type annotation
      resolves to a registered artifact.
    - ``/properties/<field>/default`` — the assigned default
      expression OR a positional first arg of ``Field(...)``.
    - ``/properties/<field>/<json_schema_key>`` — for each
      mapped Pydantic ``Field(...)`` kwarg (see
      ``PYDANTIC_KWARG_TO_JSON_SCHEMA``).

    Result is suitable for use as :class:`JsonSchemaWithRefs.refs`.

    Raises :class:`AnalysisError` if ``source`` does not parse or
    if ``class_qualname`` is not found.
    """
    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001 — uniform surface
        raise AnalysisError(f"failed to parse source: {exc}") from exc

    import_map = ImportMap.from_module(module)
    visitor = FieldDefaultVisitor(
        target_qualname=class_qualname,
        import_map=import_map,
        resolver=resolver,
    )
    module.visit(visitor)

    if not visitor.found_target:
        raise AnalysisError(
            f"class {class_qualname!r} not found in source"
        )

    return visitor.refs_by_pointer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slice_body_source(source: str, location: FunctionLocation) -> str:
    """Return the function-body text starting at ``location.body_start_line``.

    libcst position lines are 1-indexed and inclusive; we slice
    against ``str.splitlines(keepends=True)`` to preserve original
    line endings. End is also inclusive — the body's last line is
    included.
    """
    lines = source.splitlines(keepends=True)
    start = max(location.body_start_line - 1, 0)
    end = min(location.body_end_line, len(lines))
    return "".join(lines[start:end])
