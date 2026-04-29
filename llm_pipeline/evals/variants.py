"""Variant model + delta machinery for the eval system.

A ``Variant`` is a delta over production: any null/empty field means
"use production". The runner applies the delta to the live pipeline
at run time via ``PipelineDeps`` overrides; the acceptance helper
walks the same delta to upsert ``StepModelConfig`` rows, post Phoenix
prompt versions, and AST-rewrite instructions classes.

This module also owns the ``apply_instruction_delta`` machinery
previously in ``evals/delta.py``. The two are co-located so the type
whitelist + JSON-default validator live next to the type that
references them.

Security constraints (ACE hygiene) for ``apply_instruction_delta``:

- Type resolution uses a HARD-CODED WHITELIST for scalars plus a
  REGISTRY-ONLY enum lookup (``enum:<Name>`` -> ``_AUTO_GENERATE_REGISTRY``).
  No eval/exec, no importlib, no typing.get_type_hints, no dynamic class
  resolution outside the trusted registry.
- Field names must match ``^[a-z_][a-z0-9_]*$``. Dunder names rejected.
- Enum names must match ``^[A-Za-z_][A-Za-z0-9_]*$`` and resolve in
  ``_AUTO_GENERATE_REGISTRY`` to an ``enum.Enum`` subclass.
- ``op`` must be ``add`` or ``modify``. ``remove`` is intentionally
  unsupported (would break ``LLMResultMixin`` + downstream evaluator
  assumptions).
- Defaults must be JSON-serialisable structures. Length caps prevent
  resource exhaustion from malicious payloads.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import BaseModel, Field, create_model


# ---------------------------------------------------------------------------
# Variant model
# ---------------------------------------------------------------------------


class DeltaOp(BaseModel):
    """One element of a variant's ``instructions_delta`` list.

    Mirrors the dict shape consumed by :func:`apply_instruction_delta`.
    Surfaced as a typed model so the variant editor and the API layer
    share a single source of truth.
    """

    op: str  # "add" | "modify"
    field: str
    type_str: Optional[str] = None
    default: Any = None


class Variant(BaseModel):
    """A delta over production for a single eval run.

    Empty / null fields = use production. The baseline (no overrides)
    is ``Variant()``.

    Fields:
        model: Override the runtime model. ``None`` -> production
            ``StepModelConfig`` resolution applies.
        prompt_overrides: Map of step_name -> raw user-prompt template
            string. When set, ``LLMStepNode._run_llm`` skips the
            Phoenix prompt fetch and renders this template directly.
        instructions_delta: List of dict-shaped delta ops (the runtime
            uses dicts for backward compat with the existing
            ``apply_instruction_delta`` signature; ``DeltaOp`` is a
            convenience for typed callers).
    """

    model: Optional[str] = None
    prompt_overrides: dict[str, str] = Field(default_factory=dict)
    instructions_delta: list[dict[str, Any]] = Field(default_factory=list)

    def is_baseline(self) -> bool:
        """True iff the variant is fully empty (== production)."""
        return (
            self.model is None
            and not self.prompt_overrides
            and not self.instructions_delta
        )


# ---------------------------------------------------------------------------
# Type whitelist + delta application (formerly evals/delta.py)
# ---------------------------------------------------------------------------


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
_DUNDER_RE = re.compile(r"^__.*__$")
_ENUM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_MAX_DELTA_ITEMS = 50
_MAX_STRING_LEN = 1000
_MAX_DEFAULT_LEN = 2000
_MAX_DEFAULT_NODES = 1000

_ALLOWED_OPS = frozenset({"add", "modify"})
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _is_enum_type(field_type: Any) -> bool:
    import enum as _enum
    import typing as _t

    if isinstance(field_type, type) and issubclass(field_type, _enum.Enum):
        return True
    origin = _t.get_origin(field_type)
    if origin is _t.Union:
        return any(
            isinstance(a, type) and issubclass(a, _enum.Enum)
            for a in _t.get_args(field_type)
        )
    return False


def _default_spec(field_type: Any, default_value: Any) -> Any:
    if _is_enum_type(field_type):
        return Field(default=default_value, validate_default=True)
    return default_value


def _resolve_enum(name: str) -> type:
    import enum as _enum

    from llm_pipeline.prompts.variables import _AUTO_GENERATE_REGISTRY

    if not _ENUM_NAME_RE.match(name):
        raise ValueError(
            f"enum name {name!r} is not a valid identifier. "
            f"Must match {_ENUM_NAME_RE.pattern}"
        )

    obj = _AUTO_GENERATE_REGISTRY.get(name)
    if obj is None:
        raise ValueError(
            f"enum type {name!r} not registered. "
            f"Use register_auto_generate() or ensure llm_pipelines/enums/ "
            f"discovery has run."
        )
    if not (isinstance(obj, type) and issubclass(obj, _enum.Enum)):
        raise ValueError(
            f"{name!r} is registered but is not an enum "
            f"(got {type(obj).__name__})"
        )
    return obj


def _resolve_type(type_str: str) -> type:
    if not isinstance(type_str, str):
        raise ValueError(
            f"type_str must be a string, got {type(type_str).__name__}"
        )
    if len(type_str) > _MAX_STRING_LEN:
        raise ValueError(f"type_str exceeds max length {_MAX_STRING_LEN}")

    if type_str.startswith("Optional[enum:") and type_str.endswith("]"):
        inner = type_str[len("Optional["):-1]
        return Optional[_resolve_type(inner)]  # type: ignore[return-value]

    if type_str.startswith("enum:"):
        enum_name = type_str[len("enum:"):]
        return _resolve_enum(enum_name)

    if type_str not in _TYPE_WHITELIST:
        raise ValueError(
            f"type_str {type_str!r} not in whitelist. "
            f"Allowed: {sorted(_TYPE_WHITELIST)} (plus "
            f"'enum:<RegisteredName>' / 'Optional[enum:<RegisteredName>]')"
        )
    return _TYPE_WHITELIST[type_str]


def _validate_default(default: Any) -> None:
    try:
        encoded = json.dumps(default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"default is not JSON-serialisable: {exc}") from exc

    if len(encoded) > _MAX_DEFAULT_LEN:
        raise ValueError(
            f"default JSON-encoded length {len(encoded)} exceeds max "
            f"{_MAX_DEFAULT_LEN}"
        )

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
                    raise ValueError("default dict keys must be strings")
                stack.append(value)
            continue
        raise ValueError(
            f"default contains unsupported type {type(node).__name__}; "
            f"only scalars, lists, and dicts (string keys) permitted "
            f"at any depth"
        )


def _validate_field_name(field: Any) -> str:
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
    instructions_delta: list[dict] | None,
) -> type:
    """Build a new pydantic model subclass by applying a delta to ``base_cls``.

    Returns ``base_cls`` unchanged when the delta is empty or ``None``.
    See module docstring for full security constraints + supported
    op/type/default shapes.
    """
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
                raise ValueError(
                    f"delta item {idx}: 'add' op requires a default value"
                )
            fields_dict[field_name] = (
                field_type, _default_spec(field_type, default_value),
            )
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
            fields_dict[field_name] = (
                field_type, _default_spec(field_type, default_value),
            )

    from pydantic import ValidationError as _PydValidationError

    try:
        return create_model(
            "VariantInstructions",
            __base__=base_cls,
            **fields_dict,
        )
    except _PydValidationError as exc:
        raise ValueError(
            f"default value(s) failed type validation during variant "
            f"instructions build: {exc}. For enum fields, the default must "
            f"match a registered member value."
        ) from exc
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"failed to build VariantInstructions from delta: {exc}. "
            f"Check that defaults match their declared types "
            f"(e.g. enum defaults must be a registered member value)."
        ) from exc


def merge_variable_definitions(
    prod_defs: list | None,
    variant_defs: list | None,
) -> list:
    """Union variable_definitions lists by name; variant wins on conflict.

    See historical ``evals.delta.merge_variable_definitions`` for the
    full contract — preserved here so callers don't need to chase the
    consolidation.
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
    for item in variant_defs:
        if isinstance(item, dict) and "name" in item:
            by_name[item["name"]] = item
    return list(by_name.values())


def get_type_whitelist() -> list[str]:
    """Sorted list of allowed ``type_str`` values; powers the variant editor."""
    return sorted(_TYPE_WHITELIST.keys())


__all__ = [
    "Variant",
    "DeltaOp",
    "apply_instruction_delta",
    "merge_variable_definitions",
    "get_type_whitelist",
]
