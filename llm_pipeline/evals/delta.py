"""Apply instruction delta to a pydantic model class.

Pure, side-effect-free function that constructs a new pydantic model subclass
from a base class plus a JSON delta list. Used by the evals runner to produce
variant instruction schemas for LLM step execution.

Security constraints (ACE hygiene):
- Type resolution uses a HARD-CODED WHITELIST. No eval/exec, no importlib,
  no typing.get_type_hints, no dynamic resolution.
- Field names must match ``^[a-z_][a-z0-9_]*$`` — dunder / traversal / attribute
  injection rejected.
- ``op`` must be ``add`` or ``modify`` — any other value raises ValueError.
  ``remove`` is explicitly NOT supported in this v2 (removing inherited fields
  from LLMResultMixin subclasses breaks pydantic-ai output validation and
  downstream evaluator assumptions).
- Defaults must be JSON-serialisable structures (scalars, or arbitrarily
  nested lists/dicts with string keys). Callables, class references, sets,
  and other non-JSON objects are rejected by the json.dumps round-trip.
- Length caps on delta list (50), string fields (1000 chars), default
  JSON-encoded length (2000 chars), and total nested node count in defaults
  (1000) prevent resource exhaustion from malicious payloads.

Architectural invariants for future Docker-sandbox relocation:
- No I/O, no session, no global state.
- Only JSON-serialisable inputs; the output class itself stays in-process but
  can be reconstructed in a sandbox from the delta + base-class module path.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import create_model


# Whitelist of permitted type strings. Mapping to concrete Python type objects
# used by pydantic.create_model. Nothing else is resolvable — unknown strings
# raise ValueError.
_TYPE_WHITELIST: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "Optional[str]": Optional[str],  # type: ignore[dict-item]
    "Optional[int]": Optional[int],  # type: ignore[dict-item]
    "Optional[float]": Optional[float],  # type: ignore[dict-item]
    "Optional[bool]": Optional[bool],  # type: ignore[dict-item]
}

_FIELD_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")
# Dunder names (e.g. __class__, __init__) match the identifier regex but
# collide with Python's internal protocol slots. Reject separately.
_DUNDER_RE = re.compile(r"^__.*__$")

_MAX_DELTA_ITEMS = 50
_MAX_STRING_LEN = 1000
_MAX_DEFAULT_LEN = 2000
_MAX_DEFAULT_NODES = 1000

_ALLOWED_OPS = frozenset({"add", "modify"})
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _resolve_type(type_str: str) -> type:
    """Resolve a whitelisted type string to a Python type.

    Whitelist lookup ONLY. Never uses eval/exec/importlib/get_type_hints.
    """
    if not isinstance(type_str, str):
        raise ValueError(
            f"type_str must be a string, got {type(type_str).__name__}"
        )
    if len(type_str) > _MAX_STRING_LEN:
        raise ValueError(
            f"type_str exceeds max length {_MAX_STRING_LEN}"
        )
    if type_str not in _TYPE_WHITELIST:
        raise ValueError(
            f"type_str {type_str!r} not in whitelist. "
            f"Allowed: {sorted(_TYPE_WHITELIST)}"
        )
    return _TYPE_WHITELIST[type_str]


def _validate_default(default: Any) -> None:
    """Validate that a default value is safe to persist and apply.

    Accepts arbitrary JSON-compatible structures: scalars, or nested lists
    and dicts (string keys only) of any depth. Rejects anything else.

    ACE safeguards:
    - ``json.dumps`` round-trip rejects callables, class references, sets,
      custom objects, and non-string dict keys (raises TypeError).
    - Encoded-length cap (``_MAX_DEFAULT_LEN``, 2000 chars) bounds payload
      size.
    - Total node count cap (``_MAX_DEFAULT_NODES``, 1000) sums list items +
      dict entries recursively, preventing pathological deeply-nested or
      wide inputs.

    Note: Python tuples are permitted as inputs and treated as lists; the
    ``json.dumps`` round-trip serialises them identically to JSON arrays,
    so downstream storage sees a list either way.
    """
    # json.dumps rejects callables, sets, class refs, custom objects, and
    # non-string dict keys (e.g. {1: "a"} raises TypeError in strict mode).
    try:
        encoded = json.dumps(default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"default is not JSON-serialisable: {exc}") from exc

    if len(encoded) > _MAX_DEFAULT_LEN:
        raise ValueError(
            f"default JSON-encoded length {len(encoded)} exceeds max "
            f"{_MAX_DEFAULT_LEN}"
        )

    # Iterative walk: scalars, lists (any depth), dicts with string keys
    # (any depth). Anything else at any depth raises. Count every list item
    # and every dict entry toward the node budget.
    stack: list[Any] = [default]
    node_count = 0
    while stack:
        node = stack.pop()
        if isinstance(node, _SCALAR_TYPES):
            continue
        if isinstance(node, (list, tuple)):
            node_count += len(node)
            if node_count > _MAX_DEFAULT_NODES:
                raise ValueError(
                    f"default nested node count exceeds max "
                    f"{_MAX_DEFAULT_NODES}"
                )
            stack.extend(node)
            continue
        if isinstance(node, dict):
            node_count += len(node)
            if node_count > _MAX_DEFAULT_NODES:
                raise ValueError(
                    f"default nested node count exceeds max "
                    f"{_MAX_DEFAULT_NODES}"
                )
            for key, value in node.items():
                if not isinstance(key, str):
                    # json.dumps catches this too, but be explicit — if
                    # json.dumps ever changes, we still reject here.
                    raise ValueError("default dict keys must be strings")
                stack.append(value)
            continue
        raise ValueError(
            f"default contains unsupported type {type(node).__name__}; "
            f"only scalars, lists, and dicts (string keys) permitted "
            f"at any depth"
        )


def _validate_field_name(field: Any) -> str:
    """Validate a field name against the identifier regex."""
    if not isinstance(field, str):
        raise ValueError(
            f"field must be a string, got {type(field).__name__}"
        )
    if len(field) > _MAX_STRING_LEN:
        raise ValueError(f"field exceeds max length {_MAX_STRING_LEN}")
    if not _FIELD_NAME_RE.match(field):
        raise ValueError(
            f"field {field!r} is not a valid identifier. "
            f"Must match {_FIELD_NAME_RE.pattern}"
        )
    if _DUNDER_RE.match(field):
        raise ValueError(
            f"field {field!r} is not a valid identifier "
            f"(dunder names are reserved)"
        )
    return field


def apply_instruction_delta(
    base_cls: type,
    instructions_delta: list[dict],
) -> type:
    """Build a new pydantic model subclass by applying a delta to ``base_cls``.

    Args:
        base_cls: A pydantic BaseModel subclass (typically LLMResultMixin or a
            subclass thereof). Returned unchanged if ``instructions_delta`` is
            empty.
        instructions_delta: List of delta items. Each item is a dict with keys:
            - ``op``: ``"add"`` or ``"modify"`` (required).
            - ``field``: target field name (required, must match identifier
              regex).
            - ``type_str``: whitelisted type string. Required for ``add``;
              optional for ``modify`` (preserves existing annotation if
              omitted).
            - ``default``: optional default value. Must be JSON-serialisable:
              a scalar (str/int/float/bool/None), or any nested structure of
              lists and string-keyed dicts (any depth). Callables, class
              refs, sets, and non-string dict keys are rejected. Encoded
              length capped at 2000 chars; total nested node count capped
              at 1000.

    Returns:
        A new pydantic BaseModel subclass named ``VariantInstructions`` (or
        ``base_cls`` unchanged when delta is empty).

    Raises:
        ValueError: on any validation failure (unknown op, bad field name,
            unknown type_str, non-JSON default, list too long, etc.).
    """
    # Type check FIRST — reject non-list inputs (e.g. dict, str) before any
    # length-based early-return. An empty dict has ``len == 0`` and would
    # otherwise pass the no-op check, silently bypassing type validation.
    if instructions_delta is not None and not isinstance(instructions_delta, list):
        raise ValueError(
            f"instructions_delta must be a list, got "
            f"{type(instructions_delta).__name__}"
        )

    if instructions_delta is None or len(instructions_delta) == 0:
        return base_cls

    if len(instructions_delta) > _MAX_DELTA_ITEMS:
        raise ValueError(
            f"instructions_delta length {len(instructions_delta)} "
            f"exceeds max {_MAX_DELTA_ITEMS}"
        )

    existing_fields = getattr(base_cls, "model_fields", {}) or {}
    fields_dict: dict[str, tuple[Any, Any]] = {}

    for idx, item in enumerate(instructions_delta):
        if not isinstance(item, dict):
            raise ValueError(
                f"delta item {idx} must be a dict, got {type(item).__name__}"
            )

        op = item.get("op")
        if op not in _ALLOWED_OPS:
            raise ValueError(
                f"delta item {idx}: op must be one of "
                f"{sorted(_ALLOWED_OPS)}; got {op!r}"
            )

        field_name = _validate_field_name(item.get("field"))

        type_str = item.get("type_str")
        has_default = "default" in item
        default_value = item.get("default") if has_default else ...

        if has_default:
            _validate_default(default_value)

        if op == "add":
            if type_str is None:
                raise ValueError(
                    f"delta item {idx}: 'add' op requires type_str"
                )
            field_type = _resolve_type(type_str)
            if not has_default:
                # Pydantic requires either a default or Ellipsis for required;
                # for safety, all added fields must have an explicit default.
                raise ValueError(
                    f"delta item {idx}: 'add' op requires a default value"
                )
            fields_dict[field_name] = (field_type, default_value)
        else:  # modify
            if type_str is not None:
                field_type = _resolve_type(type_str)
            else:
                existing = existing_fields.get(field_name)
                if existing is None:
                    raise ValueError(
                        f"delta item {idx}: cannot modify field "
                        f"{field_name!r} — not present on base class "
                        f"{base_cls.__name__} and no type_str provided"
                    )
                field_type = existing.annotation
            if not has_default:
                raise ValueError(
                    f"delta item {idx}: 'modify' op requires a default value"
                )
            fields_dict[field_name] = (field_type, default_value)

    # pydantic.create_model builds a subclass; inherited methods
    # (e.g. create_failure) are preserved.
    return create_model(
        "VariantInstructions",
        __base__=base_cls,
        **fields_dict,
    )


def merge_variable_definitions(
    prod_defs: list | None,
    variant_defs: list | None,
) -> list:
    """Union variable_definitions lists by variable name; variant wins on conflict.

    Both inputs are lists of dicts with at minimum a ``name`` key (matching the
    shape persisted on ``Prompt.variable_definitions``). Either list may be
    ``None`` — a ``None`` + list case returns a shallow copy of the other; both
    ``None`` returns ``[]``.

    This function MUST NOT evaluate any ``auto_generate`` expression strings —
    registry-based resolution happens later at prompt rendering time. Pass-
    through only.

    Security: no eval/exec; pure data-structure merge. Relocatable into a
    future Docker sandbox layer with zero refactor.
    """
    if prod_defs is None and variant_defs is None:
        return []
    if prod_defs is None:
        return list(variant_defs or [])
    if variant_defs is None:
        return list(prod_defs or [])

    by_name: dict[str, dict] = {}
    for item in prod_defs:
        if isinstance(item, dict) and "name" in item:
            by_name[item["name"]] = item
    # Variant overrides prod on name collision.
    for item in variant_defs:
        if isinstance(item, dict) and "name" in item:
            by_name[item["name"]] = item
    return list(by_name.values())


def get_type_whitelist() -> list[str]:
    """Return the sorted list of allowed ``type_str`` values.

    Public accessor for the module-private ``_TYPE_WHITELIST``. Used by the
    API to expose the canonical whitelist to the frontend so the editor's
    type dropdown stays in sync with backend validation — single source of
    truth, no drift.
    """
    return sorted(_TYPE_WHITELIST.keys())


__all__ = [
    "apply_instruction_delta",
    "merge_variable_definitions",
    "get_type_whitelist",
]
