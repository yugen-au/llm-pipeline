# IMPLEMENTATION - STEP 3: BUILD_STEP_AGENT TOOLS
**Status:** completed

## Summary
Added `tools: Sequence[Any] | None = None` parameter to `build_step_agent()`. When tools are provided, constructs `FunctionToolset` wrapping them, then wraps that in `EventEmittingToolset`, and passes as `toolsets=[emitting]` to Agent constructor kwargs. Both imports are lazy (inside the `if tools:` guard) to avoid circular imports and defer loading until needed.

## Files
**Created:** none
**Modified:** llm_pipeline/agent_builders.py
**Deleted:** none

## Changes
### File: `llm_pipeline/agent_builders.py`
Added `Sequence` import, `tools` parameter, and toolset construction logic.

```python
# Before (imports)
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

# After (imports)
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING
```

```python
# Before (signature)
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
    instrument: Any | None = None,
) -> Agent[StepDeps, Any]:

# After (signature)
def build_step_agent(
    step_name: str,
    output_type: type,
    model: str | None = None,
    system_instruction_key: str | None = None,
    retries: int = 3,
    model_settings: Any | None = None,
    validators: list[Any] | None = None,
    instrument: Any | None = None,
    tools: Sequence[Any] | None = None,
) -> Agent[StepDeps, Any]:
```

```python
# Before (agent construction)
    if instrument is not None:
        agent_kwargs["instrument"] = instrument

    agent: Agent[StepDeps, Any] = Agent(**agent_kwargs)

# After (agent construction)
    if instrument is not None:
        agent_kwargs["instrument"] = instrument

    if tools:
        from pydantic_ai.toolsets import FunctionToolset
        from llm_pipeline.toolsets import EventEmittingToolset

        inner = FunctionToolset(tools=list(tools))
        emitting = EventEmittingToolset(inner)
        agent_kwargs["toolsets"] = [emitting]

    agent: Agent[StepDeps, Any] = Agent(**agent_kwargs)
```

Docstring updated to document tools parameter:
```
tools: Optional sequence of tool callables to register on the
    agent. When provided, wraps them in FunctionToolset then
    EventEmittingToolset for automatic tool call event emission.
    None or empty = no tools registered.
```

## Decisions
### Lazy imports inside if-guard
**Choice:** Both `FunctionToolset` and `EventEmittingToolset` imported inside `if tools:` block
**Rationale:** Avoids circular imports (EventEmittingToolset not yet created by Step 6). Also avoids importing pydantic_ai.toolsets when no tools are used, keeping the no-tools path unchanged.

### tools parameter position after instrument
**Choice:** `tools` placed as last parameter after `instrument`
**Rationale:** Matches plan spec. tools is an optional additive feature; placing last means zero impact on existing callers using positional or keyword args.

### Truthy check (`if tools:`) instead of `if tools is not None:`
**Choice:** Use `if tools:` which catches both None and empty sequences
**Rationale:** An empty tools list should behave identically to None (no toolsets registered). Avoids constructing empty FunctionToolset unnecessarily.

## Verification
[x] Module imports cleanly: `from llm_pipeline.agent_builders import build_step_agent`
[x] `tools` param exists with correct default (None) and annotation (Sequence[Any] | None)
[x] `FunctionToolset` import path verified: `from pydantic_ai.toolsets import FunctionToolset`
[x] pipeline.py already passes `tools=step_tools` (wired by Group A Step 2) - will work once this param exists
[x] All 53 existing tests pass (test_agent_registry_core.py) - no regression
[x] No-tools path unchanged: when tools=None, agent_kwargs has no toolsets key

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Missing unit tests for build_step_agent with tools param

### Changes Made
#### File: `tests/test_agent_registry_core.py`
Added `TestBuildStepAgentTools` class with 8 tests covering all tools param behaviors:

1. `test_tools_none_no_toolset` - tools=None produces empty _user_toolsets
2. `test_tools_empty_list_no_toolset` - tools=[] (falsy guard) produces empty _user_toolsets
3. `test_tools_provided_attaches_toolset` - non-empty tools list produces exactly one toolset
4. `test_tools_wrapped_in_event_emitting_toolset` - attached toolset is EventEmittingToolset
5. `test_inner_toolset_is_function_toolset` - EventEmittingToolset.wrapped is FunctionToolset
6. `test_multiple_tools_registered` - multiple callables all appear in inner FunctionToolset.tools dict
7. `test_tools_with_other_params_coexist` - tools + validators both work together
8. `test_agent_still_valid_with_tools` - agent name, retries, type correct when tools provided

Tests use Agent._user_toolsets (pydantic-ai internal) to verify toolset attachment without needing runtime execution.

### Verification
[x] All 61 tests pass (53 original + 8 new)
[x] No regressions in existing tests
[x] All three tools param cases covered: None, [], [callable]
