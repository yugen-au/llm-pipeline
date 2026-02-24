# Research Summary

## Executive Summary

Consolidated findings from UI component research (step-1) and data layer research (step-2) for the Step Detail Panel (task 35). Both research files are largely accurate and agree on core facts: Sheet+Tabs need installing, StepDetailPanelProps interface is preserved, useStepEvents hook is missing, event_data is untyped, and no server-side step_name filter exists on the events API.

Cross-referencing against actual source code revealed one significant factual correction: the ContextEvolution API returns per-step `{step_name: serialized_output}` blobs, NOT cumulative pipeline context -- making it unsuitable as a diff source. The ContextUpdated event's `context_snapshot` field contains the true cumulative pipeline context needed for diffing.

Five decisions require CEO input before planning: Input tab semantics, Instructions tab viability, event pagination strategy, Context Diff data source, and downstream extensibility for task 49.

## Domain Findings

### Component Infrastructure (Confirmed)
**Source:** step-1-ui-component-research.md, actual codebase

- shadcn Sheet and Tabs are NOT installed; all other needed components (ScrollArea, Badge, Button, Card, Separator) are present
- Current StepDetailPanel is div-based with custom a11y (focus trap, Escape, backdrop) -- Sheet replaces all of this
- StepDetailPanelProps interface `{ runId, stepNumber: number|null, open, onClose, runStatus? }` confirmed in actual code (StepDetailPanel.tsx lines 8-14)
- StepContent child component guards useStep hook call -- only mounts when panel open + stepNumber non-null (lines 16-60)
- Task 34 SUMMARY explicitly says: "Task 35 should install Sheet and rewrite the panel with the full 7-tab layout"
- 8 existing tests must be rewritten for Sheet (Radix portal changes DOM query strategies)
- Panel width changes from w-96 (384px) to w-[600px] per task 35 spec

### Data Hooks & API Layer (Confirmed)
**Source:** step-2-data-layer-research.md, actual codebase (steps.ts, events.ts, types.ts)

- `useStep(runId, stepNumber, runStatus?)` exists in `src/api/steps.ts` -- returns StepDetail
- `useEvents(runId, filters?, runStatus?)` exists in `src/api/events.ts` -- returns EventListResponse
- `useStepEvents` does NOT exist -- must be created or event filtering done inline
- EventItem.event_data typed as `Record<string, unknown>` (types.ts line 155) -- no discriminated interfaces for specific event payloads
- EventListParams only supports `event_type`, `offset`, `limit` -- NO `step_name` filter (types.ts lines 87-91)
- RunDetailPage already fetches and caches events via useEvents with default params

### context_snapshot Semantics (Critical Correction)
**Source:** cross-reference of pipeline.py, runs.py, types.py

Both research files discuss context_snapshot but the distinction needs emphasis:

1. **PipelineStepState.context_snapshot** (DB / StepDetail API): Set to `{step.step_name: serialized_instructions}` at pipeline.py line 946. This is the step's OWN output wrapped in a dict keyed by step_name. NOT cumulative.
2. **ContextUpdated.context_snapshot** (event): Set to `dict(self._context)` at pipeline.py line 381. This IS the full accumulated pipeline context after all steps up to and including this one.
3. **ContextEvolution API**: Returns PipelineStepState.context_snapshot per step (runs.py line 277). So it returns per-step output blobs, NOT cumulative context.

Data research section 4.3 states "ContextEvolution snapshots: previous step's context vs current step's context" which implies diffable cumulative snapshots. This is INCORRECT -- these are per-step output blobs. Only ContextUpdated events provide cumulative context suitable for diffing.

### result_data vs context_snapshot Redundancy (New Finding)
**Source:** pipeline.py lines 930-964

`result_data` = serialized step instructions (the list of serialized instruction objects).
`context_snapshot` = `{step.step_name: result_data}` (same data, wrapped in dict with step_name key).

These are effectively redundant for the same step. Neither represents the step's INPUT. The step's actual input is the accumulated pipeline context BEFORE this step ran, available only from the previous step's ContextUpdated event.

### Event Type Coverage (Gap in UI Research)
**Source:** step-2-data-layer-research.md, events/types.py

UI research documented 8 event types. The full catalog has 27 concrete event types across 9 categories. Notably missing from UI research but relevant to tabs:
- **LLMCallPrepared** (call_count, system_key, user_key) -- useful for Prompts tab header
- **LLMCallRetry/Failed/RateLimited** -- useful for Meta tab (retry info)
- **ConsensusStarted/Attempt/Reached/Failed** -- relevant when step uses consensus strategy
- **CacheHit/CacheMiss** -- useful for Meta tab (cache status)
- **TransformationStarting/Completed** -- relevant for steps with transformations
- **StepSelected** (strategy_name) -- useful for Meta tab

### Task 35 Description Code Inaccuracy
**Source:** task 35 details (TaskMaster)

The task description code accesses `llmStarting?.rendered_system_prompt` directly on the event object. In reality, this field is nested inside `event_data`: `event.event_data.rendered_system_prompt`. The description also uses `.find()` which returns only the FIRST matching event -- consensus steps can have multiple LLMCallStarting/Completed events. Implementation must use `.filter()` and handle multi-call display.

### Downstream Task Constraints
**Source:** TaskMaster tasks 37, 49

- **Task 37 (Live Execution)**: Reuses `<StepDetailPanel />` in a 3-column grid. Same props interface. No special requirements beyond task 35's scope.
- **Task 49 (Step Creator)**: Shows `<StepDetailPanel results={testResults} />` -- a `results` prop that doesn't exist in current interface. This suggests task 49 needs a data-override mode where the panel displays test results instead of fetching from API. OUT OF SCOPE for task 35, but component architecture should not preclude adding this later.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| [Pending -- see Questions below] | [Awaiting CEO response] | [TBD] |

## Assumptions Validated
- [x] Sheet and Tabs shadcn components are not installed (confirmed via component listing)
- [x] StepDetailPanelProps interface is stable and should be preserved (confirmed in code + task 34 SUMMARY)
- [x] useStep hook exists with correct signature (confirmed in steps.ts)
- [x] useEvents hook exists with correct signature (confirmed in events.ts)
- [x] useStepEvents does NOT exist (confirmed: not in steps.ts or events.ts)
- [x] EventListParams lacks step_name filter (confirmed in types.ts)
- [x] EventItem.event_data is untyped Record<string, unknown> (confirmed in types.ts)
- [x] No existing JsonViewer/PromptViewer/CodeViewer components (confirmed via codebase search)
- [x] StepContent child component guards useStep call (confirmed in StepDetailPanel.tsx)
- [x] Steps only appear in DB after completion, no status column (confirmed in state.py)
- [x] context_snapshot in PipelineStepState is per-step output, not cumulative (confirmed in pipeline.py line 946)
- [x] ContextUpdated event has cumulative pipeline context (confirmed in pipeline.py line 381)
- [x] result_data and context_snapshot are effectively redundant for same step (confirmed in pipeline.py lines 930-964)

## Open Items
- Q1: Input tab data source -- what should "Input" display? (see Questions)
- Q2: Instructions tab viability with minimal event data (see Questions)
- Q3: Event pagination strategy for runs with >100 events (see Questions)
- Q4: Context Diff tab data source -- ContextUpdated events vs ContextEvolution API (see Questions)
- Q5: Forward compatibility with task 49's `results` prop pattern (see Questions)
- TypeScript discriminated union interfaces for event_data payloads -- technical decision, can be made during planning
- Multi-call (consensus) display strategy for Prompts/Response tabs -- technical decision, can be made during planning

## Recommendations for Planning
1. **Resolve all 5 CEO questions before creating implementation plan** -- Q1 and Q2 directly affect tab count and content; Q4 affects data fetching strategy
2. **Install Sheet + Tabs as first implementation step** -- no dependencies, unblocks all UI work
3. **Create useStepEvents derived hook** -- filter from RunDetailPage's cached events using `select` option on useQuery; avoids duplicate network requests
4. **Define TypeScript interfaces for event_data payloads** -- at minimum: LLMCallStartingData, LLMCallCompletedData, ContextUpdatedData, ExtractionCompletedData, ExtractionErrorData
5. **Use .filter() not .find() for event matching** -- consensus steps produce multiple LLM call events; tabs must handle arrays, not single values
6. **Build tab content components as private sub-components initially** -- extract to shared components only if task 37/49 needs them
7. **Increase event fetch limit to 500 for StepDetailPanel** (pending Q3 decision) -- or create separate useEvents call with higher limit
8. **Context Diff tab should use ContextUpdated events** (pending Q4 decision) -- ContextEvolution API snapshots are per-step output, not diffable cumulative context
9. **Keep component extensible but don't add task 49's results prop yet** (pending Q5 decision) -- use clean separation between data fetching and rendering so future data-override mode is straightforward
10. **Rewrite all 8 existing tests** -- Sheet renders via Radix portal; test queries will need updating for portal-based DOM structure
