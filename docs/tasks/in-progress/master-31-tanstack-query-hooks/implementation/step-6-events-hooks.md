# IMPLEMENTATION - STEP 6: EVENTS HOOKS
**Status:** completed

## Summary
Created `useEvents` TanStack Query hook for fetching pipeline run events with dynamic staleTime based on run status and filter support via URLSearchParams.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/events.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/events.ts`
New file exporting `useEvents(runId, filters, runStatus?)` hook.

- `buildEventParams` helper filters out undefined/null values from `EventListParams` before constructing URLSearchParams, preventing empty-string query params
- `useEvents` uses `queryKeys.runs.events(runId, filters)` for hierarchical cache keys
- Dynamic staleTime: `Infinity` for terminal runs, `5_000` for active/unknown
- Polling: `refetchInterval: 3_000` for active runs, `false` for terminal
- Default `filters` to `{}` so callers can omit the argument

## Decisions
### buildEventParams as private helper
**Choice:** Extracted URL param building into a local `buildEventParams` function rather than inline
**Rationale:** Keeps the hook body readable; same pattern will be used by runs.ts and prompts.ts. Not exported since each hook file may have slightly different param types.

### Default filters parameter
**Choice:** Default `filters` to `{}` in the function signature
**Rationale:** Most consumers will call `useEvents(runId)` without filters initially. Defaulting avoids forcing an empty object at every call site.

## Verification
[x] TypeScript strict compilation passes (`npx tsc --noEmit`)
[x] No semicolons, single quotes throughout
[x] Imports use `import type` for type-only imports per verbatimModuleSyntax
[x] URLSearchParams omits undefined/null filter values
[x] Dynamic staleTime: Infinity for terminal, 5s for active
[x] refetchInterval: 3s for active runs, false for terminal

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Missing `enabled` guard: added `enabled: Boolean(runId)` to prevent fetching with empty strings, consistent with useSteps, useRun, useRunContext
[x] URLSearchParams dedup: confirmed already resolved -- events.ts imports shared `toSearchParams` from `./types`, no local `buildEventParams` remains

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/api/events.ts`
Added `enabled: Boolean(runId)` to useQuery options.
```
# Before
  return useQuery({
    queryKey: queryKeys.runs.events(runId, filters),
    queryFn: () =>
      apiClient<EventListResponse>('/runs/' + runId + '/events' + toSearchParams(filters)),
    staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 5_000,

# After
  return useQuery({
    queryKey: queryKeys.runs.events(runId, filters),
    queryFn: () =>
      apiClient<EventListResponse>('/runs/' + runId + '/events' + toSearchParams(filters)),
    enabled: Boolean(runId),
    staleTime: runStatus && isTerminalStatus(runStatus) ? Infinity : 5_000,
```

### Verification
[x] TypeScript strict compilation passes (`npx tsc --noEmit`)
[x] `enabled: Boolean(runId)` matches pattern in steps.ts, runs.ts
[x] `toSearchParams` import from `./types` already in place (no local helper)
