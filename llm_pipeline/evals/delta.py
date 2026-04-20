"""Apply instruction delta to a pydantic model class.

Pure, side-effect-free function that constructs a new pydantic model subclass
from a base class plus a JSON delta list. Used by the evals runner to produce
variant instruction schemas for LLM step execution.

Security constraints (ACE hygiene):
- Type resolution uses a HARD-CODED WHITELIST for scalars plus a
  REGISTRY-ONLY enum lookup (``enum:<Name>`` -> ``_AUTO_GENERATE_REGISTRY``).
  No eval/exec, no importlib, no typing.get_type_hints, no dynamic class
  resolution outside the trusted registry.
- Field names must match ``^[a-z_][a-z0-9_]*$`` — dunder / traversal / attribute
  injection rejected.
- Enum names must match ``^[A-Za-z_][A-Za-z0-9_]*$`` (Python identifier) and
  then be present in ``_AUTO_GENERATE_REGISTRY`` as an ``enum.Enum`` subclass.
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
- No I/O, no session, no global state (``_AUTO_GENERATE_REGISTRY`` is a
  trusted, process-local registry populated by the pipeline dev at startup).
- Only JSON-serialisable inputs; the output class itself stays in-process but
  can be reconstructed in a sandbox from the delta + base-class module path.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from pydantic import Field, create_model


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
# Enum names may start with uppercase (PascalCase convention) and must be
# valid Python identifiers before we touch the registry.
_ENUM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_MAX_DELTA_ITEMS = 50
_MAX_STRING_LEN = 1000
_MAX_DEFAULT_LEN = 2000
_MAX_DEFAULT_NODES = 1000

_ALLOWED_OPS = frozenset({"add", "modify"})
_SCALAR_TYPES = (str, int, float, bool, type(None))


def _is_enum_type(field_type: Any) -> bool:
    """True iff ``field_type`` is an enum class or ``Optional[enum]``.

    Used to decide whether to wrap the default in a ``Field(..., validate_default=True)``
    so pydantic coerces the member value to the enum member and rejects
    invalid values at class-creation time.
    """
    import enum as _enum
    import typing as _t

    if isinstance(field_type, type) and issubclass(field_type, _enum.Enum):
        return True
    # Optional[Enum] shows up as Union[Enum, None].
    origin = _t.get_origin(field_type)
    if origin is _t.Union:
        return any(
            isinstance(a, type) and issubclass(a, _enum.Enum)
            for a in _t.get_args(field_type)
        )
    return False


def _default_spec(field_type: Any, default_value: Any) -> Any:
    """Return the per-field default suitable for ``pydantic.create_model``.

    For enum-typed fields we wrap the default in ``Field(default=...,
    validate_default=True)`` so pydantic coerces the string value to the
    matching enum member at class creation (and raises ValidationError on
    mismatch — re-wrapped as ValueError by the caller). For all other types
    we pass the raw default through unchanged to preserve existing behaviour.
    """
    if _is_enum_type(field_type):
        return Field(default=default_value, validate_default=True)
    return default_value


def _resolve_enum(name: str) -> type:
    """Resolve an enum class from the auto_generate registry.

    Security: registry-only lookup. No ``importlib.import_module``, no
    ``getattr`` walks, no dynamic module resolution. The name must pass an
    identifier regex before we touch the registry so malformed input never
    reaches the lookup. Unknown names -> ValueError. Registered-but-not-enum
    objects (e.g. bare constants) are explicitly rejected so ``enum:Foo``
    can never resolve to a non-enum type.
    """
    # Lazy import avoids a module-level circular dependency risk between
    # evals.delta and prompts.variables.
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
    """Resolve a type string to a Python type.

    Supported formats:
    - Scalars: ``str``, ``int``, ``float``, ``bool``
    - Generic containers: ``list``, ``dict``
    - Optional scalar: ``Optional[str]``, ``Optional[int]``,
      ``Optional[float]``, ``Optional[bool]``
    - Enum (registry-resolved): ``enum:<RegisteredName>``
    - Optional enum: ``Optional[enum:<RegisteredName>]``

    Security: scalar forms use the hard-coded ``_TYPE_WHITELIST``; enum
    forms go through :func:`_resolve_enum`, which does a registry-only
    lookup (no eval/exec/importlib). Unknown strings -> ValueError.
    """
    if not isinstance(type_str, str):
        raise ValueError(
            f"type_str must be a string, got {type(type_str).__name__}"
        )
    if len(type_str) > _MAX_STRING_LEN:
        raise ValueError(
            f"type_str exceeds max length {_MAX_STRING_LEN}"
        )

    # Optional[enum:<Name>] — unwrap then recurse on the inner form so the
    # same enum resolution path runs for both bare and Optional enums.
    if type_str.startswith("Optional[enum:") and type_str.endswith("]"):
        inner = type_str[len("Optional["):-1]
        return Optional[_resolve_type(inner)]  # type: ignore[return-value]

    # enum:<Name> — registry-only lookup, no importlib.
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
            - ``type_str``: type string. Required for ``add``; optional for
              ``modify`` (preserves existing annotation if omitted). Supported:

                * Scalars: ``str``, ``int``, ``float``, ``bool``
                * Generics: ``list``, ``dict``
                * Optional scalar: ``Optional[str|int|float|bool]``
                * Enum (registry-resolved): ``enum:<RegisteredName>``
                * Optional enum: ``Optional[enum:<RegisteredName>]``

              Enum resolution is registry-only via
              ``_AUTO_GENERATE_REGISTRY`` — no importlib, no dynamic class
              lookup. Unknown or non-enum names raise ValueError.
            - ``default``: optional default value. Must be JSON-serialisable:
              a scalar (str/int/float/bool/None), or any nested structure of
              lists and string-keyed dicts (any depth). For enum-typed fields,
              pass the member value (e.g. ``"positive"``); the default is
              wrapped in ``Field(validate_default=True)`` so pydantic coerces
              the string to the matching enum member at model instantiation
              and raises ``ValidationError`` (a ``ValueError`` subclass) on
              mismatch. Callables, class refs, sets, and non-string dict
              keys are rejected. Encoded length capped at 2000 chars; total
              nested node count capped at 1000.

    Returns:
        A new pydantic BaseModel subclass named ``VariantInstructions`` (or
        ``base_cls`` unchanged when delta is empty).

    Raises:
        ValueError: on any validation failure (unknown op, bad field name,
            unknown type_str, non-JSON default, list too long, enum default
            not matching a registered member, etc.).
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

    # pydantic.create_model builds a subclass; inherited methods
    # (e.g. create_failure) are preserved. We delegate default-vs-type
    # validation (esp. enum member-value matching) to pydantic here —
    # _validate_default is intentionally type-agnostic.
    #
    # Error-surface consistency: pydantic raises ValidationError (a
    # ValueError subclass) for validate_default failures and PydanticUserError
    # for schema-construction problems. We re-wrap both so callers get a
    # single, human-readable ValueError regardless of which layer flagged the
    # mismatch.
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
        # Any other ValueError (e.g. raised by our own helpers below the
        # create_model call path, or future pydantic ValueError variants)
        # bubbles up unchanged so existing test expectations still match.
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
