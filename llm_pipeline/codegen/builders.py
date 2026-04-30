"""High-level builders for common CST patterns.

Wraps the verbose libcst constructor API behind small, focused helpers
that match how callers actually use the codegen subsystem. The
strategy: lean on ``cst.parse_statement`` / ``cst.parse_expression``
wherever possible (libcst's own docs recommend this over node-by-node
construction for build-from-scratch use cases) but expose the result
as the appropriate node type so transformers can compose them.

Builders are pure functions returning libcst nodes. They don't touch
disk and don't enforce path guards — that's :mod:`io`'s job. Callers
assemble builder outputs into a ``cst.Module`` and hand it to
:func:`write_module_if_changed`.

Strings flowing into builders are always quoted via ``repr()`` before
embedding in source — this is the only safe way to handle arbitrary
content (including descriptions with quotes, newlines, etc.) when
emitting Python literals.
"""
from __future__ import annotations

from dataclasses import dataclass

import libcst as cst


__all__ = [
    "FieldSpec",
    "class_var_dict_assignment",
    "import_from",
    "module_docstring",
    "pydantic_class",
    "pydantic_field_assignment",
]


@dataclass(frozen=True)
class FieldSpec:
    """Declarative spec for a Pydantic field on a generated class.

    ``annotation`` is a Python type expression as a string (e.g.
    ``"str"``, ``"list[int]"``, ``"Sentiment"``). It's emitted verbatim
    into the generated source — callers must ensure it's syntactically
    valid Python in the target file's import context.

    ``description`` is the human-readable text that goes into
    ``Field(description=...)``. It's quoted via ``repr()`` so any
    special characters (quotes, backslashes, newlines) are escaped
    safely.
    """

    name: str
    annotation: str
    description: str


def import_from(module: str, names: list[str]) -> cst.SimpleStatementLine:
    """Build ``from {module} import {name1}, {name2}, ...``."""
    if not names:
        raise ValueError(
            "import_from requires at least one name to import"
        )
    src = f"from {module} import {', '.join(names)}"
    stmt = cst.parse_statement(src)
    if not isinstance(stmt, cst.SimpleStatementLine):
        raise RuntimeError(
            f"Expected SimpleStatementLine for import; got "
            f"{type(stmt).__name__}"
        )
    return stmt


def module_docstring(text: str) -> cst.SimpleStatementLine:
    """Build a triple-quoted module docstring as the first statement.

    The text is embedded with ``repr()`` then unwrapped so we keep
    Python's escaping rules without manually escaping every quote /
    backslash. Falls back to a triple-quoted form if the docstring
    contains a triple-quote.
    """
    quoted = _python_string_literal(text, prefer_triple=True)
    return cst.parse_statement(quoted)  # type: ignore[return-value]


def pydantic_field_assignment(spec: FieldSpec) -> cst.SimpleStatementLine:
    """Build ``{name}: {annotation} = Field(description={...})``.

    The description is repr-quoted so it round-trips safely (handles
    embedded quotes, backslashes, etc.).
    """
    description_literal = _python_string_literal(spec.description)
    src = (
        f"{spec.name}: {spec.annotation} = "
        f"Field(description={description_literal})"
    )
    stmt = cst.parse_statement(src)
    if not isinstance(stmt, cst.SimpleStatementLine):
        raise RuntimeError(
            f"Expected SimpleStatementLine for field assignment; got "
            f"{type(stmt).__name__}"
        )
    return stmt


def pydantic_class(
    name: str,
    fields: list[FieldSpec],
    *,
    base: str = "BaseModel",
) -> cst.ClassDef:
    """Build ``class {name}({base}): <field assignments>``.

    Empty fields list emits ``class {name}({base}): pass``. The base
    is emitted verbatim — caller must ensure it resolves in the
    target file's import context.
    """
    if not fields:
        body_stmts: list[cst.BaseStatement] = [cst.parse_statement("pass")]
    else:
        body_stmts = [pydantic_field_assignment(f) for f in fields]

    return cst.ClassDef(
        name=cst.Name(name),
        bases=[cst.Arg(value=cst.Name(base))],
        body=cst.IndentedBlock(body=body_stmts),
    )


def class_var_dict_assignment(
    name: str,
    items: dict[str, str],
    *,
    value_type: str = "str",
) -> cst.SimpleStatementLine:
    """Build ``{name}: ClassVar[dict[str, {value_type}]] = {{ items }}``.

    Both keys and values are repr-quoted so embedded special
    characters survive. Empty ``items`` emits an empty dict literal.
    """
    if not items:
        literal = "{}"
    else:
        entries = ", ".join(
            f"{_python_string_literal(k)}: {_python_string_literal(v)}"
            for k, v in items.items()
        )
        literal = "{" + entries + "}"

    src = (
        f"{name}: ClassVar[dict[str, {value_type}]] = {literal}"
    )
    stmt = cst.parse_statement(src)
    if not isinstance(stmt, cst.SimpleStatementLine):
        raise RuntimeError(
            f"Expected SimpleStatementLine for ClassVar assignment; "
            f"got {type(stmt).__name__}"
        )
    return stmt


# ---------------------------------------------------------------------------
# String-literal helpers
# ---------------------------------------------------------------------------


def _python_string_literal(text: str, *, prefer_triple: bool = False) -> str:
    """Return ``text`` quoted as a Python string literal (safe for source).

    Handles embedded quotes, backslashes, newlines via ``repr()``.
    For multi-line content where a triple-quoted form is more
    readable, set ``prefer_triple=True`` — falls back to ``repr()``
    if ``text`` contains a triple-quote sequence.
    """
    if prefer_triple and "\n" in text and '"""' not in text:
        return f'"""{text}"""'
    return repr(text)
