# Task Summary

## Work Completed

Added tool-calling agent support to the llm-pipeline framework. Pipelines can now declare tool functions on a per-step basis via an `AgentSpec` entry in their `AgentRegistry.AGENTS` dict. The pipeline automatically constructs agents with those tools, intercepts each tool call to emit `ToolCallStarting` / `ToolCallCompleted` events over the existing WebSocket event stream, and exposes tool metadata through the introspection API so the frontend can display registered tools per step.

Nine implementation steps across four execution groups were completed, followed by a review fix loop that addressed two MEDIUM test coverage gaps and two LOW quality issues before the architecture review approved the implementation as ready for merge.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/toolsets.py` | `EventEmittingToolset(WrapperToolset)` - intercepts pydantic-ai tool calls to emit pipeline events. Includes `_RESULT_PREVIEW_MAX_LEN = 200` constant. |
| `tests/test_toolsets.py` | 17 unit tests for `EventEmittingToolset.call_tool()` covering success path, error path, and absent-emitter path across 4 test classes. |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/agent_registry.py` | Added `AgentSpec` dataclass (`output_type`, `tools`). Expanded `AGENTS` type to `dict[str, Type[BaseModel] \| AgentSpec]`. Added `get_tools()` classmethod. Updated `get_output_type()` to normalize both entry forms. Exported `AgentSpec` in `__all__`. |
| `llm_pipeline/__init__.py` | Added `AgentSpec` to package imports and `__all__`. |
| `llm_pipeline/step.py` | `get_agent()` return type changed from `type` to `tuple[type, list]`. Body now calls both `registry.get_output_type()` and `registry.get_tools()`, returning the pair. |
| `llm_pipeline/agent_builders.py` | Added `tools: Sequence[Any] \| None = None` parameter to `build_step_agent()`. When truthy, constructs `FunctionToolset(tools=list(tools))` then `EventEmittingToolset(inner)` and passes as `toolsets=[emitting]` to `Agent`. Both imports are lazy inside the `if tools:` guard. |
| `llm_pipeline/pipeline.py` | Destructures `step.get_agent()` result to `output_type, step_tools`. Passes `tools=step_tools` to `build_step_agent()`. One call site only; consensus path reuses the already-built agent. |
| `llm_pipeline/events/types.py` | Added `CATEGORY_TOOL_CALL = "tool_call"` constant. Added `ToolCallStarting` and `ToolCallCompleted` frozen dataclass events (both `StepScopedEvent` subclasses). Exported all three symbols in `__all__`. |
| `llm_pipeline/events/__init__.py` | Added `CATEGORY_TOOL_CALL`, `ToolCallStarting`, `ToolCallCompleted` to imports and `__all__`. |
| `llm_pipeline/introspection.py` | Added `"tools": []` to step_entry dict. Populates with tool function `__name__` values from `AGENT_REGISTRY.get_tools()` when available. Wrapped in `try/except` so introspection never fails on missing registry or unknown step. |
| `llm_pipeline/ui/frontend/src/api/types.ts` | Added `ToolCallStartingData` and `ToolCallCompletedData` TypeScript interfaces. Added optional `tools?: string[]` to `PipelineStepMetadata`. |
| `llm_pipeline/ui/frontend/src/components/live/EventStream.tsx` | Added `tool_call` prefix case to `getEventBadgeConfig()` returning cyan badge (`border-cyan-500 text-cyan-600 dark:text-cyan-400`). |
| `llm_pipeline/ui/frontend/src/components/pipelines/StrategySection.tsx` | Added Tools display block in `StepRow` expanded section (between Extractions and Transformation). Renders tool names as cyan monospace `Badge` elements, guarded by `step.tools && step.tools.length > 0`. |
| `tests/test_agent_registry_core.py` | Updated two `get_agent` tests to destructure tuple return. Added `TestBuildStepAgentTools` class with 8 tests for tools param wiring through `FunctionToolset -> EventEmittingToolset`. |
| `tests/events/test_event_types.py` | Added `ToolCallStarting`/`ToolCallCompleted` fixtures to `EVENT_FIXTURES`. Updated registry count from 31 to 33. Fixed stale comment. Added `CATEGORY_TOOL_CALL` import. Added `tool_call_starting` / `tool_call_completed` entries to `EXPECTED_CATEGORIES`. |
| `tests/test_introspection.py` | Added `TestToolsMetadata` class with 6 tests: tools key present, empty without registry, populated from `AgentSpec`, list-of-strings type, empty for bare Type entries, graceful on missing step. |

## Commits Made

| Hash | Message |
| --- | --- |
| `197b9739` | docs(research-A): adhoc-20260316-tool-calling-agents |
| `19366631` | docs(validate-A): adhoc-20260316-tool-calling-agents |
| `c4cc41ee` | docs(planning-A): adhoc-20260316-tool-calling-agents |
| `de0390a2` | docs(implementation-A): adhoc-20260316-tool-calling-agents (step 2: step.py tuple) |
| `f304b1c4` | docs(implementation-A): adhoc-20260316-tool-calling-agents (step 5: event types) |
| `e0c933c3` | docs(implementation-A): adhoc-20260316-tool-calling-agents (step 1: AgentSpec + registry) |
| `eacb3e5f` | docs(implementation-B): adhoc-20260316-tool-calling-agents (step 4: pipeline.py wiring) |
| `14247ed4` | docs(implementation-B): adhoc-20260316-tool-calling-agents (step 3: build_step_agent tools) |
| `e9058b51` | docs(implementation-C): adhoc-20260316-tool-calling-agents (step 8: frontend TS types) |
| `7af07319` | docs(implementation-C): adhoc-20260316-tool-calling-agents (step 7: introspection) |
| `97cdf208` | docs(implementation-C): adhoc-20260316-tool-calling-agents (step 6: EventEmittingToolset) |
| `a17e88b6` | docs(implementation-D): adhoc-20260316-tool-calling-agents (step 9: frontend UI) |
| `fdfe75b6` | docs(testing-A): adhoc-20260316-tool-calling-agents |
| `5897f3df` | docs(review-A): adhoc-20260316-tool-calling-agents |
| `36df7d45` | docs(fixing-review-A): adhoc-20260316-tool-calling-agents (step 5 fixes) |
| `ea241a76` | docs(fixing-review-B): adhoc-20260316-tool-calling-agents (step 3 fixes) |
| `e2deca6e` | docs(fixing-review-C): adhoc-20260316-tool-calling-agents (step 6 fixes) |
| `3409a912` | chore(state): adhoc-20260316-tool-calling-agents -> review |
| `09ff47f0` | chore(state): adhoc-20260316-tool-calling-agents -> summary |

## Deviations from Plan

- None. All 9 implementation steps were completed as specified. Architecture decisions (AgentSpec union, WrapperToolset interception, tuple return from get_agent, toolsets.py as separate file, lazy imports) were executed exactly as planned. The consensus path verification confirmed no second build_step_agent call site existed, matching the plan's expectation.

## Issues Encountered

### MEDIUM: Missing unit tests for build_step_agent with tools param (Step 3)
**Resolution:** Added `TestBuildStepAgentTools` class to `tests/test_agent_registry_core.py` with 8 tests. Tests access `agent._user_toolsets` (pydantic-ai internal attribute) to verify toolset attachment without requiring runtime LLM execution. Covers None, empty list, and non-empty list cases, plus combinations with validators and other params.

### MEDIUM: Zero test coverage for EventEmittingToolset (Step 6)
**Resolution:** Created `tests/test_toolsets.py` with 17 unit tests across 4 classes covering all three branches of `call_tool()`: emitter present + success, emitter present + exception (re-raise verified), and absent emitter (both missing attribute and None value). Used `MagicMock`/`AsyncMock` for inner toolset and emitter isolation.

### LOW: Stale comment "All 31 concrete event classes" in test_event_types.py (Step 5)
**Resolution:** Updated both occurrences in `tests/events/test_event_types.py` to read "All 33 concrete event classes".

### LOW: EXPECTED_CATEGORIES dict missing tool_call entries (Step 5)
**Resolution:** Added `CATEGORY_TOOL_CALL` import and `tool_call_starting`/`tool_call_completed` entries to `EXPECTED_CATEGORIES` dict. Category parametrized tests now cover all 33 event types.

### LOW: Magic 200-char truncation constant in toolsets.py (Step 6)
**Resolution:** Extracted to `_RESULT_PREVIEW_MAX_LEN: int = 200` module-level constant with docstring. Exported in `__all__`. Tests import and assert against the constant.

## Success Criteria

- [x] `AgentSpec(output_type=X, tools=[fn1])` accepted in AGENTS dict; bare `Type[BaseModel]` still works unchanged
- [x] `AgentRegistry.get_tools('step')` returns tool list for AgentSpec, `[]` for bare type
- [x] `build_step_agent(..., tools=[fn1])` creates Agent with `toolsets=[EventEmittingToolset]`
- [x] pipeline.py reads tools from registry and passes to build_step_agent without error
- [x] `ToolCallStarting` event emitted before tool execution with correct fields
- [x] `ToolCallCompleted` event emitted after tool execution with `execution_time_ms`
- [x] `ToolCallCompleted.error` populated on tool exception; exception still propagates
- [x] step_entry in introspection includes "tools" list of function names
- [x] `PipelineStepMetadata` TypeScript interface has `tools` field
- [x] EventStream renders `tool_call` events with cyan badge
- [x] StrategySection shows tool list in expanded step view when tools present
- [x] Existing tests pass (no regression on pipeline runs without tools) - 1047 passed, 6 skipped

## Recommendations for Follow-up

1. **Tool args filtering for sensitive data** - `ToolCallStarting.tool_args` serializes the full args dict to the event stream. If tools accept credentials or PII, callers have no way to redact fields before emission. Add an optional `sensitive_arg_keys: set[str]` to `AgentSpec` or `EventEmittingToolset` that redacts values before building the event.
2. **`_RESULT_PREVIEW_MAX_LEN` as pipeline config** - The 200-char truncation is currently a module constant. Consider exposing it as a pipeline-level or AgentSpec-level config so heavy-result tools (e.g. document retrieval) can be tuned without patching the constant.
3. **Frontend ToolCallStartingData / ToolCallCompletedData consumers** - The TypeScript interfaces exist in `types.ts` but no component yet narrows `EventItem.event_data` to these types for rich display. A follow-up could add expanded event rows for tool_call events in EventStream showing tool_name, args summary, and result_preview inline.
4. **Tool call correlation across events** - `call_index` is per-agent-instance (resets on each agent construction). If a step is retried, indices restart from 0 on the new agent. Consider a run-scoped counter or a UUID per tool invocation for unambiguous correlation in the event log.
5. **Test with actual pydantic-ai TestModel** - Current EventEmittingToolset tests mock the inner toolset entirely. A follow-up integration test using pydantic-ai's `TestModel` with `call_tools=['tool_name']` (as noted in VALIDATED_RESEARCH.md) would provide end-to-end coverage of the FunctionToolset -> EventEmittingToolset -> Agent path without a real LLM.
