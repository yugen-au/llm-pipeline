# IMPLEMENTATION - STEP 16: RUNDETAILPAGE TESTS
**Status:** completed

## Summary
Integration-style tests for RunDetailPage route component covering loading, error, data display, step timeline rendering, and back navigation.

## Files
**Created:** llm_pipeline/ui/frontend/src/routes/runs/$runId.test.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/runs/$runId.test.tsx`
New test file with 5 tests:
- `shows loading skeleton when useRun isLoading=true` - asserts `.animate-pulse` elements
- `shows run ID and status badge when data loaded` - asserts truncated run_id, pipeline_name, and status badges
- `shows error state when useRun isError=true` - asserts "Run not found" text
- `renders StepTimeline with steps` - asserts 2 step names visible via deriveStepStatus
- `renders back navigation link` - asserts `<a href="/">` exists

Mocks: useRun, useRunContext, useSteps, useEvents, useWebSocket (no-op), useUIStore (full object return), createFileRoute (returns Route with useParams/useSearch stubs), Link (as `<a>`), @tanstack/zod-adapter, @/lib/time (deterministic formatRelative/formatAbsolute/formatDuration).

## Decisions
### Route component access pattern
**Choice:** Mock `createFileRoute` to return a function that merges `useParams`/`useSearch` stubs into the opts object, then import `Route.component` to get `RunDetailPage`
**Rationale:** `RunDetailPage` is not exported separately; it's only passed as `component` to `createFileRoute`. Mocking `createFileRoute` to pass through the component while adding route hook stubs is the cleanest approach.

### Status badge assertion with getAllByText
**Choice:** Use `getAllByText('completed')` instead of `getByText` for status assertion
**Rationale:** "completed" appears 3 times (run header badge + 2 step timeline badges). Using `getAllByText` avoids the multiple-elements error.

### useUIStore mock without selector
**Choice:** Mock `useUIStore` returning full object (not selector pattern)
**Rationale:** `$runId.tsx` calls `useUIStore()` with destructuring, not `useUIStore(selector)` like Sidebar does. Mock matches actual call pattern.

## Verification
[x] All 5 tests pass (`npx vitest run runs/$runId`)
[x] No new npm packages added
[x] No QueryClientProvider wrapping
[x] Test file co-located next to source
[x] Hook-level vi.mock() pattern used throughout
