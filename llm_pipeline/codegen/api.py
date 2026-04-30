"""Public codegen API.

The two public entry points are:

- :func:`apply_instructions_delta` — modify an existing
  ``INSTRUCTIONS`` (or any) class file by adding new fields or
  rewriting existing ones. Used by the eval-runner accept path
  (``llm_pipeline.evals.acceptance``).

- :func:`generate_prompt_variables` — *(landed in Track B.3)*
  generate a fresh ``llm_pipelines/variables/{name}.py`` file from a
  parsed Phoenix ``Prompt`` YAML.

Every public function:

1. Validates the target path is under the configured
   ``llm_pipelines/`` root via :func:`assert_under_root` BEFORE any
   transformation runs (cheap fail-fast).
2. Reads the existing module via :func:`read_module` (or builds a
   fresh one from scratch).
3. Applies transformers / builders.
4. Writes via :func:`write_module_if_changed` (idempotent — no
   churn when content is unchanged).

All errors raise :class:`CodegenError` (or a subclass) so callers
have a single exception type to handle. Backups (``.bak``) are
written when ``write_backup=True`` so the eval-runner accept path
can roll back on review failure.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import libcst as cst

from llm_pipeline.codegen.io import (
    CodegenPathError,
    assert_under_root,
    read_module,
    write_module,
    write_module_if_changed,
)
from llm_pipeline.codegen.transformers import (
    AddFieldToClass,
    FieldNotFoundError,
    ModifyFieldOnClass,
    TargetClassNotFoundError,
    collect_class_field_names,
    find_class,
)


__all__ = [
    "CodegenError",
    "apply_instructions_delta",
]


class CodegenError(Exception):
    """Top-level error for codegen operations.

    Subclasses :class:`CodegenPathError` for path-guard failures and
    inner transformer failures (:class:`TargetClassNotFoundError`,
    :class:`FieldNotFoundError`) are re-raised as ``CodegenError`` by
    the public API so callers don't need to import three exception
    types to handle codegen failures.
    """


def apply_instructions_delta(
    *,
    source_file: Path,
    class_name: str,
    delta: list[dict[str, Any]],
    root: Path | None = None,
    write_backup: bool = True,
) -> dict[str, Any]:
    """Apply a variant ``instructions_delta`` to a class file.

    Mutates ``source_file`` in place. Each delta op:

    - ``op="add"``: appends ``{field}: {type_str} = {default!r}`` to
      the class body. Raises if the field already exists.
    - ``op="modify"``: rewrites the existing field's annotation
      (when ``type_str`` provided) and / or default. Raises if the
      field doesn't exist.

    Path-guarded: ``source_file`` must resolve under ``root`` (or the
    configured ``LLM_PIPELINES_ROOT``). Comments and surrounding
    formatting are preserved by libcst's lossless round-trip.

    A ``.bak`` of the original is written next to the source when
    ``write_backup=True`` (best-effort — failure to write the backup
    doesn't block the operation).

    Returns a summary::

        {
            "file": "absolute/path/to/file.py",
            "class": "InstructionsClassName",
            "added": [...],
            "modified": [...],
        }

    Raises:
        :class:`CodegenError` on any failure — path outside root,
        class not found, add-existing / modify-missing field, parse
        failure, etc.
    """
    resolved = _guard_or_raise(source_file, root)

    if not resolved.exists():
        raise CodegenError(f"source file does not exist: {resolved}")

    try:
        module = read_module(resolved)
    except Exception as exc:  # noqa: BLE001 — surface any parse error uniformly
        raise CodegenError(f"failed to parse {resolved}: {exc}") from exc

    if find_class(module, class_name) is None:
        raise CodegenError(
            f"class {class_name!r} not found in {resolved}"
        )

    added: list[str] = []
    modified: list[str] = []

    for idx, op_dict in enumerate(delta):
        op = op_dict.get("op")
        field = op_dict.get("field")
        type_str = op_dict.get("type_str")
        default = op_dict.get("default")

        if not isinstance(field, str) or not field:
            raise CodegenError(
                f"delta item {idx}: 'field' must be a non-empty string; "
                f"got {field!r}"
            )

        existing_fields = collect_class_field_names(module, class_name)

        if op == "add":
            if field in existing_fields:
                raise CodegenError(
                    f"delta item {idx}: cannot add field {field!r} — "
                    f"already present on {class_name}"
                )
            if not type_str:
                raise CodegenError(
                    f"delta item {idx}: 'add' op requires 'type_str' "
                    f"(got {type_str!r})"
                )
            new_stmt = _build_field_stmt(field, type_str, default)
            module = _apply_add(module, class_name, new_stmt)
            added.append(field)
        elif op == "modify":
            if field not in existing_fields:
                raise CodegenError(
                    f"delta item {idx}: cannot modify field {field!r} — "
                    f"not present on {class_name}"
                )
            # When type_str is omitted, preserve the original annotation
            # by reading it off the current AST.
            effective_type = (
                type_str
                if type_str is not None
                else _existing_annotation(module, class_name, field)
            )
            new_stmt = _build_field_stmt(field, effective_type, default)
            module = _apply_modify(module, class_name, field, new_stmt)
            modified.append(field)
        else:
            raise CodegenError(
                f"delta item {idx}: unsupported op {op!r}; expected "
                f"'add' or 'modify'"
            )

    # Backup before write — best-effort.
    if write_backup:
        bak = resolved.with_suffix(resolved.suffix + ".bak")
        try:
            shutil.copy2(resolved, bak)
        except OSError:
            pass

    try:
        write_module(resolved, module, root=root)
    except CodegenPathError:
        raise CodegenError(
            f"path-guard rejected write to {resolved} (this should "
            f"have been caught earlier)"
        )

    return {
        "file": str(resolved),
        "class": class_name,
        "added": added,
        "modified": modified,
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _guard_or_raise(source_file: Path, root: Path | None) -> Path:
    """Path-guard a write target; convert :class:`CodegenPathError` to :class:`CodegenError`."""
    try:
        return assert_under_root(source_file, root=root)
    except CodegenPathError as exc:
        raise CodegenError(str(exc)) from exc


def _build_field_stmt(
    field: str,
    type_str: str,
    default: Any,
) -> cst.BaseStatement:
    """Build ``{field}: {type_str} = {default!r}`` as a libcst statement.

    ``default`` is repr'd so it round-trips for arbitrary scalars,
    lists, and string-keyed dicts (the upstream variant whitelist
    ensures only JSON-safe values reach here).
    """
    src = f"{field}: {type_str.strip()} = {default!r}"
    return cst.parse_statement(src)


def _existing_annotation(
    module: cst.Module, class_name: str, field: str,
) -> str:
    """Return the source text of the current annotation for ``field``.

    Used when a ``modify`` op omits ``type_str`` — we preserve the
    existing annotation rather than dropping back to ``Any``. Falls
    back to ``"Any"`` if the field isn't an ``AnnAssign`` (shouldn't
    happen given the existence check above, but defensive).
    """
    cls = find_class(module, class_name)
    if cls is None:
        return "Any"
    body = cls.body
    if not isinstance(body, cst.IndentedBlock):
        return "Any"
    for stmt in body.body:
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        for sub in stmt.body:
            if (
                isinstance(sub, cst.AnnAssign)
                and isinstance(sub.target, cst.Name)
                and sub.target.value == field
            ):
                return module.code_for_node(sub.annotation.annotation)
    return "Any"


def _apply_add(
    module: cst.Module,
    class_name: str,
    new_stmt: cst.BaseStatement,
) -> cst.Module:
    transformer = AddFieldToClass(class_name, new_stmt)
    new_module = module.visit(transformer)
    if not transformer.visited_target:
        raise CodegenError(
            f"AddFieldToClass: class {class_name!r} disappeared between "
            f"discovery and transform (internal error)"
        )
    if not isinstance(new_module, cst.Module):
        raise CodegenError(
            f"AddFieldToClass returned a non-Module result "
            f"({type(new_module).__name__}); aborting"
        )
    return new_module


def _apply_modify(
    module: cst.Module,
    class_name: str,
    field: str,
    new_stmt: cst.BaseStatement,
) -> cst.Module:
    transformer = ModifyFieldOnClass(class_name, field, new_stmt)
    new_module = module.visit(transformer)
    if not transformer.visited_target:
        raise CodegenError(
            f"ModifyFieldOnClass: class {class_name!r} disappeared "
            f"between discovery and transform (internal error)"
        )
    if not transformer.visited_field:
        raise CodegenError(
            f"ModifyFieldOnClass: field {field!r} disappeared from "
            f"{class_name!r} between discovery and transform "
            f"(internal error)"
        )
    if not isinstance(new_module, cst.Module):
        raise CodegenError(
            f"ModifyFieldOnClass returned a non-Module result "
            f"({type(new_module).__name__}); aborting"
        )
    return new_module
