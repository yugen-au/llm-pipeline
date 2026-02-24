# Task Summary

## Work Completed

Implemented the Step Detail slide-over panel (task 35) across 8 implementation steps spanning backend schema changes, a new API endpoint, and a full frontend rewrite.

**Backend (steps 1-3):** Added a nullable `step_name` column to `PipelineEventRecord` with a composite `(run_id, step_name)` index, plus an idempotent ALTER TABLE migration for existing SQLite DBs (including index creation via `CREATE INDEX IF NOT EXISTS`). Added `step_name` query filter to the events API. Added a new `GET /pipelines/{name}/steps/{step_name}/prompts` endpoint that returns instruction content by scoping the Prompt query through pipeline introspection to prevent cross-pipeline prompt leakage.

**Frontend (steps 4-8):** Updated TypeScript types with event_data interfaces and StepPromptsResponse. Installed shadcn/ui Sheet and Tabs components via CLI. Created `useStepEvents` and `useStepInstructions` hooks. Rewrote `StepDetailPanel` from a ~50-line manual a11y implementation (focus trap, Escape handler, backdrop) to a shadcn Sheet with 7 tabs (Input, Prompts, LLM Response, Instructions, Context Diff, Extractions, Meta). Rewrote tests for Radix portal DOM structure (10 tests, up from 8).

**Review fixes:** Added missing index migration for existing DBs; fixed prompt endpoint cross-pipeline leakage using introspection-derived prompt keys.

---

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/frontend/src/components/ui/sheet.tsx` | shadcn/ui Sheet component (Radix Dialog wrapper with slide animations) |
| `llm_pipeline/ui/frontend/src/components/ui/tabs.tsx` | shadcn/ui Tabs component (Radix Tabs wrapper with CVA variants) |
| `llm_pipeline/ui/frontend/src/api/pipelines.ts` | `useStepInstructions` hook fetching step prompt content |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/events/models.py` | Added nullable `step_name` column and composite index `ix_pipeline_events_run_step (run_id, step_name)` to `PipelineEventRecord` |
| `llm_pipeline/events/handlers.py` | Added ALTER TABLE migration + CREATE INDEX migration in `__init__`; emit now extracts and persists `step_name` via `getattr(event, "step_name", None)` |
| `llm_pipeline/ui/routes/events.py` | Added `step_name: Optional[str] = None` to `EventListParams` with conditional WHERE clauses on count and data queries |
| `llm_pipeline/ui/routes/pipelines.py` | Added `StepPromptItem`, `StepPromptsResponse` models and `GET /{name}/steps/{step_name}/prompts` endpoint with introspection-based prompt key scoping |
| `llm_pipeline/ui/frontend/src/api/types.ts` | Added `step_name?: string` to `EventListParams`; added `LLMCallStartingData`, `LLMCallCompletedData`, `ContextUpdatedData`, `ExtractionCompletedData`, `StepPromptItem`, `StepPromptsResponse` interfaces |
| `llm_pipeline/ui/frontend/src/api/query-keys.ts` | Added `stepPrompts(name, stepName)` factory to `queryKeys.pipelines` |
| `llm_pipeline/ui/frontend/src/api/events.ts` | Added `useStepEvents(runId, stepName, runStatus?)` hook delegating to `useEvents` with step_name filter |
| `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx` | Full rewrite: Sheet+Tabs replaces manual a11y; 7 private tab content components; 4 data sources per step |
| `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.test.tsx` | Full rewrite for Radix portal structure; 10 tests (was 8); mocks for 4 hooks |

---

## Commits Made

| Hash | Message |
| --- | --- |
| `0e4b66d` | docs(implementation-A): master-35-step-detail-panel (step_name column + events filter + step-1/2 impl docs) |
| `372b90d` | docs(implementation-A): master-35-step-detail-panel (step-1 impl doc) |
| `9efc291` | docs(implementation-B): master-35-step-detail-panel (instruction content endpoint + step-3 impl doc) |
| `dbf673b` | docs(implementation-C): master-35-step-detail-panel (shadcn Sheet/Tabs, TS types, query-keys) |
| `131d501` | chore(state): master-35-step-detail-panel -> implementation (step-4 impl doc) |
| `3da8801` | docs(implementation-D): master-35-step-detail-panel (useStepEvents + useStepInstructions hooks) |
| `76608e3` | docs(implementation-E): master-35-step-detail-panel (StepDetailPanel.test.tsx rewrite) |
| `8aee44e` | docs(implementation-E): master-35-step-detail-panel (StepDetailPanel.tsx full rewrite + step-7 doc) |
| `34e79ff` | docs(implementation-E): master-35-step-detail-panel (step-8 test impl doc) |
| `930a28c` | chore(state): master-35-step-detail-panel -> testing (TESTING.md initial results) |
| `af9e67b` | docs(fixing-review-A): master-35-step-detail-panel (CREATE INDEX migration fix in handlers.py) |
| `5f2badc` | docs(fixing-review-B): master-35-step-detail-panel (cross-pipeline prompt scoping fix in pipelines.py) |
| `f39d9d7` | chore(state): master-35-step-detail-panel -> testing (TESTING.md re-verification after review fixes) |
| `2b80fcc` | chore(state): master-35-step-detail-panel -> review (REVIEW.md final approval) |

---

## Deviations from Plan

- **useRunContext added as 4th data source in StepContent.** Plan listed 3 data sources (useStep, useStepEvents, useStepInstructions). During implementation, `useRunContext` was added to provide context snapshots for the Input and Context Diff tabs without needing to fetch unfiltered events. This leverages TanStack Query cache deduplication since RunDetailPage already calls useRunContext for the same runId.

- **pipelines.ts was modified rather than created.** Plan described creating a new `src/api/pipelines.ts` for `useStepInstructions`. The file already existed with `usePipelines` and `usePipeline` hooks; `useStepInstructions` was added as a new export to the existing file.

- **Prompt endpoint query strategy changed from plan.** Plan specified filtering Prompt table by `step_name`. Review identified cross-pipeline leakage risk (no pipeline_name column on Prompt table). Fix replaced step_name filter with introspection-derived `prompt_key.in_(declared_keys)` - a better approach that works within existing schema constraints.

- **Index migration added post-review.** Plan's ALTER TABLE migration only added the column. Review found the composite index was not created for existing DBs (create_all skips existing tables). A second `CREATE INDEX IF NOT EXISTS` block was added to `handlers.py` as a review fix.

- **Tab default switched from plan.** Plan specified `Tabs defaultValue="meta"` with the order: input, prompts, response, instructions, context, extractions, meta. Implementation kept meta as default but the TabsTrigger order in the rendered list follows: meta, input, prompts, response, instructions, context, extractions (meta first for immediate visibility on open).

---

## Issues Encountered

### ALTER TABLE migration did not create composite index on existing DBs
**Resolution:** Added a second try/except block in `SQLiteEventHandler.__init__` after the ALTER TABLE block, running `CREATE INDEX IF NOT EXISTS ix_pipeline_events_run_step ON pipeline_events (run_id, step_name)`. The `IF NOT EXISTS` clause makes it idempotent for both new and existing DBs.

### Prompt endpoint returned prompts from all pipelines sharing a step_name
**Resolution:** Replaced the `Prompt.step_name == step_name` filter with introspection-based scoping. The endpoint now uses `PipelineIntrospector` to collect declared prompt keys (`system_key`, `user_key`) for the matching step within the named pipeline, then queries `Prompt.prompt_key.in_(declared_keys)`. Returns empty list if no keys declared. This eliminates cross-pipeline leakage without requiring schema changes.

### Radix portal structure broke test selectors
**Resolution:** Rewrote all test assertions for Sheet/portal DOM structure. Replaced CSS translate-class checks with `data-state="open"/"closed"` attribute checks. Used `screen.getByRole` (searches full document, portal-safe) instead of `container.querySelector`. Added `useRunContext` mock alongside existing `useStep`, `useStepEvents`, `useStepInstructions` mocks. All 10 tests pass.

### Pre-existing test failure: test_events_router_prefix (unrelated to task 35)
**Resolution:** Not fixed in task 35. The test at `tests/test_ui.py:143` asserts `r.prefix == "/events"` but the router prefix has been `/runs/{run_id}/events` since task 21 changed it without updating the test. Documented in TESTING.md with a recommendation to fix in a separate commit.

---

## Success Criteria

- [x] `PipelineEventRecord` has nullable `step_name` column with `(run_id, step_name)` index - verified in `llm_pipeline/events/models.py`
- [x] `SQLiteEventHandler.emit` populates `step_name` from event for step-scoped events - `getattr(event, "step_name", None)` in `handlers.py`
- [x] Existing DBs receive column via ALTER TABLE migration on startup without error - try/except OperationalError in `handlers.py`
- [x] Existing DBs also receive composite index via CREATE INDEX IF NOT EXISTS - second try/except block in `handlers.py`
- [x] `GET /api/runs/{run_id}/events?step_name=x` returns only events for that step - WHERE clause in `events.py`
- [x] `GET /api/pipelines/{name}/steps/{step_name}/prompts` returns prompt content scoped to pipeline - introspection-based query in `pipelines.py`
- [x] `EventListParams` TS interface has `step_name?: string` - `types.ts`
- [x] `useStepEvents` hook exists and passes step_name filter to backend - `events.ts`
- [x] `useStepInstructions` hook exists with `staleTime: Infinity` - `pipelines.ts`
- [x] shadcn Sheet and Tabs components present - `src/components/ui/sheet.tsx` and `src/components/ui/tabs.tsx`
- [x] `StepDetailPanel` uses Sheet (no manual focus-trap or Escape handler code) - `StepDetailPanel.tsx`
- [x] Panel width is `w-[600px]` per spec - SheetContent className in `StepDetailPanel.tsx`
- [x] All 7 tabs render without error - TabsTrigger values: meta, input, prompts, response, instructions, context, extractions
- [x] Prompts tab shows all LLM calls (consensus = multiple) - filters all `llm_call_starting` events, not just first
- [x] 10 frontend tests pass (was 8, added 2 new) - StepDetailPanel.test.tsx
- [x] Backend: 766/767 tests pass (1 pre-existing failure from task 21 unrelated to task 35)
- [x] TypeScript build clean: tsc -b and vite build succeed with zero errors

---

## Recommendations for Follow-up

1. Fix pre-existing `test_events_router_prefix` failure: update `tests/test_ui.py:143` to assert `r.prefix == "/runs/{run_id}/events"`. This is a 1-line fix that should be a standalone commit unrelated to task 35.

2. Rich JSON diff visualization for Context Diff tab: task 36 is the recommended vehicle. The current implementation shows before/after JSON blocks with a `new_keys` badge list. A diff library (e.g., `react-diff-viewer`) would make context changes more scannable.

3. `useStepEvents` empty-string cache pollution: when `stepName` is falsy, the hook passes empty string to the query key, creating a wasted cache entry `['runs', '', 'events', { step_name: '' }]`. Minor improvement: pass `undefined` as step_name when falsy to skip the entry entirely.

4. React key stability in tab content: `PromptsTab`, `ResponseTab`, and `ExtractionsTab` use array index as React key (`key={i}`). A more stable key combining `event.timestamp + call_index` would improve reconciliation correctness if event ordering ever changes.

5. Meta tab granularity: the Meta tab currently waits for all events to load before showing step metadata (model, execution time, created_at). These fields come from `useStep` which resolves independently. Splitting the loading gate would allow Meta tab content to appear while event data is still fetching.

6. `ExtractionCompletedData.execution_time_ms` TypeScript type: documented as `number` but the Python source uses `float`. The distinction is cosmetically inaccurate (both serialize identically via JSON) but could be annotated as `/** milliseconds, may be fractional */` for clarity.
