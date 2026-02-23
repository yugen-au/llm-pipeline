# IMPLEMENTATION - STEP 7: RUNSTABLE COMPONENT
**Status:** completed

## Summary
Created RunsTable component composing shadcn Table/Tooltip, StatusBadge, and time utils into a paginated run list table with loading/error/empty states and row-click navigation.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/runs/RunsTable.tsx`, `llm_pipeline/ui/frontend/src/components/runs/RunsTable.test.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/RunsTable.tsx`
New component with props `runs: RunListItem[]`, `isLoading: boolean`, `isError: boolean`. 6 columns: Run ID (first 8 chars in `<code>`, full ID in Tooltip), Pipeline, Started (formatRelative + formatAbsolute tooltip), Status (StatusBadge), Steps (step_count ?? em-dash), Duration (total_time_ms / 1000 + "s", or em-dash). Loading renders 5 skeleton rows with animate-pulse. Error shows "Failed to load runs" in text-destructive. Empty shows "No runs found" in text-muted-foreground. Row click calls `navigate({ to: '/runs/$runId', params: { runId: run.run_id } })` with cursor-pointer hover:bg-muted/50.

### File: `llm_pipeline/ui/frontend/src/components/runs/RunsTable.test.tsx`
12 tests: column headers, truncated run ID rendering, pipeline names, relative timestamps (mocked formatRelative/formatAbsolute), StatusBadge status text, step count with em-dash fallback, duration formatting, row click navigation, loading skeleton (30 animate-pulse divs), error message with text-destructive class, empty state with text-muted-foreground class, cursor-pointer on data rows.

## Decisions
### RunListItem import source
**Choice:** Import from `@/api/types` (not `@/types/runs.ts`)
**Rationale:** No `src/types/runs.ts` file exists. RunListItem is defined in `src/api/types.ts` alongside all other API response types.

### Time mock strategy in tests
**Choice:** Mock `@/lib/time` module to return deterministic strings
**Rationale:** Avoids flaky time-dependent test output from Intl.RelativeTimeFormat while still verifying correct ISO strings are passed through.

### Em-dash handling in step count test
**Choice:** Use `getAllByText` for em-dash assertion since second mock run has both step_count=null and total_time_ms=null producing two em-dash cells
**Rationale:** `getByText` throws on multiple matches; asserting >= 1 match is sufficient to verify null fallback behavior.

## Verification
[x] RunsTable renders all 6 column headers
[x] Run ID truncated to 8 chars with full ID in tooltip trigger
[x] StatusBadge renders for each status
[x] formatRelative/formatAbsolute called for Started column
[x] Loading state shows 5 skeleton rows (30 animate-pulse divs)
[x] Error state shows "Failed to load runs" with text-destructive
[x] Empty state shows "No runs found" with text-muted-foreground
[x] Row click navigates to /runs/$runId with correct params
[x] All 12 RunsTable tests pass
[x] Full test suite (51 tests across 6 files) passes

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] COLUMN_COUNT could drift from actual column count - derived from COLUMNS array
[x] Test data uses future dates (2026) - use vi.setSystemTime with relative date constants

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/components/runs/RunsTable.tsx`
Replaced `const COLUMN_COUNT = 6` with `const COLUMNS = [...] as const` array + `COLUMN_COUNT = COLUMNS.length`. Header now renders via `COLUMNS.map()` instead of hardcoded `<TableHead>` elements.
```
# Before
const COLUMN_COUNT = 6
...
<TableHead>Run ID</TableHead>
<TableHead>Pipeline</TableHead>
...

# After
const COLUMNS = ['Run ID', 'Pipeline', 'Started', 'Status', 'Steps', 'Duration'] as const
const COLUMN_COUNT = COLUMNS.length
...
{COLUMNS.map((col) => (
  <TableHead key={col}>{col}</TableHead>
))}
```

#### File: `llm_pipeline/ui/frontend/src/components/runs/RunsTable.test.tsx`
Added `vi.useFakeTimers()` / `vi.setSystemTime(new Date(NOW))` in `beforeEach` and `vi.useRealTimers()` in `afterEach`. Mock data dates changed from hardcoded 2026 strings to named constants (`NOW`, `ONE_HOUR_AGO`, `TWO_HOURS_AGO`) relative to a fixed system time. Test assertions updated to reference constants. Click test uses `vi.useRealTimers()` locally to avoid Radix Tooltip timer deadlock during pointer events.
```
# Before
const mockRuns = [{ started_at: '2026-02-23T10:00:00Z', ... }]
expect(screen.getByText('relative(2026-02-23T10:00:00Z)'))

# After
const NOW = '2025-06-15T12:00:00.000Z'
const TWO_HOURS_AGO = '2025-06-15T10:00:00.000Z'
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date(NOW)) })
afterEach(() => { vi.useRealTimers() })
const mockRuns = [{ started_at: TWO_HOURS_AGO, ... }]
expect(screen.getByText(`relative(${TWO_HOURS_AGO})`))
```

### Verification
[x] All 12 RunsTable tests pass
[x] Full test suite (57 tests across 6 files) passes
[x] COLUMN_COUNT derived from COLUMNS.length (adding/removing column auto-updates colspan)
[x] Headers rendered via COLUMNS.map() (single source of truth)
[x] Test dates are self-documenting via named constants relative to fixed NOW
[x] Click test works correctly with Radix Tooltip by restoring real timers locally
