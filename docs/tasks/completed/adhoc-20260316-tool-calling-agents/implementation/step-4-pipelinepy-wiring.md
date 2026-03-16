# IMPLEMENTATION - STEP 4: PIPELINE.PY WIRING
**Status:** completed

## Summary
Wired tool-calling support through pipeline.py by destructuring the new tuple return from step.get_agent() and passing tools to build_step_agent().

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
Two changes at the agent construction site (~lines 737 and 745).

```python
# Before (line 737)
output_type = step.get_agent(self.AGENT_REGISTRY)

# After
output_type, step_tools = step.get_agent(self.AGENT_REGISTRY)
```

```python
# Before (line 745)
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
    validators=step_validators,
    instrument=self._instrumentation_settings,
)

# After
agent = build_step_agent(
    step_name=step.step_name,
    output_type=output_type,
    validators=step_validators,
    instrument=self._instrumentation_settings,
    tools=step_tools,
)
```

## Decisions
### Consensus path needs no changes
**Choice:** No changes to _execute_with_consensus or the consensus call site.
**Rationale:** The consensus path at line 818 receives the already-built `agent` variable as a parameter. The agent is built once per step at line 745, so tools are already wired through when the agent is reused in consensus iterations.

### No other call sites need changes
**Choice:** Only one get_agent() and one build_step_agent() call site exist in pipeline.py.
**Rationale:** Verified via grep - get_agent() is called only at line 737, build_step_agent() only at line 745. Both non-consensus and consensus paths reuse the same agent instance.

## Verification
[x] get_agent() call updated to destructure (output_type, step_tools) tuple
[x] build_step_agent() call updated with tools=step_tools kwarg
[x] Consensus path verified - reuses same agent variable, no separate build needed
[x] No other call sites of get_agent() or build_step_agent() in pipeline.py
[x] Depends on Step 2 (get_agent returns tuple) - confirmed committed (de0390a2)
[x] Depends on Step 3 (build_step_agent tools param) - Group B peer, tools kwarg will be accepted once Step 3 lands
