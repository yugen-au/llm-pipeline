"""CSTVisitor subclasses for the static analyser.

Two visitors:

- :class:`CodeBodyVisitor` — walks a module, locates a named
  function, emits :class:`SymbolRef` for every cross-artifact name
  reference inside that function's body.
- :class:`FieldDefaultVisitor` — walks a module, locates a named
  class, emits ``{json_pointer: [SymbolRef, ...]}`` for every
  cross-artifact ref inside Pydantic-style field declarations
  (type annotations + default expressions + ``Field(...)`` kwarg
  expressions).

Both rely on :class:`.resolver.ImportMap` for imported-name
lookup and a :data:`.api.ResolverHook` callable for the
"is this an artifact?" decision. Limitations are documented in
the module docstring of :mod:`.resolver`.
"""
from __future__ import annotations

from typing import Iterable

import libcst as cst
from libcst.metadata import PositionProvider

from llm_pipeline.cst_analysis.resolver import ImportMap, ResolverHook
# Import directly from the submodule (not the package __init__) to
# avoid a circular import: ``llm_pipeline.artifacts.builders`` imports
# back into ``cst_analysis``.
from llm_pipeline.artifacts.blocks import SymbolRef


__all__ = [
    "CodeBodyVisitor",
    "FieldDefaultVisitor",
    "FunctionLocation",
    "PYDANTIC_KWARG_TO_JSON_SCHEMA",
]


# Pydantic ``Field(...)`` kwargs that map to standard JSON Schema
# properties. Used by :class:`FieldDefaultVisitor` to assign each
# kwarg's expression a JSON Pointer location.
PYDANTIC_KWARG_TO_JSON_SCHEMA: dict[str, str] = {
    "default": "default",
    "description": "description",
    "examples": "examples",
    "title": "title",
    "le": "maximum",
    "lt": "exclusiveMaximum",
    "ge": "minimum",
    "gt": "exclusiveMinimum",
    "min_length": "minLength",
    "max_length": "maxLength",
    "min_items": "minItems",
    "max_items": "maxItems",
    "pattern": "pattern",
    "multiple_of": "multipleOf",
}


class FunctionLocation:
    """Captures where a target function lives in the file.

    Populated by :class:`CodeBodyVisitor` while walking; consumed
    by :func:`.api.analyze_code_body` to translate body-local
    positions and slice the body source text.
    """

    __slots__ = ("body_start_line", "body_end_line", "found")

    def __init__(self) -> None:
        # 1-indexed file lines per libcst ``PositionProvider``.
        self.body_start_line: int = 0
        self.body_end_line: int = 0
        # Whether the visitor located the target during the walk.
        self.found: bool = False


class CodeBodyVisitor(cst.CSTVisitor):
    """Emit :class:`SymbolRef`s from inside a named function's body.

    Match strategy: track the qualname stack as we descend into
    classes/functions. When we enter a ``FunctionDef`` whose
    qualname matches ``target_qualname``, set "inside target" and
    process every ``Name`` until we leave that ``FunctionDef``.

    Position output: line/col positions are emitted body-local
    (i.e. relative to the first line of the function body, 0-
    indexed). The ``location.body_start_line`` field captures the
    body's file-local start line so callers can populate
    ``CodeBodySpec.line_offset_in_file``.

    Limitation: does not detect local-variable shadowing of
    imports. A ``MAX_RETRIES = 5`` inside the function body will
    NOT prevent emitting a SymbolRef for an outer
    ``from .constants import MAX_RETRIES`` reference. Treat as
    acceptable for V1 — shadowing imports is unusual user code,
    and adding ScopeProvider is a follow-up if it bites.
    """

    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(
        self,
        target_qualname: str,
        import_map: ImportMap,
        resolver: ResolverHook,
        location: FunctionLocation,
    ) -> None:
        super().__init__()
        self._target = target_qualname
        self._imports = import_map
        self._resolver = resolver
        self._location = location
        self._refs: list[SymbolRef] = []
        self._qualname_stack: list[str] = []
        # Depth counter so we don't process names in nested
        # functions when the target is the outer function.
        self._inside_target_depth = 0

    @property
    def refs(self) -> list[SymbolRef]:
        return self._refs

    # -- qualname tracking ------------------------------------------------

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self._qualname_stack.append(node.name.value)

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self._qualname_stack.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        self._qualname_stack.append(node.name.value)
        if self._is_target():
            self._inside_target_depth += 1
            if not self._location.found:
                pos = self.get_metadata(PositionProvider, node.body)
                self._location.body_start_line = pos.start.line
                self._location.body_end_line = pos.end.line
                self._location.found = True

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        if self._is_target():
            self._inside_target_depth -= 1
        self._qualname_stack.pop()

    def _is_target(self) -> bool:
        return ".".join(self._qualname_stack) == self._target

    # -- name resolution --------------------------------------------------

    def visit_Name(self, node: cst.Name) -> None:
        if self._inside_target_depth <= 0:
            return
        ref = self._resolve(node)
        if ref is not None:
            self._refs.append(ref)

    def _resolve(self, node: cst.Name) -> SymbolRef | None:
        info = self._imports.lookup(node.value)
        if info is None:
            return None
        module_path, imported_symbol = info
        result = self._resolver(module_path, imported_symbol)
        if result is None:
            return None
        kind, ref_name = result
        try:
            pos = self.get_metadata(PositionProvider, node)
        except KeyError:
            return None
        # PositionProvider lines are 1-indexed and file-local.
        # SymbolRef.line is body-local 0-indexed.
        body_start = self._location.body_start_line or 1
        line = pos.start.line - body_start
        return SymbolRef(
            symbol=node.value,
            kind=kind,
            name=ref_name,
            line=line,
            col_start=pos.start.column,
            col_end=pos.end.column,
        )


class FieldDefaultVisitor(cst.CSTVisitor):
    """Emit ``{json_pointer: [SymbolRef, ...]}`` for a named class's fields.

    Walks every ``AnnAssign`` (``field: type = value``) in the
    target class body and produces refs at three categories of
    JSON Pointer:

    - ``/properties/<field>/$ref`` — when the type annotation
      resolves to a registered artifact (e.g. ``field: Sentiment``).
    - ``/properties/<field>/default`` — the assigned value, OR a
      positional ``Field(default_arg, ...)`` first arg.
    - ``/properties/<field>/<json_schema_key>`` — for each
      Pydantic ``Field(...)`` kwarg in
      :data:`PYDANTIC_KWARG_TO_JSON_SCHEMA`.

    Refs inside complex expressions (e.g. ``MAX_RETRIES * 2``) all
    register at the enclosing JSON Pointer — the consumer can
    treat the field's value as "depends on these symbols" without
    needing to evaluate the expression.

    Position fields on emitted SymbolRefs are left at the default
    "not applicable" sentinel (``line=-1``, ``col_start=col_end=0``)
    since JSON-Pointer addressing is the primary key.
    """

    METADATA_DEPENDENCIES = ()

    def __init__(
        self,
        target_qualname: str,
        import_map: ImportMap,
        resolver: ResolverHook,
    ) -> None:
        super().__init__()
        self._target = target_qualname
        self._imports = import_map
        self._resolver = resolver
        self._refs_by_pointer: dict[str, list[SymbolRef]] = {}
        self._qualname_stack: list[str] = []
        self._found_target = False

    @property
    def refs_by_pointer(self) -> dict[str, list[SymbolRef]]:
        return self._refs_by_pointer

    @property
    def found_target(self) -> bool:
        return self._found_target

    # -- qualname tracking ------------------------------------------------

    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        self._qualname_stack.append(node.name.value)
        if ".".join(self._qualname_stack) == self._target:
            self._found_target = True
            self._scan_class_body(node)

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        self._qualname_stack.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        # Track functions on the qualname stack only so nested
        # classes inside methods are addressable correctly.
        self._qualname_stack.append(node.name.value)

    def leave_FunctionDef(self, original_node: cst.FunctionDef) -> None:
        self._qualname_stack.pop()

    # -- field walking ----------------------------------------------------

    def _scan_class_body(self, class_node: cst.ClassDef) -> None:
        body = class_node.body
        if not isinstance(body, cst.IndentedBlock):
            return
        for stmt in body.body:
            if not isinstance(stmt, cst.SimpleStatementLine):
                continue
            for sub in stmt.body:
                if isinstance(sub, cst.AnnAssign):
                    self._scan_annotated_assignment(sub)

    def _scan_annotated_assignment(self, node: cst.AnnAssign) -> None:
        if not isinstance(node.target, cst.Name):
            return  # Pydantic fields are simple ``name: type = ...``
        field_name = node.target.value

        # 1. Type annotation -> $ref
        for ref in self._collect_refs(node.annotation.annotation):
            self._add_ref(f"/properties/{field_name}/$ref", ref)

        # 2. RHS value -> /default OR Field(...) decomposition
        if node.value is None:
            return
        if self._is_field_call(node.value):
            self._scan_field_call(field_name, node.value)
        else:
            for ref in self._collect_refs(node.value):
                self._add_ref(f"/properties/{field_name}/default", ref)

    def _is_field_call(self, node: cst.BaseExpression) -> bool:
        return (
            isinstance(node, cst.Call)
            and isinstance(node.func, cst.Name)
            and node.func.value == "Field"
        )

    def _scan_field_call(
        self, field_name: str, call: cst.BaseExpression,
    ) -> None:
        # ``call`` is guaranteed to be a Call to ``Field`` here.
        assert isinstance(call, cst.Call)

        positional_seen = 0
        for arg in call.args:
            if arg.keyword is None:
                # First positional arg is the default value (per
                # Pydantic's Field signature).
                if positional_seen == 0:
                    pointer = f"/properties/{field_name}/default"
                    for ref in self._collect_refs(arg.value):
                        self._add_ref(pointer, ref)
                positional_seen += 1
                continue
            kw = arg.keyword.value
            json_key = PYDANTIC_KWARG_TO_JSON_SCHEMA.get(kw)
            if json_key is None:
                continue  # unknown kwarg — skip (forward-compat
                # with future Pydantic additions).
            pointer = f"/properties/{field_name}/{json_key}"
            for ref in self._collect_refs(arg.value):
                self._add_ref(pointer, ref)

    # -- ref collection ---------------------------------------------------

    def _collect_refs(self, node: cst.CSTNode) -> Iterable[SymbolRef]:
        """Yield resolvable artifact refs from any expression subtree."""
        for name_node in _walk_names(node):
            info = self._imports.lookup(name_node.value)
            if info is None:
                continue
            module_path, imported_symbol = info
            result = self._resolver(module_path, imported_symbol)
            if result is None:
                continue
            kind, ref_name = result
            yield SymbolRef(
                symbol=name_node.value,
                kind=kind,
                name=ref_name,
                # JSON-Pointer-keyed refs leave position fields at
                # the "not applicable" sentinel.
                line=-1,
                col_start=0,
                col_end=0,
            )

    def _add_ref(self, pointer: str, ref: SymbolRef) -> None:
        bucket = self._refs_by_pointer.setdefault(pointer, [])
        # Dedup within a single pointer so the same symbol used
        # multiple times in one expression doesn't multiply.
        if not any(
            r.kind == ref.kind and r.name == ref.name and r.symbol == ref.symbol
            for r in bucket
        ):
            bucket.append(ref)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _walk_names(node: cst.CSTNode) -> Iterable[cst.Name]:
    """Yield every ``cst.Name`` descendant of ``node``.

    ``Attribute`` nodes are traversed via their ``value`` so that
    ``Sentiment.POSITIVE`` yields the ``Sentiment`` Name (the
    leftmost component, which is the imported symbol).
    """
    if isinstance(node, cst.Name):
        yield node
        return
    if isinstance(node, cst.Attribute):
        yield from _walk_names(node.value)
        return
    for child in node.children:
        yield from _walk_names(child)
