"""
Prompt variable resolution: registry, protocol, and base class.

Two registries:
- _CODE_REGISTRY: classes registered via register_prompt_variables() (code-defined)
- _VARIABLE_REGISTRY: active classes used at runtime (may be merged from code + DB)

rebuild_from_db() merges DB variable_definitions with code-defined classes
using pydantic's create_model, preserving default_factory fields from code.
auto_generate expressions (e.g. enum_values(X)) are evaluated at runtime
to produce default_factory callables.
"""
import importlib
import logging
import re
from typing import Callable, Optional, Protocol, Type, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo

logger = logging.getLogger(__name__)


class PromptVariables(BaseModel):
    """Base class for typed prompt variable collections.

    All fields must use Field(description="...") for self-documenting variables.
    Validates at class definition time via __init_subclass__.

    Example:
        class SentimentSystemVars(PromptVariables):
            text: str = Field(description="Input text to analyze")
            max_length: int = Field(description="Max response length")
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if cls.__name__ == 'PromptVariables':
            return
        for field_name in getattr(cls, '__annotations__', {}):
            if field_name.startswith('_'):
                continue
            if field_name in cls.__dict__:
                field_value = cls.__dict__[field_name]
                if not isinstance(field_value, FieldInfo):
                    raise ValueError(
                        f"{cls.__name__}.{field_name} must use Field() definition"
                    )
                if not field_value.description:
                    raise ValueError(
                        f"{cls.__name__}.{field_name} must have Field(description='...')"
                    )


# ---------------------------------------------------------------------------
# Dual registry: code-defined + active (possibly merged)
# ---------------------------------------------------------------------------

_CODE_REGISTRY: dict[tuple[str, str], Type[PromptVariables]] = {}
_VARIABLE_REGISTRY: dict[tuple[str, str], Type[PromptVariables]] = {}

# ---------------------------------------------------------------------------
# auto_generate: registry, parser, resolver, factory builder
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
    """Parse 'func_name(arg1, arg2)' -> ('func_name', ['arg1', 'arg2']).

    Raises ValueError on unrecognized expression format.
    """
    m = _EXPR_PATTERN.match(expr.strip())
    if not m:
        raise ValueError(f"Unrecognized auto_generate expression: {expr!r}")
    return m.group(1), [a.strip() for a in m.group(2).split(",")]


def _resolve_object(name: str, import_path: str | None, expr_type: str) -> object:
    """Resolve a named object via registry -> import_path -> convention.

    Args:
        name: Object name (e.g. 'SemanticType')
        import_path: Explicit dotted path (e.g. 'my_project.enums.SemanticType')
        expr_type: Expression function name, determines convention submodule
    """
    # Tier 1: Registry
    if name in _AUTO_GENERATE_REGISTRY:
        return _AUTO_GENERATE_REGISTRY[name]

    # Tier 2: Explicit import_path
    if import_path:
        module_path, _, attr = import_path.rpartition(".")
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)

    # Tier 3: Convention (base_path + submodule)
    if _AUTO_GENERATE_BASE_PATH:
        submodule = "enums" if expr_type.startswith("enum") else "constants"
        full_path = f"{_AUTO_GENERATE_BASE_PATH}.{submodule}"
        try:
            mod = importlib.import_module(full_path)
            return getattr(mod, name)
        except (ImportError, AttributeError):
            pass

    raise ValueError(
        f"Cannot resolve '{name}' for auto_generate. "
        f"Register via register_auto_generate(), provide import_path, "
        f"or set base_path via set_auto_generate_base_path()."
    )


def _build_auto_generate_factory(
    expr: str, import_path: str | None = None,
) -> Callable[[], str]:
    """Build a default_factory callable from an auto_generate expression.

    Resolution is lazy (at call time), so registrations can happen after
    rebuild_from_db().
    """
    func_name, args = _parse_auto_generate(expr)

    if func_name == "enum_values":
        name = args[0]

        def factory(
            _name=name, _import_path=import_path, _fn=func_name,
        ) -> str:
            obj = _resolve_object(_name, _import_path, _fn)
            return ", ".join(str(e.value) for e in obj)

        return factory

    if func_name == "enum_names":
        name = args[0]

        def factory(
            _name=name, _import_path=import_path, _fn=func_name,
        ) -> str:
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


TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "enum": str,  # enum variables resolve to str for prompt substitution
}


def register_prompt_variables(
    prompt_key: str, prompt_type: str, cls: Type[PromptVariables]
) -> None:
    """Register a code-defined PromptVariables class.

    Stored in both code registry (immutable source) and active registry.
    """
    _CODE_REGISTRY[(prompt_key, prompt_type)] = cls
    _VARIABLE_REGISTRY[(prompt_key, prompt_type)] = cls


def get_prompt_variables(
    prompt_key: str, prompt_type: str
) -> Type[PromptVariables] | None:
    """Get the active (possibly merged) variables class."""
    return _VARIABLE_REGISTRY.get((prompt_key, prompt_type))


def get_code_prompt_variables(
    prompt_key: str, prompt_type: str
) -> Type[PromptVariables] | None:
    """Get the original code-defined class (before any DB merge)."""
    return _CODE_REGISTRY.get((prompt_key, prompt_type))


def get_all_prompt_variables() -> dict[tuple[str, str], Type[PromptVariables]]:
    """Return copy of all active variable classes (for introspection)."""
    return dict(_VARIABLE_REGISTRY)


def clear_prompt_variables_registry() -> None:
    """Clear all registries. Use in test teardown."""
    _CODE_REGISTRY.clear()
    _VARIABLE_REGISTRY.clear()
    clear_auto_generate_registry()


def rebuild_from_db(
    prompt_key: str, prompt_type: str, variable_definitions: dict
) -> Type[PromptVariables]:
    """Create/update a PromptVariables class from DB definitions.

    Merges with code-registered class (if any) to preserve default_factory
    fields. DB definitions override type/description for matching fields
    and add new simple fields.

    Registers the merged class as active in _VARIABLE_REGISTRY.
    """
    code_cls = _CODE_REGISTRY.get((prompt_key, prompt_type))

    # Collect fields: start with code, override/extend from DB
    fields: dict[str, tuple[type, FieldInfo]] = {}

    if code_cls:
        for name, field_info in code_cls.model_fields.items():
            fields[name] = (field_info.annotation, field_info)

    for name, defn in variable_definitions.items():
        py_type = TYPE_MAP.get(defn.get("type", "str"), str)
        desc = defn.get("description", "")

        # auto_generate expression -> default_factory
        auto_gen = defn.get("auto_generate")
        if auto_gen:
            try:
                factory = _build_auto_generate_factory(
                    auto_gen, defn.get("import_path"),
                )
                fields[name] = (
                    py_type,
                    Field(description=desc, default_factory=factory),
                )
                continue
            except ValueError:
                logger.warning(
                    "Failed auto_generate for %s.%s: %s",
                    prompt_key, name, auto_gen,
                    exc_info=True,
                )
                # fall through to simple field / code preservation

        # If code already defines this field with a default_factory, preserve it
        if name in fields and code_cls:
            code_field = code_cls.model_fields.get(name)
            if code_field and code_field.default_factory is not None:
                fields[name] = (
                    py_type,
                    Field(
                        description=desc or code_field.description or "",
                        default_factory=code_field.default_factory,
                    ),
                )
                continue
        fields[name] = (py_type, Field(description=desc))

    safe_name = f"{prompt_key}_{prompt_type}_vars".replace(".", "_")
    merged = create_model(safe_name, **fields)  # type: ignore[call-overload]

    _VARIABLE_REGISTRY[(prompt_key, prompt_type)] = merged  # type: ignore[assignment]
    return merged  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Built-in resolver backed by registry
# ---------------------------------------------------------------------------


class RegistryVariableResolver:
    """Built-in VariableResolver backed by the global prompt variables registry.

    Used as default when no custom resolver is passed to PipelineConfig.
    """

    def resolve(
        self, prompt_key: str, prompt_type: str
    ) -> Type[BaseModel] | None:
        return get_prompt_variables(prompt_key, prompt_type)


# ---------------------------------------------------------------------------
# Protocol (backward compat for custom resolvers)
# ---------------------------------------------------------------------------


@runtime_checkable
class VariableResolver(Protocol):
    """Protocol for resolving prompt variable classes.

    The built-in RegistryVariableResolver handles most cases. Implement
    this protocol only if you need custom resolution logic.
    """

    def resolve(
        self, prompt_key: str, prompt_type: str
    ) -> Optional[Type[BaseModel]]:
        ...


__all__ = [
    "PromptVariables",
    "VariableResolver",
    "RegistryVariableResolver",
    "register_prompt_variables",
    "get_prompt_variables",
    "get_code_prompt_variables",
    "get_all_prompt_variables",
    "clear_prompt_variables_registry",
    "rebuild_from_db",
    "register_auto_generate",
    "set_auto_generate_base_path",
    "clear_auto_generate_registry",
]
