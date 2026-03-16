# Gap: Tool-Calling Agents in build_step_agent

## Problem

`build_step_agent()` in `agent_builders.py` creates structured-output-only agents. It does NOT accept a `tools` parameter. For agentic steps (e.g. an agent that navigates an Excel workbook via tool calls), we need tools support.

## Changes Required

### 1. Add `tools` param to `build_step_agent()`

- Add `tools: list[Callable] | None = None` parameter
- Register each via `agent.tool(fn)` after construction, or pass to `Agent()` constructor as `tools=[...]`
- Tools receive `RunContext[StepDeps]` so they access session, context, etc.

### 2. Extend StepDeps for domain-specific deps

Current `StepDeps` has: session, pipeline_context, prompt_service, run_id, event_emitter, etc. Tool-calling agents need domain-specific deps (e.g. `WorkbookContext` for spreadsheet navigation).

**Recommended**: Add `extra: dict[str, Any] = field(default_factory=dict)` to `StepDeps`. Steps populate it via pipeline context or prepare_calls. Tools access via `ctx.deps.extra["workbook_context"]`.

Alternative options:
- Allow `StepDeps` subclassing per-pipeline (needs `deps_type` param on builder)
- Stash in `pipeline_context` dict (simplest but least typed)

### 3. No executor changes needed

- `agent.run_sync()` handles tool-call loops internally (pydantic-ai)
- Executor calls `run_sync`, gets `RunResult` -- unchanged
- Token usage from tool-call loops included in `RunResult.usage()`
- `model_settings` already passes through for tool-calling model requirements

## Scope

~30 lines in `agent_builders.py`, ~3 lines in `StepDeps`.
