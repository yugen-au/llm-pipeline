"""
Hybrid AST-locate + string-splice module for pipeline file modification.

Strategy: use ast.parse() to find precise line positions of three modification
targets, then perform string-level splicing to preserve comments and formatting.
All three modifications (get_steps list, models keyword, agents keyword) share a
single file read/parse/splice/write cycle.

Pure ast.unparse() is rejected because it strips all comments and reformats.
Pure regex is rejected as brittle on varied multiline formatting.
libcst is rejected as a heavy dependency not in the project stack.
"""
from __future__ import annotations

import ast
import shutil
from pathlib import Path


class ASTModificationError(Exception):
    """Raised when any AST modification step fails."""


# ---------------------------------------------------------------------------
# AST locators
# ---------------------------------------------------------------------------


def _find_function_def(
    tree: ast.AST,
    name: str,
) -> ast.FunctionDef | None:
    """Return the first FunctionDef named `name` at module or class level.

    Walks module-level nodes and class body nodes. Does NOT recurse into
    nested functions or inner classes.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef)):
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.FunctionDef) and child.name == name:
                    return child
    return None


def _find_class_keyword_node(
    tree: ast.AST,
    class_name_pattern: str,
    keyword_name: str,
) -> tuple[ast.expr | None, int | None]:
    """Find a class keyword value node by class name substring and keyword name.

    Searches for a ClassDef whose name contains `class_name_pattern` (substring
    match for flexibility). Returns (value_node, end_lineno) or (None, None).

    The `end_lineno` is the last line of the keyword value expression so callers
    can determine where to insert new entries.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if class_name_pattern not in node.name:
            continue
        for kw in node.keywords:
            if kw.arg == keyword_name:
                return kw.value, kw.value.end_lineno
    return None, None


# ---------------------------------------------------------------------------
# String-splice helpers
# ---------------------------------------------------------------------------


def _get_indent(line: str) -> str:
    """Return leading whitespace of a line."""
    return line[: len(line) - len(line.lstrip())]


def _splice_into_list(
    source_lines: list[str],
    list_node: ast.List,
    new_element: str,
) -> list[str]:
    """Splice `new_element` into a list literal in source.

    Handles both multiline lists (inserts before closing `]`) and single-line
    lists (expands to multiline first, then inserts). Preserves indentation by
    using the indent of the opening line.

    Args:
        source_lines: 1-indexed file lines (index 0 == line 1).
        list_node: AST List node with lineno/end_lineno attributes.
        new_element: the Python expression to append, e.g. "NewStep.create_definition()".

    Returns:
        Modified source_lines list.
    """
    start_line = list_node.lineno - 1  # convert to 0-indexed
    end_line = list_node.end_lineno - 1  # 0-indexed

    is_multiline = end_line > start_line

    if not is_multiline:
        # Single-line: expand then insert
        return _expand_list_and_insert(source_lines, list_node, new_element)

    # Multiline: find closing bracket line and insert before it
    close_line_idx = end_line
    close_line = source_lines[close_line_idx]

    # Determine element indent from existing elements
    elem_indent = _infer_list_element_indent(source_lines, list_node)

    # Build new line with trailing comma
    new_line = f"{elem_indent}{new_element},\n"

    # Insert before closing bracket
    result = source_lines[:close_line_idx] + [new_line] + source_lines[close_line_idx:]
    return result


def _infer_list_element_indent(
    source_lines: list[str],
    list_node: ast.List,
) -> str:
    """Infer element indentation from the first element of a multiline list."""
    if list_node.elts:
        first_elt = list_node.elts[0]
        first_line = source_lines[first_elt.lineno - 1]
        return _get_indent(first_line)
    # Fall back: opening line indent + 4 spaces
    opening_line = source_lines[list_node.lineno - 1]
    return _get_indent(opening_line) + "    "


def _expand_list_and_insert(
    source_lines: list[str],
    list_node: ast.List,
    new_element: str,
) -> list[str]:
    """Expand a single-line list to multiline and append new_element.

    E.g.  `models=[Topic]`  becomes:
        models=[
            Topic,
            NewModel,
        ]
    """
    line_idx = list_node.lineno - 1  # 0-indexed
    line = source_lines[line_idx]

    # Find bracket positions in line text
    bracket_pos = line.find("[")
    close_pos = line.rfind("]")
    if bracket_pos == -1 or close_pos == -1:
        raise ASTModificationError(
            f"Cannot expand list on line {list_node.lineno}: no brackets found"
        )

    base_indent = _get_indent(line)
    elem_indent = base_indent + "    "

    prefix = line[: bracket_pos + 1]  # everything up to and including '['
    inner = line[bracket_pos + 1 : close_pos].strip()
    suffix = line[close_pos + 1 :]  # everything after ']'

    # Build replacement lines
    elements = [e.strip() for e in inner.split(",") if e.strip()]
    element_lines = [f"{elem_indent}{e},\n" for e in elements]
    element_lines.append(f"{elem_indent}{new_element},\n")
    close = f"{base_indent}]{suffix}" if suffix.strip() else f"{base_indent}]\n"

    replacement = [f"{prefix}\n"] + element_lines + [close]
    return source_lines[:line_idx] + replacement + source_lines[line_idx + 1 :]


# ---------------------------------------------------------------------------
# Import injection
# ---------------------------------------------------------------------------


def _detect_and_add_import(
    source_lines: list[str],
    tree: ast.AST,
    step_class: str,
    module_path: str,
    get_steps_func: ast.FunctionDef | None,
) -> list[str]:
    """Inject step class import using inline or top-level strategy.

    If `get_steps_func` body contains an ImportFrom matching `module_path`,
    append `step_class` to that inline import's names list. Otherwise, add a
    new top-level `from {module_path} import {step_class}` after the last
    existing top-level import.

    Returns modified source_lines.
    """
    if get_steps_func is not None:
        # Check for inline ImportFrom inside function body
        for node in ast.walk(get_steps_func):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module == module_path
            ):
                return _splice_into_inline_import(source_lines, node, step_class)

    # Fall through: top-level import injection
    return _add_toplevel_import(source_lines, tree, module_path, step_class)


def _detect_and_add_registry_import(
    source_lines: list[str],
    tree: ast.AST,
    class_name: str,
    module_path: str,
) -> list[str]:
    """Add a top-level import for a registry or agent-registry class.

    Always top-level (no inline pattern exists for registry/agent_registry).
    Skips if an import for `class_name` from `module_path` already exists.

    Returns modified source_lines.
    """
    # Check for existing import to avoid duplicates
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module_path:
            for alias in node.names:
                if alias.name == class_name:
                    return source_lines  # already imported
    return _add_toplevel_import(source_lines, tree, module_path, class_name)


def _splice_into_inline_import(
    source_lines: list[str],
    import_node: ast.ImportFrom,
    new_name: str,
) -> list[str]:
    """Add `new_name` to an existing ImportFrom node's names list.

    Handles both single-line and multi-line import forms.
    Skips if name already present.
    """
    # Check if already imported
    existing = {alias.name for alias in import_node.names}
    if new_name in existing:
        return source_lines

    start = import_node.lineno - 1  # 0-indexed
    end = import_node.end_lineno - 1  # 0-indexed

    is_multiline = end > start

    if is_multiline:
        # Insert before closing paren line
        close_line_idx = end
        close_line = source_lines[close_line_idx]

        # Infer element indent from last name
        last_name_line = source_lines[import_node.names[-1].lineno - 1]
        elem_indent = _get_indent(last_name_line)

        new_line = f"{elem_indent}{new_name},\n"
        return (
            source_lines[:close_line_idx]
            + [new_line]
            + source_lines[close_line_idx:]
        )
    else:
        # Single line: expand to multiline
        line_idx = start
        line = source_lines[line_idx]
        # Find the opening paren (may not exist for single-name inline imports)
        paren_pos = line.find("(")
        if paren_pos == -1:
            # e.g. `from foo import Bar` -> expand with parens
            # Find 'import ' and split
            import_kw = line.find(" import ")
            prefix = line[: import_kw + 8]  # up to and including 'import '
            names_part = line[import_kw + 8 :].rstrip()
            names = [n.strip() for n in names_part.split(",") if n.strip()]
            names.append(new_name)
            base_indent = _get_indent(line)
            elem_indent = base_indent + "    "
            replacement = (
                [f"{base_indent}from {import_node.module} import (\n"]
                + [f"{elem_indent}{n},\n" for n in names]
                + [f"{base_indent})\n"]
            )
            return source_lines[:line_idx] + replacement + source_lines[line_idx + 1 :]
        else:
            # Has parens: `from foo import (Bar)` single-line
            close_paren = line.rfind(")")
            inner = line[paren_pos + 1 : close_paren]
            names = [n.strip() for n in inner.split(",") if n.strip()]
            names.append(new_name)
            base_indent = _get_indent(line)
            elem_indent = base_indent + "    "
            suffix = line[close_paren + 1 :]
            replacement = (
                [f"{base_indent}from {import_node.module} import (\n"]
                + [f"{elem_indent}{n},\n" for n in names]
                + [f"{base_indent}){suffix}" if suffix.strip() else f"{base_indent})\n"]
            )
            return source_lines[:line_idx] + replacement + source_lines[line_idx + 1 :]


def _add_toplevel_import(
    source_lines: list[str],
    tree: ast.AST,
    module_path: str,
    class_name: str,
) -> list[str]:
    """Add `from {module_path} import {class_name}` after last top-level import.

    Skips if exact same from-import already present.
    """
    # Check for existing exact match
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module_path:
            for alias in node.names:
                if alias.name == class_name:
                    return source_lines

    # Find last top-level import line
    last_import_lineno = 0
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if node.end_lineno and node.end_lineno > last_import_lineno:
                last_import_lineno = node.end_lineno

    new_import_line = f"from {module_path} import {class_name}\n"

    if last_import_lineno == 0:
        # No imports found; insert at top (after module docstring if any)
        insert_idx = _find_after_docstring(tree, source_lines)
        return source_lines[:insert_idx] + [new_import_line] + source_lines[insert_idx:]

    insert_idx = last_import_lineno  # 0-indexed insert position (after last import line)
    return source_lines[:insert_idx] + [new_import_line] + source_lines[insert_idx:]


def _find_after_docstring(tree: ast.AST, source_lines: list[str]) -> int:
    """Return 0-indexed line to insert after module docstring (or 0 if none)."""
    if (
        isinstance(tree, ast.Module)
        and tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        return tree.body[0].end_lineno  # 0-indexed insert after docstring
    return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def modify_pipeline_file(
    pipeline_file: Path,
    step_class: str,
    step_module: str,
    step_name: str,
    extraction_model: str | None = None,
    extraction_module: str | None = None,
) -> None:
    """Modify a pipeline file to register a new step.

    Performs a single read/parse/splice/write cycle:
    1. Read source and create .bak backup.
    2. Parse with ast.parse().
    3. Locate get_steps(), Registry.models keyword.
    4. Inject step import (inline or top-level depending on get_steps pattern).
    5. Splice new step into get_steps() return list.
    6. If extraction_model provided, inject extraction import and splice models=[].
    7. Write modified source back to pipeline_file.

    Args:
        pipeline_file: Path to the target pipeline.py file.
        step_class: Name of the new step class, e.g. "SentimentAnalysisStep".
        step_module: Dotted module path for step_class import.
        step_name: snake_case step name, e.g. "sentiment_analysis".
        extraction_model: Optional SQLModel class name for registry models update.
        extraction_module: Optional dotted module path for extraction_model import.

    Raises:
        ASTModificationError: on parse failure, missing targets, or splice error.
    """
    # --- Read source ---
    try:
        source = pipeline_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ASTModificationError(f"Cannot read {pipeline_file}: {exc}") from exc

    # --- Backup ---
    bak_path = pipeline_file.with_suffix(".py.bak")
    try:
        bak_path.write_text(source, encoding="utf-8")
    except OSError as exc:
        raise ASTModificationError(f"Cannot write backup {bak_path}: {exc}") from exc

    try:
        source_lines = source.splitlines(keepends=True)
        # Ensure trailing newline present (simplifies splice logic)
        if source_lines and not source_lines[-1].endswith("\n"):
            source_lines[-1] += "\n"

        # --- Parse ---
        try:
            tree = ast.parse(source)
        except SyntaxError as exc:
            raise ASTModificationError(
                f"Syntax error parsing {pipeline_file}: {exc}"
            ) from exc

        # --- Locate get_steps() ---
        get_steps_func = _find_function_def(tree, "get_steps")
        if get_steps_func is None:
            raise ASTModificationError(
                f"Cannot find get_steps() function in {pipeline_file}"
            )

        # Locate the return list inside get_steps
        steps_list_node = _find_return_list(get_steps_func)
        if steps_list_node is None:
            raise ASTModificationError(
                f"get_steps() does not contain a return list literal in {pipeline_file}"
            )

        # --- Inject step import ---
        source_lines = _detect_and_add_import(
            source_lines, tree, step_class, step_module, get_steps_func
        )
        # Re-parse after import injection so line numbers stay consistent for
        # subsequent locates. We accumulate all splices in one pass but must
        # re-parse to get updated node positions.
        tree = _reparse(source_lines, pipeline_file)
        get_steps_func = _find_function_def(tree, "get_steps")
        steps_list_node = _find_return_list(get_steps_func)

        # --- Splice step into get_steps() return list ---
        source_lines = _splice_into_list(
            source_lines,
            steps_list_node,
            f"{step_class}.create_definition()",
        )
        tree = _reparse(source_lines, pipeline_file)

        # --- Extraction model (optional) ---
        if extraction_model and extraction_module:
            source_lines = _detect_and_add_registry_import(
                source_lines, tree, extraction_model, extraction_module
            )
            tree = _reparse(source_lines, pipeline_file)

            models_node, _ = _find_class_keyword_node(tree, "Registry", "models")
            if models_node is None:
                raise ASTModificationError(
                    f"Cannot find Registry models=[...] keyword in {pipeline_file}"
                )
            if not isinstance(models_node, ast.List):
                raise ASTModificationError(
                    f"Registry models keyword is not a list literal in {pipeline_file}"
                )
            source_lines = _splice_into_list(source_lines, models_node, extraction_model)
            tree = _reparse(source_lines, pipeline_file)

        # --- Write result ---
        pipeline_file.write_text("".join(source_lines), encoding="utf-8")

    except ASTModificationError:
        # Restore backup on failure
        try:
            shutil.copy2(str(bak_path), str(pipeline_file))
        except OSError:
            pass  # best effort
        raise
    except Exception as exc:
        try:
            shutil.copy2(str(bak_path), str(pipeline_file))
        except OSError:
            pass
        raise ASTModificationError(
            f"Unexpected error modifying {pipeline_file}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Internal utilities
# ---------------------------------------------------------------------------


def _find_return_list(func: ast.FunctionDef) -> ast.List | None:
    """Return the List node from the last return statement in func, or None."""
    for node in ast.walk(func):
        if isinstance(node, ast.Return) and isinstance(node.value, ast.List):
            return node.value
    return None


def _reparse(source_lines: list[str], path: Path) -> ast.Module:
    """Re-parse source_lines after an in-place modification."""
    try:
        return ast.parse("".join(source_lines))
    except SyntaxError as exc:
        raise ASTModificationError(
            f"Syntax error after splice in {path}: {exc}"
        ) from exc


__all__ = ["modify_pipeline_file", "ASTModificationError"]
