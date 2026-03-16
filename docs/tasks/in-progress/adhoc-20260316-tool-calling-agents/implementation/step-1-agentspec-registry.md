# IMPLEMENTATION - STEP 1: AGENTSPEC + REGISTRY
**Status:** completed

## Summary
Added AgentSpec dataclass to agent_registry.py. Expanded AgentRegistry to accept both bare Type[BaseModel] and AgentSpec(output_type, tools) in AGENTS dict. Added get_tools() classmethod. Updated get_output_type() to normalize both forms. Exported AgentSpec from module and package.

## Files
**Created:** none
**Modified:** llm_pipeline/agent_registry.py, llm_pipeline/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/agent_registry.py`
Added AgentSpec dataclass, expanded AGENTS type, normalized get_output_type, added get_tools classmethod.
```
# Before
from abc import ABC
from typing import ClassVar, Type
from pydantic import BaseModel

class AgentRegistry(ABC):
    AGENTS: ClassVar[dict[str, Type[BaseModel]]] = {}

    @classmethod
    def get_output_type(cls, step_name: str) -> Type[BaseModel]:
        ...
        return cls.AGENTS[step_name]

__all__ = ["AgentRegistry"]

# After
from abc import ABC
from dataclasses import dataclass, field
from typing import Any, ClassVar, Type
from pydantic import BaseModel

@dataclass
class AgentSpec:
    output_type: Type[BaseModel]
    tools: list[Any] = field(default_factory=list)

class AgentRegistry(ABC):
    AGENTS: ClassVar[dict[str, Type[BaseModel] | AgentSpec]] = {}

    @classmethod
    def get_output_type(cls, step_name: str) -> Type[BaseModel]:
        ...
        entry = cls.AGENTS[step_name]
        if isinstance(entry, AgentSpec):
            return entry.output_type
        return entry

    @classmethod
    def get_tools(cls, step_name: str) -> list[Any]:
        ...
        entry = cls.AGENTS[step_name]
        if isinstance(entry, AgentSpec):
            return entry.tools
        return []

__all__ = ["AgentRegistry", "AgentSpec"]
```

### File: `llm_pipeline/__init__.py`
Added AgentSpec to import and __all__ export.
```
# Before
from llm_pipeline.agent_registry import AgentRegistry
...
    "AgentRegistry",

# After
from llm_pipeline.agent_registry import AgentRegistry, AgentSpec
...
    "AgentRegistry",
    "AgentSpec",
```

## Decisions
### Used stdlib dataclass over pydantic BaseModel for AgentSpec
**Choice:** stdlib @dataclass
**Rationale:** AgentSpec is a simple container for output_type + tools. No validation needed. Avoids circular dependency with pydantic BaseModel used as the output_type field type. Keeps it lightweight.

### KeyError on missing step in get_tools (same as get_output_type)
**Choice:** Raise KeyError for unknown step_name in get_tools
**Rationale:** Consistent with get_output_type behavior. Caller should know if a step doesn't exist rather than silently getting [].

## Verification
[x] AgentSpec(output_type=X, tools=[fn]) accepted in AGENTS dict
[x] Bare Type[BaseModel] still works unchanged (backward compat)
[x] get_output_type normalizes AgentSpec -> .output_type
[x] get_output_type returns bare Type as-is
[x] get_tools returns .tools for AgentSpec entries
[x] get_tools returns [] for bare Type entries
[x] KeyError raised for unknown step in both methods
[x] AgentSpec exported in agent_registry.__all__
[x] AgentSpec imported/exported in llm_pipeline.__init__
[x] All 1009 existing tests pass (6 skipped, pre-existing event count test excluded)
