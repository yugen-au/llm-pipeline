"""
Prompt variable resolution: registry, protocol, and base class.

Two registries:
- _CODE_REGISTRY: classes registered via register_prompt_variables() (code-defined)
- _VARIABLE_REGISTRY: active classes used at runtime (may be merged from code + DB)

rebuild_from_db() merges DB variable_definitions with code-defined classes
using pydantic's create_model, preserving default_factory fields from code.
"""
from typing import Optional, Protocol, Type, runtime_checkable
from pydantic import BaseModel, ConfigDict, Field, create_model
from pydantic.fields import FieldInfo


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

TYPE_MAP: dict[str, type] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
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
    """Clear both registries. Use in test teardown."""
    _CODE_REGISTRY.clear()
    _VARIABLE_REGISTRY.clear()


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
        # If code already defines this field with a default_factory, preserve it
        if name in fields and code_cls:
            code_field = code_cls.model_fields.get(name)
            if code_field and code_field.default_factory is not None:
                # Keep default_factory, update description only
                fields[name] = (
                    py_type,
                    Field(
                        description=defn.get("description", code_field.description or ""),
                        default_factory=code_field.default_factory,
                    ),
                )
                continue
        fields[name] = (py_type, Field(description=defn.get("description", "")))

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
]
