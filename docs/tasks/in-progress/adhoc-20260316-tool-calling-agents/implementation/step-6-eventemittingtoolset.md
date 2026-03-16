# IMPLEMENTATION - STEP 6: EVENTEMITTINGTOOLSET
**Status:** completed

## Summary
Created `llm_pipeline/toolsets.py` containing `EventEmittingToolset(WrapperToolset)` that intercepts tool calls to emit `ToolCallStarting` and `ToolCallCompleted` pipeline events around each tool execution.

## Files
**Created:** `llm_pipeline/toolsets.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/toolsets.py`
New file implementing EventEmittingToolset. Key design:
- Extends `pydantic_ai.toolsets.WrapperToolset` (canonical pydantic-ai 1.0.5 interception pattern)
- `__init__` accepts wrapped toolset, initializes `itertools.count()` for call indexing
- `call_tool(name, tool_args, ctx, tool)` overrides WrapperToolset with:
  - `hasattr(ctx.deps, 'event_emitter')` guard for consensus/test paths with different deps
  - `ToolCallStarting` emitted before `super().call_tool()`
  - `ToolCallCompleted` emitted after, with `time.perf_counter()` timing (ms)
  - On exception: `ToolCallCompleted` with `error=str(exc)`, then re-raise
  - `result_preview` truncated to 200 chars via `str(result)[:200]`

```python
# Core method signature (matches pydantic-ai 1.0.5 WrapperToolset contract)
async def call_tool(
    self,
    name: str,
    tool_args: dict[str, Any],
    ctx: RunContext,
    tool: ToolsetTool,
) -> Any:
```

## Decisions
### Guard pattern for deps access
**Choice:** `hasattr(ctx.deps, 'event_emitter')` check before accessing emitter
**Rationale:** Consensus path may use different deps type without event_emitter. Silently skipping emission is safer than crashing tool execution.

### Lazy import of event types
**Choice:** Import ToolCallStarting/ToolCallCompleted inside call_tool method body
**Rationale:** Avoids circular imports since events module may transitively import from modules that import toolsets. Follows same pattern as agent_builders.py lazy imports.

### Event kwargs dict reuse
**Choice:** Pre-build common event kwargs (run_id, pipeline_name, step_name) once per call
**Rationale:** Avoids repetition across starting/completed/error emission paths. Clean and DRY.

## Verification
[x] Import succeeds: `from llm_pipeline.toolsets import EventEmittingToolset`
[x] MRO correct: EventEmittingToolset -> WrapperToolset -> AbstractToolset -> ABC
[x] call_tool method signature matches pydantic-ai 1.0.5 WrapperToolset (verified via Context7 docs)
[x] build_step_agent integration works (constructs agent with tools param using EventEmittingToolset)
[x] All 1021 existing tests pass (0 failures, 6 skipped)
[x] hasattr guard prevents crash when deps lacks event_emitter
