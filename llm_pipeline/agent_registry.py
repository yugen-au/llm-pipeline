"""
Base class for agent registries.

Defines the interface for declaring which output types a pipeline's agents produce.
Mirrors PipelineDatabaseRegistry pattern: registry = WHAT, runtime factory = HOW.
"""
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, ClassVar, Type

from pydantic import BaseModel


@dataclass
class AgentSpec:
    """Specification for a pipeline agent, bundling output type with optional tools.

    Use this instead of a bare Type[BaseModel] in AGENTS dict when tools are needed.

    Example:
        class MyRegistry(AgentRegistry, agents={
            "simple_step": SimpleOutput,                          # bare type (no tools)
            "tool_step": AgentSpec(ToolOutput, tools=[my_func]),  # with tools
        }):
            pass
    """
    output_type: Type[BaseModel]
    tools: list[Any] = field(default_factory=list)


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

    AGENTS: ClassVar[dict[str, Type[BaseModel] | AgentSpec]] = {}

    def __init_subclass__(cls, agents=None, **kwargs):
        """
        Called when a subclass is defined. Sets AGENTS from class parameter.

        Args:
            agents: Dict mapping step_name to either a bare Type[BaseModel] or an
                AgentSpec(output_type, tools) for steps that need tool-calling support.
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

        Normalizes both bare Type[BaseModel] and AgentSpec entries.

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
        entry = cls.AGENTS[step_name]
        if isinstance(entry, AgentSpec):
            return entry.output_type
        return entry

    @classmethod
    def get_tools(cls, step_name: str) -> list[Any]:
        """
        Get the tools list for a given step name.

        Returns the tools from an AgentSpec entry, or an empty list for bare types.

        Args:
            step_name: The snake_case step name to look up

        Returns:
            List of tool callables registered for this step, or []

        Raises:
            KeyError: If step_name not found in registry
        """
        if step_name not in cls.AGENTS:
            raise KeyError(
                f"No agent registered for step '{step_name}' in {cls.__name__}. "
                f"Available steps: {list(cls.AGENTS.keys())}"
            )
        entry = cls.AGENTS[step_name]
        if isinstance(entry, AgentSpec):
            return entry.tools
        return []


__all__ = ["AgentRegistry", "AgentSpec"]
