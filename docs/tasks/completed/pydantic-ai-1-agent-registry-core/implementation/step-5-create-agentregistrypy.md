# IMPLEMENTATION - STEP 5: CREATE AGENT_REGISTRY.PY
**Status:** completed

## Summary
Created `llm_pipeline/agent_registry.py` with `AgentRegistry` ABC following the Category A class-param `__init_subclass__` pattern, matching `PipelineDatabaseRegistry` in `registry.py` exactly.

## Files
**Created:** `llm_pipeline/agent_registry.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/agent_registry.py`
New file. AgentRegistry ABC with:
- `AGENTS: ClassVar[dict[str, Type[BaseModel]]] = {}` class variable
- `__init_subclass__(cls, agents=None, **kwargs)` with same guard pattern as PipelineDatabaseRegistry (underscore-prefix skip + direct-subclass enforcement)
- `get_output_type(cls, step_name) -> Type[BaseModel]` classmethod with descriptive KeyError on miss
- `__all__ = ["AgentRegistry"]`

```python
# Usage
class MyAgentRegistry(AgentRegistry, agents={
    "extract_rates": RateExtraction,
    "validate_lanes": LaneValidation,
}):
    pass

MyAgentRegistry.get_output_type("extract_rates")  # -> RateExtraction
```

## Decisions
### Mirror PipelineDatabaseRegistry exactly
**Choice:** Same __init_subclass__ guard logic, same ClassVar pattern, same error message style
**Rationale:** CEO-approved Category A pattern. Consistency with existing registry.py reduces cognitive load.

### KeyError for get_output_type miss (not ValueError)
**Choice:** Raise KeyError with descriptive message listing available steps
**Rationale:** Dict lookup semantics -- KeyError is the natural Python exception for missing dict keys. Includes available steps in message for debuggability.

## Verification
[x] AgentRegistry(ABC) defined with AGENTS ClassVar
[x] __init_subclass__ raises ValueError for concrete subclass without agents=
[x] __init_subclass__ skips validation for _-prefixed classes
[x] __init_subclass__ sets cls.AGENTS when agents provided
[x] get_output_type returns correct type for registered step
[x] get_output_type raises KeyError for unregistered step
[x] AGENTS isolated between subclasses (no shared state)
[x] Base class AGENTS remains empty dict
[x] __all__ exports AgentRegistry
[x] Existing test suite passes (803 passed, 1 pre-existing unrelated failure)
