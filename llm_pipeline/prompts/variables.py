"""``auto_generate`` registry and expression evaluator.

Phase E: the framework no longer maintains a per-prompt
``PromptVariables`` registry — variable shapes come from each step's
``StepInputs`` class. The runtime expression evaluator
(``enum_values(X)``, ``enum_names(X)``, ``enum_value(X, MEMBER)``,
``constant(value)``) lives on, since it's used by the prompts UI
when computing default text snippets for variables.
"""
from __future__ import annotations

import importlib
import logging
import re
from typing import Callable

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# auto_generate registry
# ---------------------------------------------------------------------------


_AUTO_GENERATE_REGISTRY: dict[str, object] = {}
_AUTO_GENERATE_BASE_PATH: str | None = None

_EXPR_PATTERN = re.compile(
    r"^(enum_values|enum_names|enum_value|constant)\((.+)\)$"
)


def register_auto_generate(name: str, obj: object) -> None:
    """Register a Python object (enum, constant) for auto_generate expressions."""
    _AUTO_GENERATE_REGISTRY[name] = obj


def set_auto_generate_base_path(base_path: str | None) -> None:
    """Set the base module path for convention-based object resolution."""
    global _AUTO_GENERATE_BASE_PATH
    _AUTO_GENERATE_BASE_PATH = base_path


def clear_auto_generate_registry() -> None:
    """Clear auto_generate registry and base path. For test teardown."""
    global _AUTO_GENERATE_BASE_PATH
    _AUTO_GENERATE_REGISTRY.clear()
    _AUTO_GENERATE_BASE_PATH = None


def _parse_auto_generate(expr: str) -> tuple[str, list[str]]:
    """Parse ``func_name(arg1, arg2)`` -> ``(func_name, [arg1, arg2])``."""
    m = _EXPR_PATTERN.match(expr.strip())
    if not m:
        raise ValueError(f"Unrecognized auto_generate expression: {expr!r}")
    return m.group(1), [a.strip() for a in m.group(2).split(",")]


def _resolve_object(name: str, import_path: str | None, expr_type: str) -> object:
    """Resolve a named object via registry -> import_path -> convention."""
    if name in _AUTO_GENERATE_REGISTRY:
        return _AUTO_GENERATE_REGISTRY[name]

    if import_path:
        module_path, _, attr = import_path.rpartition(".")
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    if _AUTO_GENERATE_BASE_PATH:
        submodule = "enums" if expr_type.startswith("enum") else "constants"
        full_path = f"{_AUTO_GENERATE_BASE_PATH}.{submodule}"
        try:
            mod = importlib.import_module(full_path)
            return getattr(mod, name)
        except (ImportError, AttributeError):
            pass

    raise ValueError(
        f"Cannot resolve {name!r} for auto_generate. Register via "
        f"register_auto_generate(), provide import_path, or set "
        f"base_path via set_auto_generate_base_path()."
    )


def build_auto_generate_factory(
    expr: str, import_path: str | None = None,
) -> Callable[[], str]:
    """Build a callable that resolves an ``auto_generate`` expression at call time."""
    func_name, args = _parse_auto_generate(expr)

    if func_name == "enum_values":
        name = args[0]

        def factory(_name=name, _import_path=import_path, _fn=func_name) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return ", ".join(str(e.value) for e in obj)

        return factory

    if func_name == "enum_names":
        name = args[0]

        def factory(_name=name, _import_path=import_path, _fn=func_name) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return ", ".join(e.name for e in obj)

        return factory

    if func_name == "enum_value":
        if len(args) != 2:
            raise ValueError(
                f"enum_value requires 2 args (EnumName, MEMBER), got {len(args)}"
            )
        name, member = args[0], args[1]

        def factory(
            _name=name, _member=member, _import_path=import_path, _fn=func_name,
        ) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return str(obj[_member].value)

        return factory

    if func_name == "constant":
        value = args[0]

        def factory(_value=value) -> str:
            return _value

        return factory

    raise ValueError(f"Unknown auto_generate function: {func_name}")


__all__ = [
    "register_auto_generate",
    "set_auto_generate_base_path",
    "clear_auto_generate_registry",
    "build_auto_generate_factory",
]
