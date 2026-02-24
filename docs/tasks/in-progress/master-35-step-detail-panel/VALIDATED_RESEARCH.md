# Research Summary

## Executive Summary

Consolidated findings from UI component research (step-1) and data layer research (step-2) for the Step Detail Panel (task 35). Both research files are largely accurate and agree on core facts: Sheet+Tabs need installing, StepDetailPanelProps interface is preserved, useStepEvents hook is missing, event_data is untyped, and no server-side step_name filter exists on the events API.

Cross-referencing against actual source code revealed one significant factual correction: the ContextEvolution API returns per-step `{step_name: serialized_output}` blobs, NOT cumulative pipeline context -- making it unsuitable as a diff source. The ContextUpdated event's `context_snapshot` field contains the true cumulative pipeline context needed for diffing.

All 5 CEO questions resolved. **Scope expanded** -- task 35 now includes 2 backend features in addition to the UI panel:
1. Add `step_name` filter to events API (backend + frontend params)
2. Extend introspection API with actual instruction/prompt content (new endpoint, requires DB access)

Planning must order backend work before frontend tabs that depend on it.

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
| Q1: What should Input tab display? | Pipeline context (true input) -- use previous step's accumulated pipeline context from ContextUpdated events | Input tab shows what the step received. Data source = ContextUpdated event from previous step (or empty for step 1). Requires step_name event filter to efficiently fetch. |
| Q2: Instructions tab -- minimal event data acceptable? | Full content via new API -- extend pipeline introspection to return actual instruction text/content | SCOPE EXPANSION: new backend endpoint needed. Prompt table has content field. PipelineIntrospector currently class-level only (no DB). Need new endpoint with DB session to load Prompt.content by key. |
| Q3: Context Diff tab data source? | ContextUpdated events -- use cumulative pipeline context for true before/after diff | Confirmed: ContextUpdated.context_snapshot = dict(self._context) at pipeline.py:381. Use N-1 vs N step events for diff. ContextEvolution API NOT suitable (per-step output blobs, not cumulative). |
| Q4: Event pagination strategy? | Add step_name event filter NOW -- build backend filter on events API | SCOPE EXPANSION: PipelineEventRecord has no step_name column. Must add column (follows existing pattern of duplicating event_data fields for query efficiency) + update EventListParams + events.py WHERE clause. Frontend useStepEvents becomes server-side filtered. |
| Q5: Task 49 forward-compat? | Ignore for now -- task 49 adds its own results prop when needed | No impact on task 35 architecture. Keep clean separation between data-fetching and rendering for future extensibility but don't add unused props. |

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
- DB migration for step_name column on PipelineEventRecord -- create_all() won't add columns to existing tables. Need ALTER TABLE or migration script for existing DBs. Technical decision for planning phase.
- Instruction content endpoint design -- PipelineIntrospector is pure class-level (no DB). New endpoint needs DB session to load Prompt.content by prompt_key. Decide: extend GET /pipelines/{name} or add new GET /pipelines/{name}/steps/{step_name}/instructions. Technical decision for planning phase.
- TypeScript discriminated union interfaces for event_data payloads -- at minimum: LLMCallStartingData, LLMCallCompletedData, ContextUpdatedData, ExtractionCompletedData, ExtractionErrorData, InstructionsLoggedData. Technical decision for planning phase.
- Multi-call (consensus) display strategy for Prompts/Response tabs -- .filter() returns array of events; UI must handle 1-N LLM calls per step. Technical decision for planning phase.
- Backfill strategy for step_name on existing PipelineEventRecord rows -- existing rows have step_name only inside event_data JSON. Could backfill via json_extract or leave NULL. Technical decision for planning phase.

## Recommendations for Planning

### Execution Order (backend-first, then frontend)

1. **Backend: Add step_name column to PipelineEventRecord** -- follows existing pattern (table already duplicates run_id/event_type/timestamp from event_data for query efficiency). Add column, index, populate from event_data on persist in SQLiteEventHandler. Handle ALTER TABLE for existing DBs.
2. **Backend: Add step_name filter to events API** -- add `step_name: Optional[str]` to EventListParams, add WHERE clause in events.py list_events endpoint. Update count query too.
3. **Backend: Instruction content endpoint** -- new endpoint (e.g. GET /pipelines/{name}/steps/{step_name}/prompts) that loads Prompt.content from DB by prompt_key. Prompt table already has content, prompt_key, prompt_type, step_name fields. Requires DB session dependency (unlike existing introspection which is class-level only).
4. **Frontend: Install shadcn Sheet + Tabs** -- no dependencies, unblocks all UI work
5. **Frontend: Update TypeScript types** -- add step_name to EventListParams, define discriminated union interfaces for event_data payloads, add instruction content response types
6. **Frontend: Create useStepEvents hook** -- server-side filtered via new step_name param (not client-side filter). Pass step_name to useEvents filters.
7. **Frontend: Replace div-based panel with Sheet+Tabs** -- rewrite StepDetailPanel using Sheet (removes ~50 lines custom a11y code), add 7 TabsTrigger/TabsContent pairs
8. **Frontend: Build tab content sub-components** -- private components within StepDetailPanel.tsx initially. Use .filter() for event matching (consensus = multiple LLM calls per step).
9. **Frontend: Input tab** -- fetch ContextUpdated events for this step's step_name; use previous step's snapshot as "what this step received" (empty object for step 1)
10. **Frontend: Context Diff tab** -- use ContextUpdated events for cumulative diff (N-1 vs N). Defer rich diff visualization to task 36; show raw JSON comparison for now.
11. **Frontend: Instructions tab** -- fetch instruction content from new backend endpoint by pipeline_name + step_name. Show prompt templates + instructions_schema from introspection.
12. **Frontend: Rewrite all 8 existing tests** -- Sheet renders via Radix portal; test queries need updating for portal-based DOM structure
13. **Keep component extensible but don't add task 49's results prop** -- clean separation between data-fetching and rendering for future extensibility

---

## Revision 1: CEO Decisions & Scope Expansion (2026-02-24)

### Scope Change Summary

Task 35 expanded from UI-only (Step Detail Panel with 7 tabs) to include 2 backend features:

| Scope Item | Type | Complexity | Blocking |
| --- | --- | --- | --- |
| step_name column + filter on events API | Backend (DB schema + route) | Medium | Blocks useStepEvents hook, Input tab, Context Diff tab |
| Instruction content endpoint | Backend (new route + DB query) | Medium | Blocks Instructions tab |
| Step Detail Panel with 7 tabs | Frontend (Sheet+Tabs+sub-components) | High | Original scope |

### Backend Scope: step_name Event Filter

**Current state:** PipelineEventRecord has columns: id, run_id, event_type, pipeline_name, timestamp, event_data (JSON). The step_name value exists only inside event_data JSON blob. No server-side step_name filtering.

**Required changes:**
1. Add `step_name: Optional[str]` column to PipelineEventRecord (nullable for pipeline-level events like pipeline_started/completed)
2. Add index: `ix_pipeline_events_run_step` on (run_id, step_name)
3. Populate step_name from event dataclass in SQLiteEventHandler._persist() -- extract from event.step_name attribute before serialization
4. Add `step_name: Optional[str]` to EventListParams in events.py
5. Add WHERE clause in list_events for step_name filter (both count + data queries)
6. Handle existing DBs: create_all() won't add columns. Need ALTER TABLE migration or startup check.

**Key code locations:**
- `llm_pipeline/events/models.py` -- PipelineEventRecord model (add column + index)
- `llm_pipeline/events/handlers.py` -- SQLiteEventHandler._persist() (populate step_name on save)
- `llm_pipeline/ui/routes/events.py` -- EventListParams + list_events endpoint (add filter)
- `llm_pipeline/ui/frontend/src/api/types.ts` -- EventListParams TS type (add step_name)

### Backend Scope: Instruction Content Endpoint

**Current state:** PipelineIntrospector.get_metadata() returns per-step: system_key, user_key, instructions_class, instructions_schema (JSON schema). But NO actual prompt template content. The Prompt table (llm_pipeline/db/prompt.py) stores the content with fields: prompt_key, prompt_type (system/user), content, step_name, required_variables.

**Required changes:**
1. New endpoint: GET /pipelines/{name}/steps/{step_name}/prompts (or similar)
2. Requires DBSession dependency (unlike existing /pipelines routes which are class-level introspection only)
3. Query Prompt table by step_name + prompt_key (keys available from introspection metadata)
4. Return: system prompt content, user prompt content, required_variables, version
5. Frontend: new hook + types for instruction content response

**Key code locations:**
- `llm_pipeline/ui/routes/pipelines.py` -- add new endpoint or sub-router
- `llm_pipeline/db/prompt.py` -- Prompt model (read-only access)
- `llm_pipeline/ui/frontend/src/api/types.ts` -- new response types
- New hook file or extend existing API hooks

### Impact on Frontend Architecture

With server-side step_name filter:
- `useStepEvents(runId, stepName, runStatus?)` calls `useEvents(runId, { step_name: stepName }, runStatus)` -- no client-side filtering needed
- Event pagination no longer a concern per step (typical step has 5-15 events, well under limit=100)
- RunDetailPage's existing useEvents call (no step_name filter) remains unchanged for the timeline/event log

With instruction content endpoint:
- Instructions tab has full prompt templates to display (not just logged_keys/instruction_count)
- New `useStepInstructions(pipelineName, stepName)` hook needed
- Data is static per pipeline definition (staleTime: Infinity appropriate)
