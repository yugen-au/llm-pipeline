# Research Summary

## Executive Summary

Validated 3 research docs against actual source code and resolved 2 architectural questions with CEO. Core approach confirmed: constructor tool registration on pydantic-ai Agent, no executor changes needed. CEO directed: (1) tools declared at AgentRegistry level via new AgentSpec dataclass (bare Type still works), (2) defer StepDeps.extra -- use pipeline_context for domain tool deps. Additional scope confirmed: tool call event types (ToolCallStarting/ToolCallCompleted), event emission via pydantic-ai WrapperToolset interception, and frontend display of tool definitions + live tool events via existing WebSocket plumbing.

Context7 research revealed pydantic-ai 1.0.5 has both `tools=` (plain functions) and `toolsets=` (AbstractToolset instances) on the Agent constructor. The `WrapperToolset.call_tool()` override is the clean interception point for emitting tool events without modifying tool functions.

## Domain Findings

### pydantic-ai Agent Tool Registration
**Source:** research/step-1-pydantic-ai-agent-patterns.md, Context7 pydantic-ai docs

- pydantic-ai 1.0.5 Agent constructor accepts both `tools=` (list of callables/Tool) and `toolsets=` (list of AbstractToolset).
- For event emission, `toolsets=` with `WrapperToolset` is required. Pattern: wrap user tools in `FunctionToolset(tools=[...])`, then wrap in `EventEmittingToolset(inner)`, pass as `toolsets=[emitting_toolset]`.
- `WrapperToolset.call_tool(name, tool_args, ctx, tool)` receives `RunContext` -- so `ctx.deps` (StepDeps) gives access to `event_emitter`, `run_id`, `pipeline_name`, `step_name` for event construction.
- Auto-detection of `takes_ctx` via `RunContext` first param inspection works for both tools= and FunctionToolset.
- `run_sync()` handles tool-call loops internally. Both call sites (pipeline.py:829, :1256) work unchanged.
- Token tracking via `RunResult.usage()` aggregates across all tool-call iterations.

### AgentRegistry Expansion (CEO-directed)
**Source:** CEO answer to Q1, agent_registry.py analysis

Current state:
- `AgentRegistry.AGENTS: ClassVar[dict[str, Type[BaseModel]]]` maps step_name -> output_type
- `get_output_type(step_name)` returns the bare type
- Consumed at pipeline.py:737 via `step.get_agent(self.AGENT_REGISTRY)`
- step.py:233 `get_agent()` returns type reference (comment says "Task 2 will provide full Agent")

Proposed: Add `AgentSpec` dataclass:
```python
@dataclass
class AgentSpec:
    output_type: Type[BaseModel]
    tools: list[Any] = field(default_factory=list)
```

Registry accepts both: `"step_name": OutputType` (bare, backward-compat) and `"step_name": AgentSpec(output_type=X, tools=[fn1, fn2])`.

Files impacted:
- `agent_registry.py`: Add AgentSpec, update AGENTS type annotation, update get_output_type to normalize, add get_tools() method
- `step.py:217-234`: get_agent() needs to return AgentSpec (or update to return tuple/spec)
- `pipeline.py:737-750`: Read tools from registry, pass to build_step_agent
- `introspection.py`: Include tool names in step metadata for AgentSpec entries
- `__init__.py`: Export AgentSpec

### StepDeps -- No Changes Needed (CEO-directed)
**Source:** CEO answer to Q2

- extra_deps deferred. Tools access domain data via `ctx.deps.pipeline_context` dict (already exists on StepDeps).
- No StepCallParams changes needed.
- No StepDeps field additions.
- All original StepDeps backward-compat analysis remains valid but is moot for this task.

### Tool Registration in build_step_agent
**Source:** research/step-3-tool-registration-patterns.md, agent_builders.py analysis

- Add `tools: Sequence[Any] | None = None` param to build_step_agent.
- When tools provided AND event_emitter available: wrap in FunctionToolset -> EventEmittingToolset, pass as `toolsets=`.
- When tools provided but no event_emitter: pass via `tools=` (simpler, no interception needed).
- Import: `from collections.abc import Sequence`.
- Matches existing conditional pattern (instrument at line 113-114).

### Tool Call Events
**Source:** CEO additional scope, events/types.py analysis

New category and events:
```python
CATEGORY_TOOL_CALL = "tool_call"

@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallStarting(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TOOL_CALL
    tool_name: str
    tool_args: dict[str, Any]
    call_index: int  # which tool call within this step

@dataclass(frozen=True, slots=True, kw_only=True)
class ToolCallCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_TOOL_CALL
    tool_name: str
    result_preview: str | None  # truncated str repr of result
    execution_time_ms: float
    call_index: int
    error: str | None = None
```

Event emission via `EventEmittingToolset(WrapperToolset)`:
- Override `call_tool()`: emit ToolCallStarting before `super().call_tool()`, ToolCallCompleted after
- Access event_emitter via `ctx.deps.event_emitter` (StepDeps already has this field)
- run_sync runs async loop internally; emit() is sync (queue.put_nowait) -- no threading issues
- Auto-registered via `PipelineEvent.__init_subclass__` (snake_case derivation: tool_call_starting, tool_call_completed)

### EventEmittingToolset Design
**Source:** Context7 WrapperToolset docs

```python
class EventEmittingToolset(WrapperToolset):
    def __init__(self, wrapped, call_counter=None):
        super().__init__(wrapped)
        self._call_counter = call_counter or itertools.count()

    async def call_tool(self, name, tool_args, ctx, tool):
        idx = next(self._call_counter)
        emitter = ctx.deps.event_emitter
        # emit ToolCallStarting
        start = time.perf_counter()
        try:
            result = await super().call_tool(name, tool_args, ctx, tool)
            # emit ToolCallCompleted (success)
            return result
        except Exception as e:
            # emit ToolCallCompleted (error)
            raise
```

Location: new file `llm_pipeline/toolsets.py` or within `agent_builders.py`. Recommend separate file for clarity.

### Frontend Changes
**Source:** EventStream.tsx, api/types.ts, StrategySection.tsx analysis

Events auto-stream via existing: UIBridge.emit() -> ConnectionManager.broadcast_to_run() -> Queue -> WS clients. No new plumbing needed.

Changes required:

1. **api/types.ts**: Add typed event_data interfaces:
```typescript
export interface ToolCallStartingData {
    tool_name: string
    tool_args: Record<string, unknown>
    call_index: number
}
export interface ToolCallCompletedData {
    tool_name: string
    result_preview: string | null
    execution_time_ms: number
    call_index: number
    error: string | null
}
```

2. **api/types.ts**: Extend PipelineStepMetadata with optional tools:
```typescript
export interface PipelineStepMetadata {
    // ...existing fields...
    tools: string[]  // tool function names from AgentSpec
}
```

3. **EventStream.tsx**: Add tool_call badge config in `getEventBadgeConfig()`:
```typescript
if (eventType.startsWith('tool_call')) {
    return { variant: 'outline', className: 'border-cyan-500 text-cyan-600 dark:text-cyan-400' }
}
```

4. **StrategySection.tsx**: Display tool definitions list alongside extractions when `step.tools.length > 0`.

5. **introspection.py**: Add `tools` list (function names) to step metadata dict when AgentSpec provides tools.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Where do tools come from at pipeline.py:745? | AgentRegistry level via AgentSpec(output_type, tools). Bare Type still works. pipeline.py reads tools from registry, passes to build_step_agent. | Resolved: tools flow is AgentSpec -> get_tools() -> pipeline.py -> build_step_agent -> toolsets= on Agent |
| Is extra_deps in StepCallParams in scope? | Deferred. Use pipeline_context for domain tool deps. No StepDeps changes. | Resolved: simplifies scope, no StepDeps/StepCallParams modifications needed |

## Assumptions Validated
- [x] Constructor tool registration is best pattern (verified: pydantic-ai tools= and toolsets= both work)
- [x] WrapperToolset.call_tool() is the interception point for tool events (verified via Context7 docs)
- [x] No executor/run_sync changes needed (pydantic-ai handles tool-call loop internally)
- [x] Token usage tracking works unchanged (RunResult.usage() aggregates across iterations)
- [x] StepDeps already has event_emitter field for tool event emission (agent_builders.py:47)
- [x] Event auto-registration via __init_subclass__ handles new tool_call events (events/types.py)
- [x] Frontend WebSocket plumbing auto-streams new event types (UIBridge -> ConnectionManager -> Queue)
- [x] AgentSpec with union type in AGENTS dict is backward-compatible (bare Type still works)
- [x] StepDefinition does NOT need changes (tools come from AgentRegistry, not StepDefinition)
- [x] FunctionToolset wrapping + EventEmittingToolset works with run_sync (async loop is internal)
- [x] emit() is sync (queue.put_nowait) so calling from async call_tool() is safe

## Open Items
- EventEmittingToolset needs to handle the case where ctx.deps has no event_emitter (None) -- should silently skip emission
- tool_args in ToolCallStarting may contain large/sensitive data -- consider truncation or filtering policy (can defer to follow-up)
- Consensus path (pipeline.py:1256) also needs tools passed to build_step_agent if agent is rebuilt per-consensus iteration -- verify single agent build site covers both paths
- Test strategy: use pydantic-ai TestModel with `call_tools=['tool_name']` to simulate tool invocation in unit tests

## Recommendations for Planning

### Task breakdown (suggested order):

1. **AgentSpec + AgentRegistry expansion** (~20 lines)
   - agent_registry.py: AgentSpec dataclass, dual-type AGENTS, get_output_type normalization, get_tools()
   - step.py: update get_agent to return AgentSpec or (output_type, tools)
   - __init__.py: export AgentSpec

2. **build_step_agent tools param** (~10 lines)
   - agent_builders.py: add tools param, conditional toolsets= kwarg on Agent constructor
   - pipeline.py:745: read tools from registry via step.get_agent, pass to build_step_agent

3. **Tool call events** (~30 lines)
   - events/types.py: CATEGORY_TOOL_CALL, ToolCallStarting, ToolCallCompleted
   - events/__init__.py: export new types

4. **EventEmittingToolset** (~40 lines)
   - New llm_pipeline/toolsets.py: EventEmittingToolset(WrapperToolset) with call_tool override
   - Wire into build_step_agent: when tools + event_emitter present, use toolsets= pattern

5. **Introspection + frontend metadata** (~15 lines backend, ~20 lines frontend)
   - introspection.py: include tool names in step metadata
   - api/types.ts: PipelineStepMetadata.tools field

6. **Frontend event display** (~15 lines)
   - api/types.ts: ToolCallStartingData, ToolCallCompletedData
   - EventStream.tsx: tool_call badge config
   - StrategySection.tsx: tool list display

7. **Tests** (~50 lines)
   - AgentSpec backward compat tests
   - build_step_agent with tools
   - EventEmittingToolset unit test with TestModel
   - Event type registration tests for new events
