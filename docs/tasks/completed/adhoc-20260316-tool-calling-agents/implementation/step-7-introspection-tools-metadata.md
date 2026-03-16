# IMPLEMENTATION - STEP 7: INTROSPECTION TOOLS METADATA
**Status:** completed

## Summary
Added "tools" field to introspection step_entry dicts. Looks up tool function names from AGENT_REGISTRY.get_tools() when available, defaults to empty list. Fully guarded with try/except so introspection never fails.

## Files
**Created:** none
**Modified:** llm_pipeline/introspection.py, tests/test_introspection.py
**Deleted:** none

## Changes
### File: `llm_pipeline/introspection.py`
Added "tools": [] default to step_entry dict. After dict construction, looks up AGENT_REGISTRY via getattr, calls get_tools(step_name) if available, extracts __name__ from each tool function. Wrapped in try/except to keep introspection safe.

```
# Before
step_entry: Dict[str, Any] = {
    "step_name": self._step_name(step_cls),
    ...
    "action_after": step_def.action_after,
}

# After
step_name = self._step_name(step_cls)
step_entry: Dict[str, Any] = {
    "step_name": step_name,
    ...
    "tools": [],
    "action_after": step_def.action_after,
}
# Tools from AGENT_REGISTRY (safe: never fails introspection)
try:
    agent_registry = getattr(self._pipeline_cls, 'AGENT_REGISTRY', None)
    if agent_registry is not None and hasattr(agent_registry, 'get_tools'):
        tool_fns = agent_registry.get_tools(step_name)
        step_entry["tools"] = [
            getattr(fn, '__name__', str(fn)) for fn in tool_fns
        ]
except Exception:
    pass  # keep tools=[] default
```

### File: `tests/test_introspection.py`
Added TestToolsMetadata class with 6 tests covering: tools key present, empty when no registry, populated from AgentSpec, list-of-strings type check, empty for bare Type entries, graceful handling when step not in registry.

## Decisions
### Tool name extraction strategy
**Choice:** `getattr(fn, '__name__', str(fn))` for each tool callable
**Rationale:** Works for regular functions, lambdas, and callable objects. Falls back to str() for edge cases.

### Error handling approach
**Choice:** Broad try/except around entire tools lookup block
**Rationale:** get_tools() raises KeyError if step not in registry. Other unexpected errors possible. Introspection must never fail -- tools=[] is safe default.

## Verification
[x] All 49 introspection tests pass (6 new tools tests)
[x] Tools populated correctly from AgentSpec with tool functions
[x] Tools empty for pipelines without AGENT_REGISTRY
[x] Tools empty for bare Type entries in registry
[x] Graceful fallback when step_name not in registry AGENTS dict
[x] No regression on existing 43 tests
