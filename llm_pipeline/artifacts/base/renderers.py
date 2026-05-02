"""Per-sub-component source renderers — spec → Python text fragments.

Each function takes one ``ArtifactField`` instance (or a small bit of
context) and returns a Python source-code string. Writers compose
these fragments into per-kind files via :class:`ArtifactTemplate`.

Pure functions — no state, no side-effects, no Jinja awareness.
:class:`ArtifactTemplate` exposes them as Jinja filters via
:func:`default_jinja_env`.

Adding a new ``ArtifactField`` subclass = add one renderer here +
register it as a Jinja filter in :func:`default_jinja_env`.
"""
from __future__ import annotations

import textwrap
from typing import Any

from llm_pipeline.artifacts.base import (
    ArtifactRef,
    ImportArtifact,
    ImportBlock,
)
from llm_pipeline.artifacts.base.blocks import (
    CodeBodySpec,
    JsonSchemaWithRefs,
)


__all__ = [
    "render_artifact_ref",
    "render_code_body",
    "render_import",
    "render_pydantic_class",
    "schema_to_annotation",
]


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


def render_import(block: ImportBlock) -> str:
    """Render one :class:`ImportBlock` to a single source line.

    - ``from X import a, b as c`` for ``ImportFrom``-shaped blocks
      (``module`` set).
    - ``import X`` / ``import X as Y`` for bare imports
      (``module`` is ``None``; each artifact carries the dotted path).
    """
    parts = [_render_import_artifact(a) for a in block.artifacts if a.name]
    if not parts:
        return ""
    if block.module:
        return f"from {block.module} import {', '.join(parts)}"
    return "\n".join(f"import {p}" for p in parts)


def _render_import_artifact(artifact: ImportArtifact) -> str:
    if artifact.alias:
        return f"{artifact.name} as {artifact.alias}"
    return artifact.name


# ---------------------------------------------------------------------------
# Refs
# ---------------------------------------------------------------------------


def render_artifact_ref(ref: ArtifactRef) -> str:
    """Render an :class:`ArtifactRef` as the bare Python identifier.

    The source-side spelling (``ref.name``) is what appears in code;
    the resolver-populated ``ref`` field is metadata for the UI, not
    the rendered output.
    """
    return ref.name


# ---------------------------------------------------------------------------
# Code bodies
# ---------------------------------------------------------------------------


def render_code_body(
    body: CodeBodySpec,
    *,
    signature: str,
    indent: str = "    ",
) -> str:
    """Render a :class:`CodeBodySpec` as a function definition.

    ``signature`` is the function's full ``def name(...) -> X:`` line
    (caller knows the kind-specific shape — ``def run(self, ctx)``,
    ``def prepare(self, inputs)``, etc.). The body is dedented then
    re-indented under ``indent``.
    """
    body_text = textwrap.dedent(body.source.rstrip())
    indented = textwrap.indent(body_text, indent) if body_text else f"{indent}pass"
    return f"{signature}\n{indented}"


# ---------------------------------------------------------------------------
# Pydantic-shaped classes
# ---------------------------------------------------------------------------


def render_pydantic_class(
    *,
    name: str,
    schema: JsonSchemaWithRefs,
    base: str = "BaseModel",
    indent: str = "    ",
) -> str:
    """Render a Pydantic-style class declaration.

    Walks ``schema.json_schema["properties"]`` and emits one
    ``field: type = default`` line per property. For each field:

    1. If ``schema.field_source[field]`` exists, the original
       annotation text is used verbatim — round-tripping the user's
       exact syntax (``Annotated[...]``, qualified types, etc.).
    2. Otherwise, the annotation is derived from the JSON schema via
       :func:`schema_to_annotation`. Lossy for non-primitive shapes;
       the user can hand-edit if the inference is wrong.

    Defaults follow the same logic — JSON schema's ``default`` →
    Python literal — but the source-side default expression isn't
    captured in V1, so any non-trivial default re-renders from the
    JSON form.
    """
    props: dict[str, dict[str, Any]] = (schema.json_schema or {}).get(
        "properties", {},
    ) or {}
    required = set((schema.json_schema or {}).get("required", []) or [])

    lines = [f"class {name}({base}):"]
    description = schema.description.strip() if schema.description else ""
    if description:
        lines.append(f'{indent}"""{description}"""')
        lines.append("")

    if not props:
        lines.append(f"{indent}pass")
        return "\n".join(lines)

    for field_name, prop in props.items():
        annotation = (
            schema.field_source.get(field_name)
            or schema_to_annotation(prop)
        )
        default_expr = _default_expr(prop, field_name in required)
        if default_expr is None:
            lines.append(f"{indent}{field_name}: {annotation}")
        else:
            lines.append(f"{indent}{field_name}: {annotation} = {default_expr}")

    return "\n".join(lines)


def _default_expr(prop: dict[str, Any], required: bool) -> str | None:
    """Return the Python-source default for one JSON-schema property.

    ``None`` means "no default" (i.e. the field is required and we
    omit the ``= ...`` segment). Required fields without a default
    produce ``None``; optional fields fall back to ``= None``.
    """
    if "default" in prop:
        return repr(prop["default"])
    if not required:
        return "None"
    return None


# ---------------------------------------------------------------------------
# JSON-Schema-to-Python annotation (best-effort fallback)
# ---------------------------------------------------------------------------


_SIMPLE_TYPE_MAP: dict[str, str] = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "null": "None",
}


def schema_to_annotation(prop: dict[str, Any]) -> str:
    """Best-effort JSON-Schema → Python-annotation translator.

    Handles primitives, ``list``, ``dict[str, ...]``, ``X | None``
    (``anyOf``), and bare ``$ref`` (uses the last path segment). For
    anything more exotic, returns ``"Any"`` and lets the user hand-
    edit the rendered annotation.

    This is the fallback path. The primary path uses
    :attr:`JsonSchemaWithRefs.field_source` to round-trip the
    original annotation text.
    """
    if not prop:
        return "Any"

    if "$ref" in prop:
        # ``"#/$defs/Foo"`` → ``Foo``
        return prop["$ref"].rsplit("/", 1)[-1]

    if "anyOf" in prop:
        arms = prop["anyOf"]
        rendered = [schema_to_annotation(arm) for arm in arms]
        # ``str | None`` is the typical Optional shape.
        return " | ".join(rendered)

    schema_type = prop.get("type")
    if isinstance(schema_type, list):
        # ``["string", "null"]`` → ``str | None``
        return " | ".join(_SIMPLE_TYPE_MAP.get(t, "Any") for t in schema_type)

    if schema_type in _SIMPLE_TYPE_MAP:
        return _SIMPLE_TYPE_MAP[schema_type]

    if schema_type == "array":
        inner = schema_to_annotation(prop.get("items", {}))
        return f"list[{inner}]"

    if schema_type == "object":
        additional = prop.get("additionalProperties")
        if isinstance(additional, dict):
            return f"dict[str, {schema_to_annotation(additional)}]"
        return "dict[str, Any]"

    return "Any"
