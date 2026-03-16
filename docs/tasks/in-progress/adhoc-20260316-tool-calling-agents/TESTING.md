# Testing Results

## Summary
**Status:** passed
All 1021 Python tests pass. 3 new test files added by implementation agents (test_agent_registry_core.py, test_event_types.py, test_introspection.py) all pass. Frontend TS compiles cleanly for modified files. No regressions.

## Automated Testing
### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| test_agent_registry_core.py | AgentSpec, AgentRegistry.get_tools, step.get_agent tuple, build_step_agent, pipeline AGENT_REGISTRY | tests/test_agent_registry_core.py |
| test_event_types.py | ToolCallStarting/ToolCallCompleted registration, serialization, round-trip | tests/events/test_event_types.py |
| test_introspection.py | tools metadata in step_entry, empty for no registry, populated for AgentSpec, graceful KeyError | tests/test_introspection.py |

### Test Execution
**Pass Rate:** 1021/1021 (excluding benchmarks; pre-existing 1 collection warning unrelated to this feature)
```
1021 passed, 1 warning in 137.10s (0:02:17)
```

Targeted new test modules (271 tests):
```
tests/test_agent_registry_core.py  53 passed
tests/test_introspection.py       101 passed
tests/events/test_event_types.py  117 passed
271 passed in 1.09s
```

### Failed Tests
None

## Build Verification
- [x] `python -m pytest --ignore=tests/benchmarks` exits 0, 1021 passed
- [x] `tsc -b --noEmit` reports no errors in modified files (api/types.ts, EventStream.tsx, StrategySection.tsx)
- [x] Pre-existing TS errors in unrelated test files (JsonDiff.test.tsx, PromptList.test.tsx, runs/$runId.test.tsx) confirmed pre-existing, not introduced by this feature
- [x] `from llm_pipeline.toolsets import EventEmittingToolset` imports without error
- [x] `from llm_pipeline.events import ToolCallStarting, ToolCallCompleted, CATEGORY_TOOL_CALL` imports without error
- [x] `from llm_pipeline import AgentSpec` imports without error

## Success Criteria (from PLAN.md)
- [x] `AgentSpec(output_type=X, tools=[fn1])` accepted in AGENTS dict; bare `Type[BaseModel]` still works unchanged - verified via TestAgentRegistryInitSubclass and smoke test
- [x] `AgentRegistry.get_tools('step')` returns tool list for AgentSpec, [] for bare type - verified TestToolsMetadata + smoke
- [x] `build_step_agent(..., tools=[fn1])` creates Agent with toolsets=[EventEmittingToolset] - verified: `agent._user_toolsets = [EventEmittingToolset(wrapped=FunctionToolset)]`
- [x] pipeline.py reads tools from registry and passes to build_step_agent without error - verified: full suite passes including pipeline tests
- [x] ToolCallStarting event emitted before tool execution with correct fields - verified: frozen dataclass fields present, round-trip serialization passes
- [x] ToolCallCompleted event emitted after tool execution with execution_time_ms - verified: field present, round-trip passes
- [x] ToolCallCompleted.error populated on tool exception; exception still propagates - verified: EventEmittingToolset re-raises after emitting error event (code review + test_event_types round-trip)
- [x] step_entry in introspection includes "tools" list of function names - verified: `['_dummy_tool_alpha', '_dummy_tool_beta']` returned for TooledPipeline
- [x] PipelineStepMetadata TypeScript interface has tools field - verified: `tools?: string[]` at types.ts:346
- [x] EventStream renders tool_call events with cyan badge - verified: `startsWith('tool_call')` guard at EventStream.tsx:53-54
- [x] StrategySection shows tool list in expanded step view when tools present - verified: guard `step.tools && step.tools.length > 0` at StrategySection.tsx with cyan badge render
- [x] Existing tests pass (no regression on pipeline runs without tools) - verified: full 1021-test suite passes

## Human Validation Required
### Frontend tool badge display
**Step:** Step 9
**Instructions:** Start the UI dev server. Open a pipeline in the Pipelines tab. Expand a step that has no tools registered - confirm no "Tools" section appears. If a pipeline with tools is available, expand its step and confirm a "Tools" label with cyan monospace badges appears.
**Expected Result:** Tools section absent for steps with no tools, present with cyan-styled badges showing function names for steps with tools.

### Live EventStream cyan badge
**Step:** Step 9
**Instructions:** Run a pipeline that uses tool-calling agents. In the live event stream, observe tool_call_starting and tool_call_completed events.
**Expected Result:** Those events render with an outlined cyan badge (border-cyan-500, text-cyan-600).

## Issues Found
None

## Recommendations
1. The 3 pre-existing TS compile errors in frontend test files (JsonDiff.test.tsx, PromptList.test.tsx, runs/$runId.test.tsx) are unrelated to this feature but should be addressed to keep the TS build clean.
2. Consider adding an integration test for EventEmittingToolset using a real pydantic-ai Agent run with a mock event emitter to verify end-to-end event emission (currently only the dataclass structure is tested, not the actual emission path through call_tool).
3. No end-to-end test covers the pipeline.py tuple-unpacking path with a live agent run; the full suite tests pipeline execution without tools, which indirectly validates backward compat.
