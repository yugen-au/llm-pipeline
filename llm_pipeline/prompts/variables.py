"""
Variable resolver protocol for prompt variable resolution.

Allows host projects to provide custom variable resolution logic
without coupling the pipeline to specific variable class implementations.
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


@runtime_checkable
class VariableResolver(Protocol):
    """
    Protocol for resolving prompt variable classes.

    Host projects implement this to provide their specific prompt variable
    classes (e.g., get_variable_class from logistics-intelligence).

    Example:
        class MyVariableResolver:
            def resolve(self, prompt_key: str, prompt_type: str) -> Type[BaseModel] | None:
                # Look up variable class for this prompt
                return my_variable_registry.get(prompt_key, prompt_type)

        pipeline = MyPipeline(
            model='google-gla:gemini-2.0-flash-lite',
            variable_resolver=MyVariableResolver()
        )
    """

    def resolve(
        self, prompt_key: str, prompt_type: str
    ) -> Optional[Type[BaseModel]]:
        """
        Resolve a prompt key and type to a variable class.

        Args:
            prompt_key: The prompt key (e.g., 'semantic_mapping.system_instruction')
            prompt_type: The prompt type ('system' or 'user')

        Returns:
            A Pydantic BaseModel subclass for the variables, or None if not found
        """
        ...


__all__ = ["PromptVariables", "VariableResolver"]
