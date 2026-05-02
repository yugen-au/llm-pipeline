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
from typing import Any, Callable

import libcst as cst

from llm_pipeline.codegen.builders import (
    FieldSpec,
    class_var_dict_assignment,
    import_from,
    module_docstring,
    pydantic_class,
)
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
    SetAttributeOnClass,
    TargetClassNotFoundError,
    collect_class_field_names,
    find_class,
)


__all__ = [
    "CodegenError",
    "apply_instructions_delta",
    "edit_code_body",
    "edit_imports",
    "generate_prompt_variables",
    "render_import_block",
    "set_class_attribute",
    "write_code_body",
    "write_imports",
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


def generate_prompt_variables(
    *,
    prompt_name: str,
    variable_definitions: dict[str, dict[str, Any]] | None,
    step_file: Path,
    root: Path | None = None,
) -> bool:
    """Upsert the ``XPrompt`` PromptVariables class inside ``step_file``.

    Each step file owns its paired :class:`PromptVariables` subclass
    (1:1, same module). This function rewrites that class from the
    YAML's ``variable_definitions`` — replacing the existing class
    body in place if it's there, appending a new class otherwise.

    ``prompt_name`` is the snake_case Phoenix prompt name (e.g.
    ``"topic_extraction"``). The target class name is its PascalCase
    form with the ``Prompt`` suffix appended (e.g.
    ``TopicExtractionPrompt``).

    ``variable_definitions`` mirrors the YAML's
    ``metadata.variable_definitions`` dict::

        {
            "text": {"type": "str", "description": "Input text"},
            "sentiment_options": {
                "type": "str",
                "description": "Allowed sentiments",
                "auto_generate": "enum_names(Sentiment)",
            },
        }

    Per-key rules:

    - ``auto_generate`` present → key goes into the ``auto_vars``
      ``ClassVar[dict[str, str]]``, NOT a Pydantic field. (Mutual
      exclusion is enforced by ``PromptVariables.__pydantic_init_subclass__``.)
    - Otherwise → Pydantic field annotated as ``type`` (default
      ``"str"`` if absent), with ``Field(description=...)``.

    An empty / ``None`` ``variable_definitions`` emits a class with
    a ``pass`` body — useful for steps whose ``prepare()`` returns
    ``[XxxPrompt()]`` with no variables.

    Required imports (``from pydantic import Field``,
    ``from typing import ClassVar``,
    ``from llm_pipeline.prompts import PromptVariables``) are added
    if missing. Imports already present are left alone.

    Path-guarded: ``step_file`` must resolve under ``root`` (or the
    ``LLM_PIPELINES_ROOT`` env var, default ``./llm_pipelines``).
    Idempotent: returns ``False`` if the file already contains the
    generated class verbatim.

    Honors :func:`llm_pipeline._dry_run.dry_run_mode` — inside a
    dry-run scope the build + compare runs but the disk write is
    skipped. The return value still reflects "would-write", so the
    UI startup pre-flight can detect stale step files without
    mutating the working tree.

    Returns:
        ``True`` if the file was written / would be written,
        ``False`` if the existing content already matched.

    Raises:
        :class:`CodegenError` on any failure — path outside root,
        ``step_file`` doesn't exist (generate sync runs against
        existing steps; new steps must be authored first), invalid
        ``prompt_name``, malformed ``variable_definitions``, etc.
    """
    if not isinstance(prompt_name, str) or not prompt_name:
        raise CodegenError(
            f"prompt_name must be a non-empty string; got {prompt_name!r}"
        )

    resolved = _guard_or_raise(step_file, root)

    if not resolved.is_file():
        raise CodegenError(
            f"step file does not exist: {resolved}. "
            f"Generate runs against existing steps — author the step "
            f"file first, then run generate to populate its prompt "
            f"variables class from YAML."
        )

    class_name = _snake_to_pascal(prompt_name) + "Prompt"

    fields, auto_vars = _split_variable_definitions(
        prompt_name, variable_definitions or {},
    )

    module = read_module(resolved)

    new_class_def = _build_prompt_variables_classdef(
        prompt_name=prompt_name,
        class_name=class_name,
        fields=fields,
        auto_vars=auto_vars,
    )

    existing = find_class(module, class_name)
    if existing is not None:
        module = _replace_classdef(module, class_name, new_class_def)
    else:
        module = _append_classdef(module, new_class_def)

    module = _ensure_prompt_variables_imports(
        module, has_fields=bool(fields), has_auto_vars=bool(auto_vars),
    )

    try:
        return write_module_if_changed(resolved, module, root=root)
    except CodegenPathError:
        # Defensive: assert_under_root already passed in _guard_or_raise.
        raise CodegenError(
            f"path-guard rejected write to {resolved} (this should "
            f"have been caught earlier)"
        )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def set_class_attribute(
    *,
    module: cst.Module,
    class_name: str,
    attr_name: str,
    new_value_literal: str,
    append_if_missing: bool = True,
) -> cst.Module:
    """Set ``attr_name = <new_value>`` on the named class in ``module``.

    Module-in / module-out so callers can chain multiple edits before
    serialising. Matches both ``Assign`` (``value = 3``) and ``AnnAssign``
    (``value: int = 3``) shapes — preserves the annotation when present
    and only swaps the right-hand side.

    ``new_value_literal`` is Python source text parsed via
    :func:`libcst.parse_expression`. Use ``repr()`` for primitive
    literals or hand-build for expressions (``"datetime.now()"`` etc.).

    Raises :class:`CodegenError` if the class isn't found or, when
    ``append_if_missing=False``, if the attribute slot is missing.
    """
    transformer = SetAttributeOnClass(
        class_name=class_name,
        attr_name=attr_name,
        new_value_literal=new_value_literal,
        append_if_missing=append_if_missing,
    )
    new_module = module.visit(transformer)
    if not transformer.visited_target:
        raise CodegenError(
            f"set_class_attribute: class {class_name!r} not found"
        )
    if not transformer.visited_field and not append_if_missing:
        raise CodegenError(
            f"set_class_attribute: {class_name}.{attr_name} not present and "
            f"append_if_missing=False"
        )
    return new_module


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


# ---------------------------------------------------------------------------
# generate_prompt_variables internals
# ---------------------------------------------------------------------------


def _snake_to_pascal(name: str) -> str:
    """Convert ``snake_case`` -> ``PascalCase``.

    Inverse of :func:`llm_pipeline.naming.to_snake_case` for the
    normal case. Multiple underscores collapse; empty parts are
    dropped. Non-alphanumeric chars in parts are passed through —
    callers are expected to feed valid Python identifiers.
    """
    parts = [p for p in name.split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts)


def _split_variable_definitions(
    prompt_name: str,
    variable_definitions: dict[str, dict[str, Any]],
) -> tuple[list[FieldSpec], dict[str, str]]:
    """Split YAML ``variable_definitions`` into Pydantic fields + auto_vars.

    A var with ``auto_generate`` becomes an ``auto_vars`` entry
    (placeholder -> expression string). Otherwise it becomes a
    Pydantic field annotated by its ``type`` (default ``"str"``).

    Raises :class:`CodegenError` for malformed entries — missing
    description, non-string keys, etc.
    """
    if not isinstance(variable_definitions, dict):
        raise CodegenError(
            f"{prompt_name}: variable_definitions must be a dict; "
            f"got {type(variable_definitions).__name__}"
        )

    fields: list[FieldSpec] = []
    auto_vars: dict[str, str] = {}

    for var_name, spec in variable_definitions.items():
        if not isinstance(var_name, str) or not var_name:
            raise CodegenError(
                f"{prompt_name}: variable name must be a non-empty "
                f"string; got {var_name!r}"
            )
        if not isinstance(spec, dict):
            raise CodegenError(
                f"{prompt_name}.{var_name}: definition must be a dict "
                f"with 'description' (and optional 'type', "
                f"'auto_generate'); got {type(spec).__name__}"
            )

        description = spec.get("description")
        if not isinstance(description, str) or not description:
            raise CodegenError(
                f"{prompt_name}.{var_name}: 'description' must be a "
                f"non-empty string; got {description!r}"
            )

        auto_generate = spec.get("auto_generate")
        if auto_generate is not None:
            if not isinstance(auto_generate, str) or not auto_generate:
                raise CodegenError(
                    f"{prompt_name}.{var_name}: 'auto_generate' must "
                    f"be a non-empty expression string; got "
                    f"{auto_generate!r}"
                )
            auto_vars[var_name] = auto_generate
            continue

        annotation = spec.get("type", "str")
        if not isinstance(annotation, str) or not annotation:
            raise CodegenError(
                f"{prompt_name}.{var_name}: 'type' must be a "
                f"non-empty Python type expression string; got "
                f"{annotation!r}"
            )
        fields.append(
            FieldSpec(
                name=var_name,
                annotation=annotation,
                description=description,
            ),
        )

    return fields, auto_vars


def _build_prompt_variables_classdef(
    *,
    prompt_name: str,
    class_name: str,
    fields: list[FieldSpec],
    auto_vars: dict[str, str],
) -> cst.ClassDef:
    """Assemble a ``cst.ClassDef`` for a generated PromptVariables class.

    Builds source as a templated string then parses it with libcst,
    so the output gets idiomatic PEP 8 spacing for free. Returns the
    class node only (the caller upserts it into an existing step
    file's module).

    Layout::

        class XxxPrompt(PromptVariables):
            \"\"\"Variables for the 'name' Phoenix prompt.

            AUTOGENERATED by ``llm-pipeline generate`` from
            ``llm-pipeline-prompts/{name}.yaml``. Hand edits to this
            class will be overwritten on the next ``generate`` run.
            \"\"\"
            <fields>
            <auto_vars assignment, if any>

    The AUTOGENERATED warning lives in the class docstring (not a
    module-level header) because the surrounding step file holds
    hand-written code (Inputs, Instructions, the Step class itself)
    and only THIS class is regenerated. Scoping the warning to the
    class makes the boundary visible to readers and to libcst-based
    edit ops.
    """
    lines: list[str] = []
    lines.append(f"class {class_name}(PromptVariables):")
    lines.append(
        f"    \"\"\"Variables for the {prompt_name!r} Phoenix prompt."
    )
    lines.append("")
    lines.append(
        "    AUTOGENERATED by ``llm-pipeline generate`` from"
    )
    lines.append(
        f"    ``llm-pipeline-prompts/{prompt_name}.yaml``. Hand edits "
        f"to this"
    )
    lines.append(
        "    class will be overwritten on the next ``generate`` run."
    )
    lines.append("    \"\"\"")

    if not fields and not auto_vars:
        lines.append("    pass")
    else:
        for f in fields:
            desc_literal = repr(f.description)
            lines.append(
                f"    {f.name}: {f.annotation} = "
                f"Field(description={desc_literal})"
            )
        if auto_vars:
            entries = ", ".join(
                f"{k!r}: {v!r}" for k, v in auto_vars.items()
            )
            lines.append(
                f"    auto_vars: ClassVar[dict[str, str]] = "
                f"{{{entries}}}"
            )

    lines.append("")  # trailing newline so parse_module accepts it
    source = "\n".join(lines)
    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001 — surface uniformly
        raise CodegenError(
            f"generated source for {prompt_name!r} failed to parse: "
            f"{exc}"
        ) from exc
    for stmt in module.body:
        if isinstance(stmt, cst.ClassDef) and stmt.name.value == class_name:
            return stmt
    raise CodegenError(
        f"internal: could not extract {class_name!r} ClassDef from "
        f"generated module"
    )


def _replace_classdef(
    module: cst.Module, class_name: str, new_class_def: cst.ClassDef,
) -> cst.Module:
    """Swap the existing ``class_name`` ClassDef with ``new_class_def``.

    Preserves the original class's ``leading_lines`` so the spacing
    between this class and its neighbours stays consistent on
    rewrite.
    """
    transformer = _ReplaceClassDef(class_name, new_class_def)
    new_module = module.visit(transformer)
    if not transformer.visited_target:
        raise CodegenError(
            f"_replace_classdef: class {class_name!r} not found "
            f"during visit (caller already verified existence — "
            f"internal error)"
        )
    if not isinstance(new_module, cst.Module):
        raise CodegenError(
            f"_replace_classdef returned a non-Module result "
            f"({type(new_module).__name__}); aborting"
        )
    return new_module


class _ReplaceClassDef(cst.CSTTransformer):
    """libcst transformer: replace a top-level ClassDef by name."""

    def __init__(self, class_name: str, new_class_def: cst.ClassDef) -> None:
        super().__init__()
        self.class_name = class_name
        self.new_class_def = new_class_def
        self.visited_target = False

    def leave_ClassDef(
        self,
        original_node: cst.ClassDef,
        updated_node: cst.ClassDef,
    ) -> cst.ClassDef:
        if original_node.name.value != self.class_name:
            return updated_node
        self.visited_target = True
        # Preserve the original class's leading_lines so we don't
        # collapse blank lines between this class and its neighbour.
        return self.new_class_def.with_changes(
            leading_lines=original_node.leading_lines,
        )


def _append_classdef(
    module: cst.Module, new_class_def: cst.ClassDef,
) -> cst.Module:
    """Append ``new_class_def`` to the end of ``module.body``.

    Two leading blank lines are added so the appended class is
    separated from whatever precedes it (PEP 8 spacing for top-
    level classes).
    """
    spaced = new_class_def.with_changes(
        leading_lines=[cst.EmptyLine(), cst.EmptyLine()],
    )
    return module.with_changes(body=list(module.body) + [spaced])


# Imports the upserted class needs. Keys are module / name pairs;
# values are predicates over (has_fields, has_auto_vars) deciding
# whether the import is required for the current call.
_PROMPT_VARIABLES_IMPORTS: list[tuple[str, str, Callable[[bool, bool], bool]]] = [
    ("pydantic", "Field", lambda has_fields, _: has_fields),
    ("typing", "ClassVar", lambda _, has_auto_vars: has_auto_vars),
    ("llm_pipeline.prompts", "PromptVariables", lambda *_: True),
]


def _ensure_prompt_variables_imports(
    module: cst.Module, *, has_fields: bool, has_auto_vars: bool,
) -> cst.Module:
    """Add any missing imports the upserted class depends on.

    Idempotent: imports already present (under any alias / order)
    are left alone. New imports are appended after the last existing
    top-level import; if there are none, prepended at the top.
    """
    needed: list[tuple[str, str]] = [
        (mod, name)
        for mod, name, predicate in _PROMPT_VARIABLES_IMPORTS
        if predicate(has_fields, has_auto_vars)
    ]
    missing = [
        (mod, name) for mod, name in needed
        if not _has_import(module, mod, name)
    ]
    if not missing:
        return module
    new_stmts: list[cst.BaseStatement] = [
        cst.parse_statement(f"from {mod} import {name}")  # type: ignore[arg-type]
        for mod, name in missing
    ]
    return _insert_imports(module, new_stmts)


def _has_import(module: cst.Module, module_path: str, name: str) -> bool:
    """True iff ``module`` already contains ``from module_path import name``.

    Matches structurally on the imported name (ignores alias). Misses
    bare ``import module_path`` style imports — those would only
    bring ``module_path`` into scope, not ``name``, so the caller
    still needs the ``from ... import name`` form.
    """
    for stmt in module.body:
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        for sub in stmt.body:
            if not isinstance(sub, cst.ImportFrom):
                continue
            if not isinstance(sub.module, (cst.Name, cst.Attribute)):
                continue
            if _attr_to_dotted(sub.module) != module_path:
                continue
            if isinstance(sub.names, cst.ImportStar):
                return True
            for alias in sub.names:
                if (
                    isinstance(alias, cst.ImportAlias)
                    and isinstance(alias.name, cst.Name)
                    and alias.name.value == name
                ):
                    return True
    return False


def _attr_to_dotted(node: cst.BaseExpression) -> str:
    """Render an ``Attribute`` chain (or ``Name``) back to its dotted path."""
    if isinstance(node, cst.Name):
        return node.value
    if isinstance(node, cst.Attribute):
        return f"{_attr_to_dotted(node.value)}.{node.attr.value}"
    return ""


def _insert_imports(
    module: cst.Module, new_stmts: list[cst.BaseStatement],
) -> cst.Module:
    """Insert ``new_stmts`` after the last existing top-level import.

    If the module has no imports yet, prepends them at the top
    (after a leading docstring if present).
    """
    body = list(module.body)
    last_import_idx = -1
    first_non_docstring_idx = 0
    for i, stmt in enumerate(body):
        if isinstance(stmt, cst.SimpleStatementLine):
            if any(
                isinstance(sub, (cst.Import, cst.ImportFrom))
                for sub in stmt.body
            ):
                last_import_idx = i
                continue
            # Bare docstring at top of file?
            if (
                i == 0
                and len(stmt.body) == 1
                and isinstance(stmt.body[0], cst.Expr)
                and isinstance(stmt.body[0].value, cst.SimpleString)
            ):
                first_non_docstring_idx = 1
                continue
        # First non-import / non-docstring statement: stop scanning.
        break
    insert_at = (last_import_idx + 1) if last_import_idx >= 0 else first_non_docstring_idx
    return module.with_changes(
        body=body[:insert_at] + new_stmts + body[insert_at:],
    )


# ---------------------------------------------------------------------------
# Code-body editing — Edit-tool / Write-tool style contracts
# ---------------------------------------------------------------------------


def edit_code_body(
    *,
    source_file: Path,
    class_name: str,
    method_name: str,
    old_source: str,
    new_source: str,
    root: Path | None = None,
    write_backup: bool = True,
) -> dict[str, Any]:
    """Replace ``{class_name}.{method_name}``'s body with ``new_source``,
    iff the current body matches ``old_source`` exactly.

    Mirrors the Edit-tool contract: caller passes its view of the
    current body (typically ``CodeBodySpec.source`` from a previously-
    loaded spec) plus the desired replacement. The current body is
    read from disk via :func:`llm_pipeline.cst_analysis.analyze_code_body`
    (which uses libcst position metadata to scope strictly to the
    target method's body line range) and compared verbatim against
    ``old_source``. A mismatch — caused by concurrent file edits,
    a stale spec, or analyser drift — raises :class:`CodegenError`
    rather than silently overwriting.

    On match, the body's line range is replaced with ``new_source``.
    The replacement is line-level; surrounding text (signature,
    decorators, neighbouring methods, blank lines, comments) is
    untouched.

    Path-guarded: ``source_file`` must resolve under ``root`` (or
    the configured ``LLM_PIPELINES_ROOT``). A ``.bak`` of the
    original is written next to the source when ``write_backup=True``
    (best-effort).

    Returns a summary::

        {
            "file": "absolute/path/to/file.py",
            "class": "ClassName",
            "method": "method_name",
            "old_lines": <int>,
            "new_lines": <int>,
        }

    Raises:
        :class:`CodegenError` on any failure — path outside root,
        file missing, class/method not found, ``old_source`` mismatch,
        unparseable input file, etc.
    """
    return _apply_code_body(
        source_file=source_file,
        class_name=class_name,
        method_name=method_name,
        new_source=new_source,
        old_source=old_source,
        root=root,
        write_backup=write_backup,
    )


def write_code_body(
    *,
    source_file: Path,
    class_name: str,
    method_name: str,
    new_source: str,
    root: Path | None = None,
    write_backup: bool = True,
) -> dict[str, Any]:
    """Replace ``{class_name}.{method_name}``'s body with ``new_source``
    unconditionally — no verification of the current body.

    Mirrors the Write-tool contract for cases where the caller
    intentionally overwrites without knowing or caring about the
    prior state — code generation, repair flows, initial seeding.
    Same path-guard / backup / line-level splice plumbing as
    :func:`edit_code_body`.

    Returns the same summary shape as :func:`edit_code_body`
    (``old_lines`` reports the count of lines actually replaced).
    """
    return _apply_code_body(
        source_file=source_file,
        class_name=class_name,
        method_name=method_name,
        new_source=new_source,
        old_source=None,
        root=root,
        write_backup=write_backup,
    )


def _apply_code_body(
    *,
    source_file: Path,
    class_name: str,
    method_name: str,
    new_source: str,
    old_source: str | None,
    root: Path | None,
    write_backup: bool,
) -> dict[str, Any]:
    """Shared core for :func:`edit_code_body` / :func:`write_code_body`.

    The only difference between the two is whether ``old_source`` is
    verified before the swap. Locating the body's line range,
    splicing, and writing are identical.
    """
    from llm_pipeline.cst_analysis import (
        AnalysisError,
        analyze_code_body,
    )
    from llm_pipeline.artifacts import CodeBodySpec

    resolved = _guard_or_raise(source_file, root)
    if not resolved.exists():
        raise CodegenError(f"source file does not exist: {resolved}")

    text = resolved.read_text(encoding="utf-8")

    try:
        spec: CodeBodySpec = analyze_code_body(
            source=text,
            function_qualname=f"{class_name}.{method_name}",
            resolver=lambda _module, _symbol: None,
        )
    except AnalysisError as exc:
        raise CodegenError(
            f"could not locate {class_name}.{method_name} in "
            f"{resolved}: {exc}"
        ) from exc

    if old_source is not None and spec.source != old_source:
        raise CodegenError(
            f"old_source does not match the current body of "
            f"{class_name}.{method_name} in {resolved}. The file may "
            f"have been modified since the spec was loaded; refetch "
            f"the spec and retry."
        )

    new_text = _splice_body(text, spec, new_source)

    # Backup before write — best-effort, non-blocking on failure.
    if write_backup:
        bak = resolved.with_suffix(resolved.suffix + ".bak")
        try:
            shutil.copy2(resolved, bak)
        except OSError:
            pass

    resolved.write_text(new_text, encoding="utf-8")

    return {
        "file": str(resolved),
        "class": class_name,
        "method": method_name,
        "old_lines": len(spec.source.splitlines(keepends=True)),
        "new_lines": len(new_source.splitlines(keepends=True)),
    }


def _splice_body(text: str, spec: "CodeBodySpec", new_source: str) -> str:  # noqa: F821
    """Replace the line range ``spec`` describes with ``new_source``.

    The original body occupies ``len(spec.source.splitlines(keepends=True))``
    lines starting at ``spec.line_offset_in_file`` (0-indexed).
    Everything outside that range — signature, decorators,
    neighbouring methods, surrounding text — passes through verbatim.

    Caller is responsible for newline consistency at the boundary:
    if the original body ended with a newline, ``new_source``
    typically should too; mirroring the Edit-tool contract.
    """
    lines = text.splitlines(keepends=True)
    start = spec.line_offset_in_file
    end = start + len(spec.source.splitlines(keepends=True))
    return "".join(lines[:start]) + new_source + "".join(lines[end:])


# ---------------------------------------------------------------------------
# Imports editing — structured, canonical-form rewrite
# ---------------------------------------------------------------------------


def render_import_block(block: "ImportBlock") -> str:  # noqa: F821
    """Render an :class:`ImportBlock` to canonical Python source.

    Always emits a single trailing newline. Multi-name ``import a, b``
    statements (rare; bad style) are split into separate lines —
    one ``import`` per artifact — as part of the canonicalisation.

    Examples::

        ImportBlock(module="x", artifacts=[a]) → "from x import a\\n"
        ImportBlock(module="x", artifacts=[a, b]) → "from x import a, b\\n"
        ImportBlock(module=None, artifacts=[a]) → "import a\\n"
        ImportBlock(module=None, artifacts=[a, b]) → "import a\\nimport b\\n"
        ImportArtifact(name="x", alias="y") → "x as y" (in either form)
    """
    if block.module is None:
        # Bare imports: one line per artifact.
        lines = []
        for art in block.artifacts:
            piece = f"import {art.name}"
            if art.alias:
                piece += f" as {art.alias}"
            lines.append(piece)
        return "\n".join(lines) + "\n"

    # ``from X import a, b, c[ as ...]``
    names: list[str] = []
    for art in block.artifacts:
        if art.alias:
            names.append(f"{art.name} as {art.alias}")
        else:
            names.append(art.name)
    return f"from {block.module} import {', '.join(names)}\n"


def _imports_line_range(text: str) -> tuple[int, int] | None:
    """Find the contiguous line range of top-level imports in ``text``.

    Returns ``(start, end)`` 0-indexed-inclusive-start /
    0-indexed-exclusive-end, or ``None`` if the file has no
    top-level imports. The range covers from the first import's
    first line to the last import's last line. Lines BETWEEN
    imports — blank lines, comments, or non-import statements —
    fall inside the range and are part of the section that
    :func:`write_imports` replaces (intentional canonicalisation:
    pipeline files end up with imports in one consistent block).
    """
    try:
        module = cst.parse_module(text)
    except Exception as exc:  # noqa: BLE001
        raise CodegenError(f"failed to parse source: {exc}") from exc

    wrapper = cst.MetadataWrapper(module, unsafe_skip_copy=True)
    positions = wrapper.resolve(cst.metadata.PositionProvider)

    first_line: int | None = None
    last_line: int | None = None
    for stmt in wrapper.module.body:
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        if not any(
            isinstance(s, (cst.Import, cst.ImportFrom)) for s in stmt.body
        ):
            continue
        pos = positions.get(stmt)
        if pos is None:
            continue
        if first_line is None:
            first_line = pos.start.line - 1  # 0-indexed
        last_line = pos.end.line  # libcst end.line is 1-indexed-inclusive,
                                  # so this is already exclusive in 0-index

    if first_line is None or last_line is None:
        return None
    return (first_line, last_line)


def edit_imports(
    *,
    source_file: Path,
    old_imports: list,
    new_imports: list,
    root: Path | None = None,
    write_backup: bool = True,
) -> dict[str, Any]:
    """Replace the file's imports section with ``new_imports``,
    iff the file's current imports match ``old_imports`` structurally.

    Edit-tool contract: ``old_imports`` is the caller's view of the
    file's imports (typically ``spec.imports`` from a previously-
    loaded artifact). The current imports are read from disk via
    :func:`llm_pipeline.cst_analysis.analyze_imports` and compared
    structurally — module + artifact names + aliases must match
    exactly. Issue lists, refs (resolver-derived), and line offsets
    are NOT part of the comparison; they're analyser-derived
    metadata that varies independently of source content.

    On match, the imports section's line range is replaced with
    canonical-form rendering of ``new_imports`` (one statement per
    line, no internal blank lines). Body of the file below the
    imports is untouched.

    Mismatch → :class:`CodegenError`, file unchanged. The UI flow
    treats this as a 409 Conflict and prompts the user to refresh
    the spec.
    """
    return _apply_imports(
        source_file=source_file,
        new_imports=new_imports,
        old_imports=old_imports,
        root=root,
        write_backup=write_backup,
    )


def write_imports(
    *,
    source_file: Path,
    new_imports: list,
    root: Path | None = None,
    write_backup: bool = True,
) -> dict[str, Any]:
    """Replace the file's imports section with ``new_imports``
    unconditionally — Write-tool contract, no verification of
    current state. Same canonicalisation + splice as
    :func:`edit_imports`.
    """
    return _apply_imports(
        source_file=source_file,
        new_imports=new_imports,
        old_imports=None,
        root=root,
        write_backup=write_backup,
    )


def _apply_imports(
    *,
    source_file: Path,
    new_imports: list,
    old_imports: list | None,
    root: Path | None,
    write_backup: bool,
) -> dict[str, Any]:
    """Shared core for :func:`edit_imports` / :func:`write_imports`."""
    from llm_pipeline.cst_analysis import (
        AnalysisError,
        analyze_imports,
    )

    resolved = _guard_or_raise(source_file, root)
    if not resolved.exists():
        raise CodegenError(f"source file does not exist: {resolved}")

    text = resolved.read_text(encoding="utf-8")

    if old_imports is not None:
        try:
            current = analyze_imports(
                source=text,
                resolver=lambda _module, _symbol: None,
            )
        except AnalysisError as exc:
            raise CodegenError(
                f"could not analyse imports in {resolved}: {exc}"
            ) from exc
        if not _imports_match_structurally(current, old_imports):
            raise CodegenError(
                f"old_imports does not match current imports in "
                f"{resolved}. The file may have been modified since "
                f"the spec was loaded; refetch the spec and retry."
            )

    line_range = _imports_line_range(text)

    new_section = "".join(render_import_block(b) for b in new_imports)

    if line_range is None:
        # No existing imports; for V1 we don't auto-insert at the top —
        # caller should arrange the file to have at least one import or
        # use a different op. (Adding header insertion is straightforward
        # but a separate concern.)
        if not new_imports:
            new_text = text  # nothing to do
        else:
            raise CodegenError(
                f"{resolved} has no top-level imports to replace. "
                f"V1 of write_imports requires an existing imports "
                f"section to splice into."
            )
    else:
        start, end = line_range
        lines = text.splitlines(keepends=True)
        new_text = "".join(lines[:start]) + new_section + "".join(lines[end:])

    if write_backup:
        bak = resolved.with_suffix(resolved.suffix + ".bak")
        try:
            shutil.copy2(resolved, bak)
        except OSError:
            pass

    resolved.write_text(new_text, encoding="utf-8")

    return {
        "file": str(resolved),
        "old_blocks": (
            len(old_imports) if old_imports is not None else None
        ),
        "new_blocks": len(new_imports),
    }


def _imports_match_structurally(
    current: list,
    expected: list,
) -> bool:
    """True iff ``current`` and ``expected`` describe the same imports.

    Compares only the structural fields — ``module``, ``artifacts``
    (each by ``name`` + ``alias``) — so analyser-derived metadata
    (refs, issues, line offsets) doesn't cause spurious mismatches.
    """
    if len(current) != len(expected):
        return False
    for cur, exp in zip(current, expected):
        if cur.module != exp.module:
            return False
        if len(cur.artifacts) != len(exp.artifacts):
            return False
        for ca, ea in zip(cur.artifacts, exp.artifacts):
            if ca.name != ea.name or ca.alias != ea.alias:
                return False
    return True
