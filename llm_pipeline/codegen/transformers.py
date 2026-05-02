"""Reusable :class:`libcst.CSTTransformer` subclasses for common modifications.

These are the "modify an existing file" primitives. Each transformer
targets a specific change shape (add a field, modify a field, insert
into a list literal, etc.) and is fully composable — apply them by
calling ``module.visit(transformer)`` and the result is a new module
with the change applied. Comments and formatting are preserved via
libcst's lossless round-trip.

Each transformer raises :class:`TransformerError` (or a subclass) when
the target it expects to find is absent. This keeps mutation
operations strict — if the target shape isn't there, the caller
should fix the input rather than have the transformer silently no-op.
"""
from __future__ import annotations

from typing import Sequence

import libcst as cst


__all__ = [
    "AddFieldToClass",
    "FieldNotFoundError",
    "ModifyFieldOnClass",
    "SetAttributeOnClass",
    "TransformerError",
    "TargetClassNotFoundError",
]


class TransformerError(Exception):
    """Base for codegen transformer failures (target class missing, etc.)."""


class TargetClassNotFoundError(TransformerError):
    """The transformer's target class wasn't found in the visited module."""


class FieldNotFoundError(TransformerError):
    """A modify-field op targeted a field that doesn't exist on the class."""


class _ClassBodyTransformer(cst.CSTTransformer):
    """Common scaffolding: locate a class by name; track whether it was found.

    Subclasses override :meth:`_transform_body` to mutate the class body.
    The visited module's :meth:`visited_target` flag is set ``True`` if
    the class was located, allowing callers to raise
    :class:`TargetClassNotFoundError` after the visit completes.
    """

    def __init__(self, class_name: str) -> None:
        super().__init__()
        self.class_name = class_name
        self.visited_target = False

    def leave_ClassDef(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        if original_node.name.value != self.class_name:
            return updated_node
        self.visited_target = True
        return self._transform_body(original_node, updated_node)

    def _transform_body(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        raise NotImplementedError


class AddFieldToClass(_ClassBodyTransformer):
    """Append a new field-assignment statement to a named class's body.

    The new statement is inserted at the end of the class body so the
    resulting source matches what a developer would type if hand-
    appending a field. Comments / blank lines elsewhere in the class
    are preserved unchanged.

    Example::

        new_stmt = cst.parse_statement("sentiment: str = Field(description='x')")
        transformer = AddFieldToClass("Inputs", new_stmt)
        modified = original_module.visit(transformer)
        if not transformer.visited_target:
            raise TargetClassNotFoundError(...)

    Most callers go through :func:`llm_pipeline.codegen.api.apply_instructions_delta`
    rather than constructing this directly.
    """

    def __init__(
        self,
        class_name: str,
        new_stmt: cst.BaseStatement,
    ) -> None:
        super().__init__(class_name)
        self.new_stmt = new_stmt

    def _transform_body(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        body = updated_node.body
        if not isinstance(body, cst.IndentedBlock):
            return updated_node
        new_body_stmts = list(body.body) + [self.new_stmt]
        return updated_node.with_changes(
            body=body.with_changes(body=new_body_stmts),
        )


class ModifyFieldOnClass(_ClassBodyTransformer):
    """Replace an existing ``AnnAssign`` field on a named class.

    The replacement is positional: the existing field-line is swapped
    out with ``new_stmt`` while every other statement in the class
    body keeps its position and surrounding whitespace.

    If the field name isn't found on the class, ``visited_field`` stays
    ``False``. The caller is expected to check both
    :attr:`visited_target` and :attr:`visited_field` after the visit
    and raise the appropriate error.

    Example::

        replacement = cst.parse_statement("text: str = 'hello'")
        transformer = ModifyFieldOnClass("Inputs", "text", replacement)
        modified = original_module.visit(transformer)
        if not transformer.visited_target:
            raise TargetClassNotFoundError(...)
        if not transformer.visited_field:
            raise FieldNotFoundError(...)
    """

    def __init__(
        self,
        class_name: str,
        field_name: str,
        new_stmt: cst.BaseStatement,
    ) -> None:
        super().__init__(class_name)
        self.field_name = field_name
        self.new_stmt = new_stmt
        self.visited_field = False

    def _transform_body(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        body = updated_node.body
        if not isinstance(body, cst.IndentedBlock):
            return updated_node
        new_body_stmts: list[cst.BaseStatement] = []
        for stmt in body.body:
            if self._matches_target_field(stmt):
                # Preserve any leading comments / blank lines that
                # were attached to the original statement —
                # libcst stores those as `leading_lines` on the line
                # itself, so a fresh parse_statement() result would
                # otherwise drop them.
                replacement = self.new_stmt
                if (
                    isinstance(stmt, cst.SimpleStatementLine)
                    and isinstance(replacement, cst.SimpleStatementLine)
                ):
                    replacement = replacement.with_changes(
                        leading_lines=stmt.leading_lines,
                    )
                new_body_stmts.append(replacement)
                self.visited_field = True
            else:
                new_body_stmts.append(stmt)
        return updated_node.with_changes(
            body=body.with_changes(body=new_body_stmts),
        )

    def _matches_target_field(self, stmt: cst.BaseStatement) -> bool:
        """True iff ``stmt`` is a ``name: type = value`` line targeting our field."""
        if not isinstance(stmt, cst.SimpleStatementLine):
            return False
        for sub in stmt.body:
            if (
                isinstance(sub, cst.AnnAssign)
                and isinstance(sub.target, cst.Name)
                and sub.target.value == self.field_name
            ):
                return True
        return False


class SetAttributeOnClass(_ClassBodyTransformer):
    """Set ``attr_name = <new_value>`` on a named class — preserves shape.

    Unlike :class:`ModifyFieldOnClass` (which swaps the whole
    statement and is AnnAssign-only), this transformer:

    - Matches both ``Assign`` (``value = 3``) and ``AnnAssign``
      (``value: int = 3``) shapes.
    - Replaces only the right-hand-side expression — the original
      annotation (if present) is preserved.
    - Appends ``attr_name = <new_value>`` at the end of the class
      body when the slot is missing and ``append_if_missing=True``
      (default).

    The new value is provided as Python source text (e.g. ``"42"``,
    ``"'hello'"``, ``"[1, 2, 3]"``) and parsed via
    :func:`libcst.parse_expression`. Use ``repr()`` for literals or
    hand-build for expressions that need it.

    ``visited_field`` indicates whether the slot existed before the
    visit (``True``) or was newly appended (``False``).
    """

    def __init__(
        self,
        class_name: str,
        attr_name: str,
        new_value_literal: str,
        *,
        append_if_missing: bool = True,
    ) -> None:
        super().__init__(class_name)
        self.attr_name = attr_name
        self.new_value_literal = new_value_literal
        self.append_if_missing = append_if_missing
        self.visited_field = False

    def _transform_body(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        body = updated_node.body
        if not isinstance(body, cst.IndentedBlock):
            return updated_node

        new_value_expr = cst.parse_expression(self.new_value_literal)
        new_inner: list = []
        for inner in body.body:
            if isinstance(inner, cst.SimpleStatementLine):
                new_subs: list = []
                for sub in inner.body:
                    if (
                        isinstance(sub, cst.Assign)
                        and len(sub.targets) == 1
                        and isinstance(sub.targets[0].target, cst.Name)
                        and sub.targets[0].target.value == self.attr_name
                    ):
                        sub = sub.with_changes(value=new_value_expr)
                        self.visited_field = True
                    elif (
                        isinstance(sub, cst.AnnAssign)
                        and isinstance(sub.target, cst.Name)
                        and sub.target.value == self.attr_name
                        and sub.value is not None
                    ):
                        sub = sub.with_changes(value=new_value_expr)
                        self.visited_field = True
                    new_subs.append(sub)
                inner = inner.with_changes(body=new_subs)
            new_inner.append(inner)

        if not self.visited_field and self.append_if_missing:
            new_inner.append(cst.SimpleStatementLine(body=[
                cst.Assign(
                    targets=[cst.AssignTarget(target=cst.Name(self.attr_name))],
                    value=new_value_expr,
                )
            ]))

        return updated_node.with_changes(
            body=body.with_changes(body=new_inner),
        )


def collect_class_field_names(
    module: cst.Module,
    class_name: str,
) -> set[str]:
    """Return the set of ``AnnAssign`` field names on ``class_name``.

    Walks the module's CST without modifying it. Used by callers (e.g.
    ``apply_instructions_delta``) to validate add/modify ops against
    the current class shape before applying transformers.

    Returns an empty set if the class isn't found — callers should
    distinguish "class missing" from "class has no fields" via a
    separate check (e.g. :func:`find_class`).
    """
    finder = _FieldNameCollector(class_name)
    module.visit(finder)
    return finder.fields


class _FieldNameCollector(cst.CSTVisitor):
    def __init__(self, class_name: str) -> None:
        super().__init__()
        self.class_name = class_name
        self.fields: set[str] = set()
        self._inside_target = False

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        # Only descend into the targeted class (avoids false positives
        # from nested classes with the same field names).
        if node.name.value == self.class_name and not self._inside_target:
            self._inside_target = True
            return True
        # Don't recurse into nested classes when we're not on the target.
        return self._inside_target

    def leave_ClassDef(self, original_node: cst.ClassDef) -> None:
        if (
            self._inside_target
            and original_node.name.value == self.class_name
        ):
            self._inside_target = False

    def visit_AnnAssign(self, node: cst.AnnAssign) -> bool:
        if not self._inside_target:
            return False
        if isinstance(node.target, cst.Name):
            self.fields.add(node.target.value)
        return False


def find_class(
    module: cst.Module,
    class_name: str,
) -> cst.ClassDef | None:
    """Locate the first top-level ``ClassDef`` named ``class_name``.

    Falls back to a deep walk if the class is nested inside another
    construct (rare; framework-generated files always declare
    targets at module top level). Returns ``None`` if not found.
    """
    for stmt in module.body:
        if isinstance(stmt, cst.ClassDef) and stmt.name.value == class_name:
            return stmt
    finder = _ClassFinder(class_name)
    module.visit(finder)
    return finder.found


class _ClassFinder(cst.CSTVisitor):
    def __init__(self, class_name: str) -> None:
        super().__init__()
        self.class_name = class_name
        self.found: cst.ClassDef | None = None

    def visit_ClassDef(self, node: cst.ClassDef) -> bool:
        if self.found is None and node.name.value == self.class_name:
            self.found = node
        return True
