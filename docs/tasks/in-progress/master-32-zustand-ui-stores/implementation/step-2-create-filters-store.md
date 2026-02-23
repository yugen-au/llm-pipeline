# IMPLEMENTATION - STEP 2: CREATE FILTERS STORE
**Status:** completed

## Summary
Created `src/stores/filters.ts` -- a Zustand v5 store for ephemeral run list filter state (pipeline name, date range). Uses `devtools` middleware only (no persist). All defaults null.

## Files
**Created:** `llm_pipeline/ui/frontend/src/stores/filters.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/stores/filters.ts`
New file. Exports `useFiltersStore` with `FiltersState` interface containing three nullable filter fields and three actions. Follows exact same code style as existing `websocket.ts` store (no semicolons, single quotes, 2-space indent, `create<T>()()` pattern).

```typescript
// Key structure
interface FiltersState {
  pipelineName: string | null
  startedAfter: string | null
  startedBefore: string | null
  setPipelineName: (name: string | null) => void
  setDateRange: (startedAfter: string | null, startedBefore: string | null) => void
  resetFilters: () => void
}

// Middleware: devtools only, no persist
export const useFiltersStore = create<FiltersState>()(
  devtools(storeImpl, { name: 'filters', enabled: import.meta.env.DEV })
)
```

## Decisions
### No persist middleware
**Choice:** devtools only, no persist
**Rationale:** Filters are ephemeral session state per PLAN.md. Restoring stale filters on reload would produce confusing UX.

### Null defaults (not empty string)
**Choice:** All fields default to `null`
**Rationale:** `toSearchParams` skips null/undefined values, so null means "omit from API query". Empty strings would produce empty query params.

## Verification
[x] `tsc --noEmit` passes with zero errors
[x] Code style matches existing websocket.ts (no semicolons, single quotes, 2-space indent)
[x] All three fields default to null
[x] No status or pagination fields in store
[x] devtools middleware with `enabled: import.meta.env.DEV`
[x] Interface exports FiltersState with correct types
[x] Actions: setPipelineName, setDateRange, resetFilters all present
