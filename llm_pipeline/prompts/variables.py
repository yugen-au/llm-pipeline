"""
Prompt variable resolution: registry, protocol, and base class.

PromptVariables -- base class enforcing Field(description=...) on all fields.
register_prompt_variables() -- register a class for a (prompt_key, prompt_type) pair.
RegistryVariableResolver -- built-in resolver backed by the global registry.
VariableResolver -- protocol for custom resolvers (backward compat).
"""
from typing import Optional, Protocol, Type, runtime_checkable
from pydantic import BaseModel, ConfigDict
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
# Global prompt variables registry
# ---------------------------------------------------------------------------

_VARIABLE_REGISTRY: dict[tuple[str, str], Type[PromptVariables]] = {}


def register_prompt_variables(
    prompt_key: str, prompt_type: str, cls: Type[PromptVariables]
) -> None:
    """Register a PromptVariables class for a prompt key + type.

    Overwrites if already registered.
    """
    _VARIABLE_REGISTRY[(prompt_key, prompt_type)] = cls


def get_prompt_variables(
    prompt_key: str, prompt_type: str
) -> Type[PromptVariables] | None:
    """Look up registered variables class. Returns None if not registered."""
    return _VARIABLE_REGISTRY.get((prompt_key, prompt_type))


def get_all_prompt_variables() -> dict[tuple[str, str], Type[PromptVariables]]:
    """Return copy of all registered variable classes (for introspection)."""
    return dict(_VARIABLE_REGISTRY)


def clear_prompt_variables_registry() -> None:
    """Clear registry. Use in test teardown."""
    _VARIABLE_REGISTRY.clear()


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
    "get_all_prompt_variables",
    "clear_prompt_variables_registry",
]
