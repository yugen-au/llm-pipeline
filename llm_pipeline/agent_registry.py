"""
Base class for agent registries.

Defines the interface for declaring which instructions types a pipeline's agents produce.
Mirrors PipelineDatabaseRegistry pattern: registry = WHAT, runtime factory = HOW.
"""
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, ClassVar, Type

from llm_pipeline.step import LLMResultMixin


@dataclass
class AgentSpec:
    """Specification for a pipeline agent, bundling instructions type with optional tools.

    Use this instead of a bare Type[LLMResultMixin] in AGENTS dict when tools are needed.

    Example:
        class MyRegistry(AgentRegistry, agents={
            "simple_step": SimpleInstructions,                              # bare type (no tools)
            "tool_step": AgentSpec(ToolInstructions, tools=[my_func]),      # with tools
        }):
            pass
    """
    instructions: Type[LLMResultMixin]
    tools: list[Any] = field(default_factory=list)


class AgentRegistry(ABC):
    """
    Base class for pipeline agent registries.

    Each pipeline should define its own registry class that inherits from this,
    declaring which pydantic-ai agents it uses and their instructions types.

    This registry is the single source of truth for:
    1. What agent step_names the pipeline defines
    2. What instructions type each agent produces

    Registry must be configured at class definition time using class call syntax:

    Example:
        class MyPipelineAgentRegistry(AgentRegistry, agents={
            "extract_rates": RateExtraction,
            "validate_lanes": LaneValidation,
        }):
            pass
    """

    AGENTS: ClassVar[dict[str, Type[LLMResultMixin] | AgentSpec]] = {}

    def __init_subclass__(cls, agents=None, **kwargs):
        """
        Called when a subclass is defined. Sets AGENTS from class parameter.

        Args:
            agents: Dict mapping step_name to either a bare Type[LLMResultMixin] or an
                AgentSpec(instructions, tools) for steps that need tool-calling support.
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
    def get_instructions(cls, step_name: str) -> Type[LLMResultMixin]:
        """
        Get the instructions type for a given step name.

        Normalizes both bare Type[LLMResultMixin] and AgentSpec entries.

        Args:
            step_name: The snake_case step name to look up

        Returns:
            The LLMResultMixin subclass registered for this step

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
            return entry.instructions
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
