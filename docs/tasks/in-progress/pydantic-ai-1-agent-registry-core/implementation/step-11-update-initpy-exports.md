# IMPLEMENTATION - STEP 11: UPDATE __INIT__.PY EXPORTS
**Status:** completed

## Summary
Added top-level exports for AgentRegistry, StepDeps, and build_step_agent to llm_pipeline/__init__.py.

## Files
**Created:** none
**Modified:** llm_pipeline/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/__init__.py`
Added imports for agent_registry and agent_builders modules; added "Agent" category section to __all__.

```
# Before
from llm_pipeline.introspection import PipelineIntrospector

# After
from llm_pipeline.introspection import PipelineIntrospector
from llm_pipeline.agent_registry import AgentRegistry
from llm_pipeline.agent_builders import StepDeps, build_step_agent
```

```
# Before (end of __all__)
    # Introspection
    "PipelineIntrospector",
]

# After (end of __all__)
    # Introspection
    "PipelineIntrospector",
    # Agent
    "AgentRegistry",
    "StepDeps",
    "build_step_agent",
]
```

## Decisions
None

## Verification
[x] `from llm_pipeline import AgentRegistry, StepDeps, build_step_agent` succeeds
[x] Import grouping and __all__ category style matches existing patterns
