"""
Variable resolver protocol for prompt variable resolution.

Allows host projects to provide custom variable resolution logic
without coupling the pipeline to specific variable class implementations.
"""
from typing import Optional, Protocol, Type, runtime_checkable
from pydantic import BaseModel


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
            provider=GeminiProvider(),
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


__all__ = ["VariableResolver"]
