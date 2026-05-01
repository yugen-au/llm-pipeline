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
    TargetClassNotFoundError,
    collect_class_field_names,
    find_class,
)


__all__ = [
    "CodegenError",
    "apply_instructions_delta",
    "generate_prompt_variables",
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
    output_path: Path,
    root: Path | None = None,
) -> bool:
    """Generate a fresh ``_*.py`` PromptVariables file from YAML defs.

    The generated file is fully derived — it overwrites whatever was
    previously at ``output_path``. The leading docstring warns the
    reader not to hand-edit; the file lives under the ``_variables/``
    private folder convention to reinforce that.

    ``prompt_name`` is the snake_case Phoenix prompt name (e.g.
    ``"topic_extraction"``). The generated class name is its
    PascalCase form with the ``Prompt`` suffix appended (e.g.
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
    ``pass`` body (still useful — gives the registry an entry for
    a step whose ``prepare()`` returns ``[XxxPrompt()]``).

    Path-guarded: ``output_path`` must resolve under ``root`` (or
    ``LLM_PIPELINES_ROOT`` env var, default ``./llm_pipelines``).
    Idempotent: returns ``False`` if the existing file already
    matches the generated content (useful for ``llm-pipeline
    generate`` to skip clean files).

    Honors :func:`llm_pipeline._dry_run.dry_run_mode` — inside a
    dry-run scope the build + compare runs but the disk write is
    skipped. The return value still reflects "would-write", so the
    UI startup pre-flight can detect stale variables files without
    mutating the working tree.

    Returns:
        ``True`` if the file was written / would be written,
        ``False`` if the existing content already matched.

    Raises:
        :class:`CodegenError` on any failure — path outside root,
        invalid prompt_name, malformed variable_definitions, etc.
    """
    if not isinstance(prompt_name, str) or not prompt_name:
        raise CodegenError(
            f"prompt_name must be a non-empty string; got {prompt_name!r}"
        )

    resolved = _guard_or_raise(output_path, root)

    class_name = _snake_to_pascal(prompt_name) + "Prompt"

    fields, auto_vars = _split_variable_definitions(
        prompt_name, variable_definitions or {},
    )

    module = _build_prompt_variables_module(
        prompt_name=prompt_name,
        class_name=class_name,
        fields=fields,
        auto_vars=auto_vars,
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


_AUTOGEN_BANNER = (
    "AUTOGENERATED. DO NOT EDIT.\n"
    "\n"
    "Regenerated on each `uv run llm-pipeline generate` from the "
    "matching `llm-pipeline-prompts/{name}.yaml`. Hand edits will be "
    "overwritten on the next generate run."
)


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


def _build_prompt_variables_module(
    *,
    prompt_name: str,
    class_name: str,
    fields: list[FieldSpec],
    auto_vars: dict[str, str],
) -> cst.Module:
    """Assemble a ``cst.Module`` for a generated PromptVariables file.

    Builds source as a templated string then parses it with libcst,
    so the output gets idiomatic PEP 8 spacing (blank lines between
    import groups, two blank lines before the class) for free.

    Layout::

        \"\"\"AUTOGENERATED... \"\"\"
        from __future__ import annotations

        from typing import ClassVar          # only if auto_vars
        from pydantic import Field           # only if fields

        from llm_pipeline.prompts import PromptVariables


        class XxxPrompt(PromptVariables):
            \"\"\"Variables for the 'name' Phoenix prompt.\"\"\"

            <fields>
            <auto_vars assignment, if any>
    """
    lines: list[str] = []

    # Module docstring (matches existing template: docstring is
    # immediately followed by `from __future__`, no blank line).
    lines.append(f'"""{_AUTOGEN_BANNER}"""')
    lines.append("from __future__ import annotations")
    lines.append("")

    # Stdlib + third-party imports (one block, blank line after).
    stdlib_third_party: list[str] = []
    if auto_vars:
        stdlib_third_party.append("from typing import ClassVar")
    if fields:
        stdlib_third_party.append("from pydantic import Field")
    if stdlib_third_party:
        lines.extend(stdlib_third_party)
        lines.append("")

    # Local imports.
    lines.append("from llm_pipeline.prompts import PromptVariables")
    lines.append("")
    lines.append("")

    # Class definition.
    lines.append(f"class {class_name}(PromptVariables):")
    docstring = f'"""Variables for the {prompt_name!r} Phoenix prompt."""'
    lines.append(f"    {docstring}")

    if not fields and not auto_vars:
        lines.append("    pass")
    else:
        lines.append("")  # blank line between class docstring and members
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

    lines.append("")  # trailing newline so render is POSIX-clean

    source = "\n".join(lines)
    try:
        return cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001 — surface uniformly
        raise CodegenError(
            f"generated source for {prompt_name!r} failed to parse: "
            f"{exc}"
        ) from exc
