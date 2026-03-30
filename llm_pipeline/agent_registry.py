"""
Global agent registry.

Agents are defined by their tools. Steps declare which agent they use via
@step_definition(agent="agent_name"). The registry maps agent names to tool lists.

Convention: define agents in an agents/ directory, but register_agent() works
from anywhere.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentSpec:
    """Specification for a named agent's tools.

    Example:
        register_agent("code_gen", tools=[query_docs, resolve_lib])
    """
    tools: list[Any] = field(default_factory=list)


_AGENT_REGISTRY: dict[str, AgentSpec] = {}


def register_agent(name: str, tools: list[Any]) -> None:
    """Register an agent by name with its tools.

    Overwrites if name already registered.
    """
    _AGENT_REGISTRY[name] = AgentSpec(tools=list(tools))


def get_agent_tools(name: str) -> list[Any]:
    """Get tools for a named agent. Returns [] if not registered."""
    spec = _AGENT_REGISTRY.get(name)
    return spec.tools if spec else []


def get_registered_agents() -> dict[str, AgentSpec]:
    """Return a copy of all registered agents (for introspection)."""
    return dict(_AGENT_REGISTRY)


def clear_agent_registry() -> None:
    """Clear all registered agents. Use in test teardown."""
    _AGENT_REGISTRY.clear()


__all__ = ["AgentSpec", "register_agent", "get_agent_tools", "get_registered_agents", "clear_agent_registry"]
