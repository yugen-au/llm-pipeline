# Add Tool-Calling Agent Support

## Summary
Expand llm-pipeline's agent system to support tool-calling pydantic-ai agents. AgentRegistry gains an AgentSpec dataclass (backward-compat), build_step_agent gains a tools param, EventEmittingToolset intercepts tool calls to emit new ToolCallStarting/ToolCallCompleted events, and the frontend displays tool definitions and live tool call events via existing WebSocket infrastructure.

## Plugin & Agents
**Plugin:** python-development, backend-development, llm-application-dev
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases
1. Backend core: AgentSpec, AgentRegistry expansion, build_step_agent tools param, pipeline.py wiring
2. Event system: New tool call event types and EventEmittingToolset
3. Introspection + frontend: Backend metadata, TypeScript types, frontend display

## Architecture Decisions

### AgentSpec as union entry in AGENTS dict
**Choice:** New AgentSpec dataclass; AGENTS type becomes `dict[str, Type[BaseModel] | AgentSpec]`. get_output_type normalizes both. New get_tools() returns list or empty list.
**Rationale:** Validated CEO decision. Bare Type still works unchanged. No migration required for existing registries. Single source of truth for tools stays in registry.
**Alternatives:** Separate tools registry dict (rejected - scatter); StepDefinition-level tools (rejected - CEO directed registry level)

### WrapperToolset for event interception
**Choice:** EventEmittingToolset(WrapperToolset) wraps FunctionToolset(tools=[...]). Passed as toolsets= on Agent constructor when tools present.
**Rationale:** pydantic-ai 1.0.5 WrapperToolset.call_tool() override is the canonical interception point. ctx.deps (StepDeps) available in call_tool, giving access to event_emitter, run_id, pipeline_name, step_name. Validated via Context7 /pydantic/pydantic-ai docs.
**Alternatives:** Wrapping individual tool functions (rejected - boilerplate, no centralized interception); modifying run_sync call sites (rejected - fragile)

### EventEmittingToolset in separate llm_pipeline/toolsets.py
**Choice:** New file llm_pipeline/toolsets.py containing EventEmittingToolset.
**Rationale:** Keeps agent_builders.py focused on Agent construction. toolsets.py is a natural home for pydantic-ai toolset implementations. Mirrors how validators.py is separate from agent_builders.py.
**Alternatives:** Inline in agent_builders.py (rejected - growing complexity)

### step.get_agent() returns (output_type, tools) tuple
**Choice:** get_agent() returns tuple[type, list] always. pipeline.py destructures to output_type, tools.
**Rationale:** Minimal change to step.py. Pipeline.py already unpacks the single return value; returning a tuple is backward-compatible at the call site (just update the unpacking). Avoids exposing AgentSpec to pipeline.py directly.
**Alternatives:** Return AgentSpec directly (would require importing AgentSpec in pipeline.py and step.py - minor but extra coupling)

## Implementation Steps

### Step 1: AgentSpec dataclass + AgentRegistry expansion
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** A

1. In `llm_pipeline/agent_registry.py`: add `from dataclasses import dataclass, field` and `from typing import Any` imports
2. Add AgentSpec dataclass above AgentRegistry:
   ```python
   @dataclass
   class AgentSpec:
       output_type: Type[BaseModel]
       tools: list[Any] = field(default_factory=list)
   ```
3. Update AGENTS type annotation: `AGENTS: ClassVar[dict[str, Type[BaseModel] | AgentSpec]] = {}`
4. Update `__init_subclass__` docstring to reflect dual-type support
5. Update `get_output_type` to normalize: if value is AgentSpec return value.output_type, else return value as-is
6. Add `get_tools(step_name: str) -> list[Any]` classmethod: normalize AgentSpec -> return tools, bare Type -> return []
7. Update `__all__` to export `AgentSpec`

### Step 2: step.py get_agent() returns tuple
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/step.py`, update `get_agent()` return annotation to `tuple[type, list]`
2. Change body: resolve agent_name, call `registry.get_output_type(agent_name)` for output_type and `registry.get_tools(agent_name)` for tools, return `(output_type, tools)`
3. Update docstring to reflect new return type

### Step 3: build_step_agent tools param
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** B

1. In `llm_pipeline/agent_builders.py`: add `from collections.abc import Sequence` import
2. Add `tools: Sequence[Any] | None = None` parameter to `build_step_agent()` after `instrument`
3. After `agent_kwargs` dict construction and before `Agent(**agent_kwargs)`: if tools provided, import and construct `FunctionToolset(tools=list(tools))` then `EventEmittingToolset(inner)`, add `toolsets=[emitting_toolset]` to agent_kwargs
4. Guard the toolset path: only use EventEmittingToolset if tools is non-empty (plain `tools=` path not needed per research - always have event_emitter in pipeline context)
5. Import EventEmittingToolset lazily (inside function) to avoid circular imports: `from llm_pipeline.toolsets import EventEmittingToolset`
6. Import FunctionToolset lazily: `from pydantic_ai.toolsets import FunctionToolset`
7. Update docstring: document tools param
8. Update `__all__` stays same (no new exports)

### Step 4: pipeline.py wiring
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/pipeline.py` at line ~737: change `output_type = step.get_agent(self.AGENT_REGISTRY)` to `output_type, step_tools = step.get_agent(self.AGENT_REGISTRY)`
2. At the `build_step_agent(...)` call (~line 745): add `tools=step_tools` kwarg
3. Verify the consensus path (~line 1256) reuses the same agent variable (no second build_step_agent call needed) - if it does build separately, apply same change there

### Step 5: Tool call event types
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/events/types.py`: add `CATEGORY_TOOL_CALL = "tool_call"` after existing category constants
2. Add two new event dataclasses after the State Events section:
   ```python
   @dataclass(frozen=True, slots=True, kw_only=True)
   class ToolCallStarting(StepScopedEvent):
       EVENT_CATEGORY: ClassVar[str] = CATEGORY_TOOL_CALL
       tool_name: str
       tool_args: dict[str, Any]
       call_index: int

   @dataclass(frozen=True, slots=True, kw_only=True)
   class ToolCallCompleted(StepScopedEvent):
       EVENT_CATEGORY: ClassVar[str] = CATEGORY_TOOL_CALL
       tool_name: str
       result_preview: str | None
       execution_time_ms: float
       call_index: int
       error: str | None = None
   ```
3. Add `CATEGORY_TOOL_CALL`, `ToolCallStarting`, `ToolCallCompleted` to `__all__`
4. In `llm_pipeline/events/__init__.py`: import and re-export `CATEGORY_TOOL_CALL`, `ToolCallStarting`, `ToolCallCompleted`

### Step 6: EventEmittingToolset
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pydantic/pydantic-ai
**Group:** C

1. Create `llm_pipeline/toolsets.py`
2. Implement `EventEmittingToolset(WrapperToolset)`:
   - `__init__(self, wrapped)`: calls `super().__init__(wrapped)`, sets `self._call_counter = itertools.count()`
   - `async def call_tool(self, name, tool_args, ctx, tool)`:
     - `idx = next(self._call_counter)`
     - `emitter = ctx.deps.event_emitter` (may be None - skip emission if so)
     - emit `ToolCallStarting(run_id=..., pipeline_name=..., step_name=..., tool_name=name, tool_args=tool_args, call_index=idx)` if emitter
     - `start = time.perf_counter()`
     - try/except: `result = await super().call_tool(name, tool_args, ctx, tool)`
     - on success: emit `ToolCallCompleted(... execution_time_ms=..., result_preview=str(result)[:200] if result is not None else None, error=None)`
     - on exception: emit `ToolCallCompleted(... error=str(e))`, re-raise
3. Add `__all__ = ["EventEmittingToolset"]`

### Step 7: introspection.py tools metadata
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `llm_pipeline/introspection.py`, in `_introspect_strategy()` -> step_entry dict construction: after building step_entry, look up tools from pipeline's AGENT_REGISTRY if available
2. Add logic: `agent_registry = getattr(self._pipeline_cls, 'AGENT_REGISTRY', None)`. If registry present and has `get_tools`, call `get_tools(step_name)` and extract tool function names via `getattr(fn, '__name__', str(fn))` for each tool
3. Add `"tools": []` default to step_entry dict, populate with tool names if registry available
4. Keep logic safe (try/except or guard): introspection must not fail if registry absent

### Step 8: Frontend - TypeScript types
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `llm_pipeline/ui/frontend/src/api/types.ts`: add `ToolCallStartingData` and `ToolCallCompletedData` interfaces after existing typed event_data interfaces
2. Add `tools: string[]` field to `PipelineStepMetadata` interface

### Step 9: Frontend - EventStream badge + StrategySection tools display
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. In `llm_pipeline/ui/frontend/src/components/live/EventStream.tsx`: in `getEventBadgeConfig()`, add case before the fallback: `if (eventType.startsWith('tool_call')) { return { variant: 'outline', className: 'border-cyan-500 text-cyan-600 dark:text-cyan-400' } }`
2. In `llm_pipeline/ui/frontend/src/components/pipelines/StrategySection.tsx`: in `StepRow` expanded section, add tools display block after extractions block:
   - Guard: `{step.tools && step.tools.length > 0 && (...)}`
   - Render list of tool function names as monospace badges/text
   - Label: "Tools" with same styling as "Extractions" label

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| step.get_agent() return type change breaks pipeline.py at other call sites | High | Grep all call sites before change; only pipeline.py calls get_agent() - verify |
| FunctionToolset import path changes across pydantic-ai versions | Medium | Pin to 1.0.5; import lazily; add try/except with clear error message |
| EventEmittingToolset ctx.deps is not StepDeps (consensus path uses different deps) | Medium | Guard: check hasattr(ctx.deps, 'event_emitter') before accessing; skip emission if absent |
| Consensus path builds second agent (separate build_step_agent call) | Medium | Check pipeline.py ~line 1256 explicitly; apply same tools wiring if needed |
| result_preview for large tool results bloats events | Low | Truncate to 200 chars in call_tool(); can be tuned later |
| introspection.py AGENT_REGISTRY lookup fails for pipelines without registry | Low | Guard with getattr default None + hasattr checks; default tools=[] |
| Frontend PipelineStepMetadata.tools field absent in older API responses | Low | TypeScript field as optional `tools?: string[]`; render conditionally |

## Success Criteria
- [ ] `AgentSpec(output_type=X, tools=[fn1])` accepted in AGENTS dict; bare `Type[BaseModel]` still works unchanged
- [ ] `AgentRegistry.get_tools('step')` returns tool list for AgentSpec, [] for bare type
- [ ] `build_step_agent(..., tools=[fn1])` creates Agent with toolsets=[EventEmittingToolset]
- [ ] pipeline.py reads tools from registry and passes to build_step_agent without error
- [ ] ToolCallStarting event emitted before tool execution with correct fields
- [ ] ToolCallCompleted event emitted after tool execution with execution_time_ms
- [ ] ToolCallCompleted.error populated on tool exception; exception still propagates
- [ ] step_entry in introspection includes "tools" list of function names
- [ ] PipelineStepMetadata TypeScript interface has tools field
- [ ] EventStream renders tool_call events with cyan badge
- [ ] StrategySection shows tool list in expanded step view when tools present
- [ ] Existing tests pass (no regression on pipeline runs without tools)

## Phase Recommendation
**Risk Level:** medium
**Reasoning:** Core changes are localized (agent_registry.py, agent_builders.py, pipeline.py) but the tuple return from get_agent() is a breaking internal interface change requiring careful grep of all call sites. WrapperToolset interception is async and requires correct error propagation. Frontend changes are low-risk additive.
**Suggested Exclusions:** review
