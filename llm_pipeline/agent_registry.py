"""
Base class for agent registries.

Defines the interface for declaring which output types a pipeline's agents produce.
Mirrors PipelineDatabaseRegistry pattern: registry = WHAT, runtime factory = HOW.
"""
from abc import ABC
from typing import ClassVar, Type

from pydantic import BaseModel


class AgentRegistry(ABC):
    """
    Base class for pipeline agent registries.

    Each pipeline should define its own registry class that inherits from this,
    declaring which pydantic-ai agents it uses and their output types.

    This registry is the single source of truth for:
    1. What agent step_names the pipeline defines
    2. What structured output type each agent produces

    Registry must be configured at class definition time using class call syntax:

    Example:
        class MyPipelineAgentRegistry(AgentRegistry, agents={
            "extract_rates": RateExtraction,
            "validate_lanes": LaneValidation,
        }):
            pass
    """

    AGENTS: ClassVar[dict[str, Type[BaseModel]]] = {}

    def __init_subclass__(cls, agents=None, **kwargs):
        """
        Called when a subclass is defined. Sets AGENTS from class parameter.

        Args:
            agents: Dict mapping step_name to output BaseModel type (required)
            **kwargs: Additional keyword arguments passed to super().__init_subclass__

        Raises:
            ValueError: If agents not provided for concrete registry
        """
        super().__init_subclass__(**kwargs)

        if agents is not None:
            cls.AGENTS = agents
        elif not cls.__name__.startswith('_') and cls.__bases__[0] is AgentRegistry:
            raise ValueError(
                f"{cls.__name__} must specify agents parameter when defining the class:\n"
                f'class {cls.__name__}(AgentRegistry, agents={{"step_name": OutputModel, ...}})'
            )

    @classmethod
    def get_output_type(cls, step_name: str) -> Type[BaseModel]:
        """
        Get the output type for a given step name.

        Args:
            step_name: The snake_case step name to look up

        Returns:
            The BaseModel subclass registered for this step

        Raises:
            KeyError: If step_name not found in registry
        """
        if step_name not in cls.AGENTS:
            raise KeyError(
                f"No agent registered for step '{step_name}' in {cls.__name__}. "
                f"Available steps: {list(cls.AGENTS.keys())}"
            )
        return cls.AGENTS[step_name]


__all__ = ["AgentRegistry"]
