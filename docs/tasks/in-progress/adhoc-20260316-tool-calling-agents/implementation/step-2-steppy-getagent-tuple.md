# IMPLEMENTATION - STEP 2: STEP.PY GET_AGENT TUPLE
**Status:** completed

## Summary
Updated LLMStep.get_agent() to return (output_type, tools) tuple instead of bare output_type. Calls registry.get_output_type() and registry.get_tools() then returns both. Updated tests to destructure tuple and assert tools == [].

## Files
**Created:** none
**Modified:** llm_pipeline/step.py, tests/test_agent_registry_core.py
**Deleted:** none

## Changes
### File: `llm_pipeline/step.py`
Changed get_agent() return type from `type` to `tuple[type, list]`. Body now calls both `registry.get_output_type(agent_name)` and `registry.get_tools(agent_name)`, returning the pair.

```python
# Before
def get_agent(self, registry: 'AgentRegistry') -> type:
    agent_name = getattr(self, '_agent_name', None) or self.step_name
    return registry.get_output_type(agent_name)

# After
def get_agent(self, registry: 'AgentRegistry') -> tuple[type, list]:
    agent_name = getattr(self, '_agent_name', None) or self.step_name
    output_type = registry.get_output_type(agent_name)
    tools = registry.get_tools(agent_name)
    return (output_type, tools)
```

### File: `tests/test_agent_registry_core.py`
Updated test_get_agent_uses_step_name and test_get_agent_uses_override to destructure tuple return and assert tools == [].

```python
# Before
output_type = step.get_agent(GetAgentRegistry)
assert output_type is ExtractionOutput

# After
output_type, tools = step.get_agent(GetAgentRegistry)
assert output_type is ExtractionOutput
assert tools == []
```

## Decisions
### No fallback if get_tools missing
**Choice:** Call registry.get_tools() directly without try/except
**Rationale:** Step 1 (Group A peer) adds get_tools to AgentRegistry. Both steps are Group A and will land together. Adding a defensive fallback would mask integration errors.

## Verification
[x] get_agent() return annotation changed to tuple[type, list]
[x] Body calls both get_output_type and get_tools
[x] Returns (output_type, tools) tuple
[x] Docstring updated to reflect new return type
[x] Tests updated to destructure tuple and assert tools
[x] Grep confirmed only pipeline.py:737 + 2 tests call get_agent() -- no missed call sites
[x] Tests fail with expected AttributeError (get_tools not yet on AgentRegistry -- Step 1 dependency)
