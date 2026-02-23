# IMPLEMENTATION - STEP 5: PAGINATION COMPONENT
**Status:** completed

## Summary
Created Pagination component with prev/next navigation via TanStack Router URL search params, plus comprehensive test suite (12 tests).

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/runs/Pagination.tsx`, `llm_pipeline/ui/frontend/src/components/runs/Pagination.test.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/Pagination.tsx`
New component. Props: `total`, `page`, `pageSize`. Computes `totalPages = Math.ceil(total / pageSize)`. Uses `useNavigate` from `@tanstack/react-router` with search function callback to update `page` param. Renders "Showing X-Y of Z" range label, "Page X of Y" label, Previous/Next buttons (shadcn `Button` variant="outline" size="sm"). Disables Previous when `page <= 1`, Next when `page >= totalPages || total === 0`.

### File: `llm_pipeline/ui/frontend/src/components/runs/Pagination.test.tsx`
12 tests covering: correct page label, record range display, range clamping on last page, zero-total edge case, Previous disabled on page 1, Previous enabled on page > 1, Next disabled on last page, Next disabled when total=0, Next enabled when not last page, navigate called with decremented page on Previous click, navigate called with incremented page on Next click, single-page edge case (total=pageSize). Mocks `useNavigate` via `vi.mock('@tanstack/react-router')`. Tests verify the search callback produces correct params by invoking it with mock prev state.

## Decisions
### Navigate approach: search function callback
**Choice:** `navigate({ to: '/', search: (prev) => ({ ...prev, page: page +/- 1 }) })`
**Rationale:** TanStack Router docs recommend search function callback to preserve existing search params. Matches pattern used in index.tsx route and avoids overwriting `status` param.

### Test strategy: mock useNavigate, verify callback output
**Choice:** Mock `useNavigate` to return `vi.fn()`, then invoke the `search` callback from the call args to verify correct page computation.
**Rationale:** Avoids needing a full router context in tests. Keeps tests focused on component logic rather than router integration. The search callback is a pure function, so testing its output is deterministic.

### "Page X of Y" fallback for zero total
**Choice:** Show "Page 1 of 1" when `totalPages` is 0 (via `totalPages || 1`).
**Rationale:** Avoids confusing "Page 1 of 0" display when no results exist. Both buttons are disabled so user cannot navigate.

## Verification
[x] All 12 tests pass (`npx vitest run src/components/runs/Pagination.test.tsx`)
[x] TypeScript type check passes (`tsc -b --noEmit`)
[x] Previous disabled on page 1
[x] Next disabled on last page and when total=0
[x] Record range shows correct "Showing X-Y of Z"
[x] Navigate called with correct search params on button clicks

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] (MEDIUM) Pagination hardcodes route path - refactored to callback props pattern matching FilterBar

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/components/runs/Pagination.tsx`
Removed `useNavigate` import and internal navigation. Added `onPageChange: (page: number) => void` prop. Buttons now call `onPageChange(page - 1)` / `onPageChange(page + 1)` directly.
```
# Before
import { useNavigate } from '@tanstack/react-router'
interface PaginationProps { total: number; page: number; pageSize: number }
// internally: navigate({ to: '/', search: ... })

# After
interface PaginationProps { total: number; page: number; pageSize: number; onPageChange: (page: number) => void }
// internally: onPageChange(page - 1) / onPageChange(page + 1)
```

#### File: `llm_pipeline/ui/frontend/src/components/runs/Pagination.test.tsx`
Removed `vi.mock('@tanstack/react-router')` and `mockNavigate`. Tests now pass `onPageChange={vi.fn()}` and assert it's called with correct page number directly.
```
# Before
expect(call.search({ page: 3, status: '' })).toEqual({ page: 2, status: '' })

# After
expect(onPageChange).toHaveBeenCalledWith(2)
```

#### File: `llm_pipeline/ui/frontend/src/routes/index.tsx`
Passes `onPageChange` callback to Pagination that calls navigate with updated page param.
```
# Before
<Pagination total={data?.total ?? 0} page={page} pageSize={PAGE_SIZE} />

# After
<Pagination total={...} page={page} pageSize={PAGE_SIZE}
  onPageChange={(newPage) => navigate({ to: '/', search: (prev) => ({ ...prev, page: newPage }) })} />
```

### Verification
[x] All 12 Pagination tests pass
[x] TypeScript type check passes
[x] Pagination component is now route-agnostic (no router imports)
[x] index.tsx passes onPageChange callback handling navigation
