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
# avoid a circular import: ``llm_pipeline.artifacts.builders`` imports
# back into ``cst_analysis``.
from llm_pipeline.artifacts.base import ImportArtifact, ImportBlock, SymbolRef
from llm_pipeline.artifacts.blocks import CodeBodySpec


__all__ = [
    "AnalysisError",
    "ResolverHook",
    "analyze_class_fields",
    "analyze_code_body",
    "analyze_imports",
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


def analyze_imports(
    *,
    source: str,
    resolver: ResolverHook,
) -> list[ImportBlock]:
    """Return one structured :class:`ImportBlock` per top-level import.

    Walks ``source``'s module body in declaration order; every
    ``import X`` and ``from X import a, b`` produces one
    :class:`ImportBlock` decomposed into ``module`` + ``artifacts``
    rather than verbatim text. Each :class:`ImportArtifact` carries
    its name, optional alias, and a :class:`SymbolRef` when the
    name resolves to a registered artifact via ``resolver``.

    Spec → code regenerates the statement in canonical form
    (``from X import a, b, c\\n``), normalising idiosyncratic
    formatting on the way — by design, so pipeline files end up
    consistently formatted.

    Skips (silent — these statements yield no :class:`ImportBlock`):

    - Star imports (``from x import *``).
    - Relative-only imports (``from . import x``) — would need
      package context the analyser doesn't have.
    - Conditional imports inside ``if TYPE_CHECKING:``, ``try``
      blocks, function bodies, etc. — only direct top-level
      module-body statements count.
    """
    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001 — uniform surface
        raise AnalysisError(f"failed to parse source: {exc}") from exc

    wrapper = MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(cst.metadata.PositionProvider)

    blocks: list[ImportBlock] = []
    for stmt in wrapper.module.body:
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        for sub in stmt.body:
            if not isinstance(sub, (cst.ImportFrom, cst.Import)):
                continue
            pos = positions.get(stmt)
            line = (pos.start.line - 1) if pos is not None else 0
            block = _build_import_block(sub, line, resolver)
            if block is not None:
                blocks.append(block)
            # one import per SimpleStatementLine in practice; the
            # rest of stmt.body would be unusual (semicolons) and
            # we treat them as not import-statements
            break
    return blocks


def _build_import_block(
    node: cst.ImportFrom | cst.Import,
    line_offset: int,
    resolver: ResolverHook,
) -> ImportBlock | None:
    """Decompose an ``Import``/``ImportFrom`` node into the structured
    :class:`ImportBlock` shape.

    Returns ``None`` for shapes the analyser deliberately skips
    (star imports, relative-only imports, malformed shapes) so the
    caller can drop them.
    """
    if isinstance(node, cst.ImportFrom):
        if node.module is None:
            return None  # relative-only `from . import x` — skip
        module_path = _dotted_to_str(node.module)
        if not module_path:
            return None
        if isinstance(node.names, cst.ImportStar):
            return None  # `from x import *` — skip
        artifacts: list[ImportArtifact] = []
        for alias in node.names:
            if not isinstance(alias, cst.ImportAlias):
                continue
            if not isinstance(alias.name, cst.Name):
                continue
            original = alias.name.value
            local_alias = (
                alias.asname.name.value
                if alias.asname and isinstance(alias.asname.name, cst.Name)
                else None
            )
            resolved = resolver(module_path, original)
            ref = (
                SymbolRef(symbol=original, kind=resolved[0], name=resolved[1])
                if resolved is not None else None
            )
            artifacts.append(ImportArtifact(
                name=original, alias=local_alias, ref=ref,
            ))
        return ImportBlock(
            module=module_path,
            artifacts=artifacts,
            line_offset_in_file=line_offset,
        )

    # ``import X[.Y][.Z] [as W]``: bare-import style — module=None;
    # each alias becomes one ImportArtifact carrying the full
    # dotted path as its name.
    artifacts = []
    for alias in node.names:
        if not isinstance(alias, cst.ImportAlias):
            continue
        full = _dotted_to_str(alias.name)
        if not full:
            continue
        local_alias = (
            alias.asname.name.value
            if alias.asname and isinstance(alias.asname.name, cst.Name)
            else None
        )
        resolved = resolver(full, full)
        ref = (
            SymbolRef(symbol=full, kind=resolved[0], name=resolved[1])
            if resolved is not None else None
        )
        artifacts.append(ImportArtifact(
            name=full, alias=local_alias, ref=ref,
        ))
    if not artifacts:
        return None
    return ImportBlock(
        module=None,
        artifacts=artifacts,
        line_offset_in_file=line_offset,
    )


def _dotted_to_str(node: cst.CSTNode) -> str:
    """Convert a libcst dotted-name expression to a flat ``a.b.c`` string."""
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        left = _dotted_to_str(node.value)
        if not left:
            return ""
        return f"{left}.{node.attr.value}"
    return ""


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
