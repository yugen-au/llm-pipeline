# Testing Results

## Summary
**Status:** passed

Backend: 766/767 tests pass. 1 pre-existing failure in `test_events_router_prefix` (introduced in task 21, not task 35 - see Issues). Frontend: 90/90 tests pass, TypeScript build succeeds with no errors or warnings.

---

## Re-verification Run (after review fixes)

**Status:** passed - identical result to initial run. Review fixes confirmed present and no regressions introduced.

### Review Fix 1: CREATE INDEX migration (Step 1)
`handlers.py` line 181: `CREATE INDEX IF NOT EXISTS ix_pipeline_events_run_step` - confirmed present. Ensures the composite index is created on existing DBs that received the column via `ALTER TABLE` but not the index.

### Review Fix 2: Cross-pipeline prompt isolation (Step 3)
`pipelines.py` lines 153-172: Endpoint now uses `PipelineIntrospector` to collect `declared_keys` for the requested step within the named pipeline, then queries `Prompt` filtered by those keys only. Prevents prompt rows from a same-named step in a different pipeline from appearing in results.

### Backend Pass Rate: 766/767 (unchanged)
```
1 failed, 766 passed, 3 warnings in 119.78s
FAILED tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix (pre-existing, task 21)
```

### Frontend Pass Rate: 90/90 (unchanged)
```
Test Files  9 passed (9)
      Tests  90 passed (90)
  Duration  8.24s
```

### Build: clean (unchanged)
```
tsc -b && vite build - 2090 modules transformed, built in 6.10s, no errors
```

## Automated Testing

### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| existing pytest suite | Backend Python unit/integration tests | `tests/` |
| existing vitest suite | Frontend TypeScript component tests | `llm_pipeline/ui/frontend/src/` |

### Test Execution

**Backend Pass Rate:** 766/767 tests
```
.......................................F...
================================== FAILURES ===================================
________________ TestRoutersIncluded.test_events_router_prefix ________________
tests\test_ui.py:143: in test_events_router_prefix
    assert r.prefix == "/events"
E   AssertionError: assert '/runs/{run_id}/events' == '/events'
============================== warnings summary ================================
1 failed, 766 passed, 3 warnings in 118.90s
```

**Frontend Pass Rate:** 90/90 tests
```
 ✓ src/test/smoke.test.ts (2 tests) 13ms
 ✓ src/lib/time.test.ts (24 tests) 35ms
 ✓ src/components/runs/StatusBadge.test.tsx (5 tests) 152ms
 ✓ src/components/runs/ContextEvolution.test.tsx (5 tests) 330ms
 ✓ src/components/runs/StepTimeline.test.tsx (14 tests) 391ms
 ✓ src/components/runs/Pagination.test.tsx (12 tests) 598ms
 ✓ src/components/runs/RunsTable.test.tsx (12 tests) 598ms
 ✓ src/components/runs/FilterBar.test.tsx (6 tests) 955ms
 ✓ src/components/runs/StepDetailPanel.test.tsx (10 tests) 1043ms

 Test Files  9 passed (9)
       Tests  90 passed (90)
   Duration  6.49s
```

### Failed Tests

#### TestRoutersIncluded.test_events_router_prefix
**Step:** Pre-existing issue from task 21 (not task 35)
**Error:** `assert '/runs/{run_id}/events' == '/events'` - test was written in task 19 asserting `/events`, but task 21 changed the router prefix to `/runs/{run_id}/events` without updating the test. Task 35 did not modify this test or the router prefix.

## Build Verification
- [x] TypeScript compilation: `tsc -b` succeeds with zero errors
- [x] Vite production build: `npm run build` succeeds, 2090 modules transformed
- [x] shadcn Sheet component present at `src/components/ui/sheet.tsx`
- [x] shadcn Tabs component present at `src/components/ui/tabs.tsx`
- [x] No TypeScript type errors in StepDetailPanel.tsx or hooks

## Success Criteria (from PLAN.md)
- [x] `PipelineEventRecord` has nullable `step_name` column with `(run_id, step_name)` index - verified in `llm_pipeline/events/models.py` lines 43-60
- [x] `SQLiteEventHandler.emit` populates `step_name` from event for step-scoped events - verified in `llm_pipeline/events/handlers.py` line 178
- [x] Existing DBs receive column via ALTER TABLE migration on startup without error - try/except block at handlers.py line 162-169
- [x] `GET /api/runs/{run_id}/events?step_name=x` returns only events for that step - WHERE clause added in events.py lines 83-90 and 98-105
- [x] `GET /api/pipelines/{name}/steps/{step_name}/prompts` returns prompt content from DB - endpoint at pipelines.py line 139
- [x] `EventListParams` TS interface has `step_name?: string` - verified in types.ts line 89
- [x] `useStepEvents` hook exists and passes step_name filter to backend - verified in events.ts lines 37-55
- [x] `useStepInstructions` hook exists with `staleTime: Infinity` - verified in pipelines.ts lines 54-70
- [x] shadcn Sheet and Tabs components present at `src/components/ui/sheet.tsx` and `src/components/ui/tabs.tsx`
- [x] `StepDetailPanel` uses Sheet (no manual focus-trap or Escape handler code) - Sheet with `open/onOpenChange` at StepDetailPanel.tsx line 550
- [x] Panel width is `w-[600px]` per spec - SheetContent className at StepDetailPanel.tsx line 551
- [x] All 7 tabs (Input, Prompts, LLM Response, Instructions, Context Diff, Extractions, Meta) render without error - TabsTrigger values: meta, input, prompts, response, instructions, context, extractions at lines 481-487
- [x] Prompts tab shows all LLM calls (consensus = multiple), not just first - filter for all `llm_call_starting` events
- [x] All existing 8 tests pass (rewritten for Sheet/portal) - 10 tests pass in StepDetailPanel.test.tsx
- [x] At least 1 new test for tab switching - confirmed 10 tests total (was 8 before, 2 new)

## Human Validation Required

### StepDetailPanel Sheet Rendering
**Step:** Step 7
**Instructions:** Open the UI, navigate to a run detail page, click on a step in the timeline to open the panel. Verify: (1) panel slides in from right as a Sheet, (2) all 7 tabs are visible, (3) clicking each tab switches content, (4) close button and clicking outside panel closes it.
**Expected Result:** Sheet opens at 600px width with tabs Meta, Input, Prompts, LLM Response, Instructions, Context Diff, Extractions. Each tab shows relevant content or empty state placeholder. Closing works via X button or clicking backdrop.

### Instruction Content Endpoint
**Step:** Step 3
**Instructions:** With a pipeline that has registered prompts, call `GET /api/pipelines/{name}/steps/{step_name}/prompts`. Also call with a pipeline name not in the registry.
**Expected Result:** Valid call returns `StepPromptsResponse` with prompt list. Unknown pipeline returns 404.

### step_name Filter on Events API
**Step:** Step 2
**Instructions:** Call `GET /api/runs/{run_id}/events?step_name=some_step` and compare with `GET /api/runs/{run_id}/events` (no filter).
**Expected Result:** Filtered response contains only events where `step_name` matches; unfiltered returns all events for the run.

### ALTER TABLE Migration
**Step:** Step 1
**Instructions:** Start the server against a pre-existing SQLite DB that lacks the `step_name` column. Check server logs for migration message.
**Expected Result:** Server starts without error; a log message indicates successful `ALTER TABLE` migration; events API works normally.

## Issues Found

### Pre-existing: test_events_router_prefix asserts wrong prefix
**Severity:** medium
**Step:** Not task 35 - this is a pre-existing issue from task 21 (master-21-steps-events-api)
**Details:** `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` asserts `r.prefix == "/events"` but the router has had prefix `/runs/{run_id}/events"` since task 21 changed it in commit `486680c`. The test was added in task 19 and was never updated when task 21 changed the prefix. Task 35 did not touch this test or the router prefix. Fix: update line 143 in `tests/test_ui.py` to assert `r.prefix == "/runs/{run_id}/events"`.

## Recommendations
1. Fix pre-existing `test_events_router_prefix` failure by updating the assertion in `tests/test_ui.py:143` to match the actual prefix `/runs/{run_id}/events`. This should be done as a separate quick fix (not part of task 35).
2. All task 35 success criteria are met. Frontend and backend implementations are complete and correct.
