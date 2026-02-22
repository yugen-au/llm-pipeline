# IMPLEMENTATION - STEP 4: RUNS HOOKS
**Status:** completed

## Summary
Created TanStack Query hooks for the Runs API with dynamic staleTime for active vs terminal runs.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/runs.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/runs.ts`
New file with 4 exported hooks and 1 internal helper:

- `toSearchParams(filters)` - filters null/undefined values, builds URLSearchParams string
- `useRuns(filters)` - paginated run list, global 30s staleTime
- `useRun(runId)` - single run, dynamic staleTime via query callback (Infinity if terminal, 5s+3s polling if active)
- `useCreateRun()` - mutation, invalidates `queryKeys.runs.all` on success
- `useRunContext(runId, status?)` - context evolution, dynamic staleTime via optional status param

## Decisions
### Dynamic staleTime via query callback vs data check
**Choice:** Used `staleTime: (query) => query.state.data?.status` callback pattern for `useRun`
**Rationale:** TanStack Query v5 supports function-form staleTime/refetchInterval receiving the query instance. This avoids needing a separate state variable or two-pass render. On first fetch (no data yet), falls back to 30s default. Once data arrives, switches to Infinity or 5s based on terminal status.

### No useRunListSearch convenience hook
**Choice:** Omitted `useRunListSearch()` wrapper around `Route.useSearch()` mentioned in plan step 4.8
**Rationale:** Route-specific search hooks are tightly coupled to route definitions (task 30). Including `Route.useSearch()` import here would create circular dependency risk. Task 33 (Run Dashboard) should define this in the route component itself. The hooks in this file are route-agnostic.

## Verification
[x] TypeScript strict compilation passes (`npx tsc --noEmit`)
[x] No semicolons, single quotes (Prettier config)
[x] Imports only from ./client, ./query-keys, ./types (Group A foundation)
[x] `useRun` dynamic staleTime: Infinity for terminal, 5_000 for active
[x] `useRun` refetchInterval: 3_000 for active, false for terminal
[x] `useCreateRun` invalidates queryKeys.runs.all on success
[x] `useRunContext` accepts optional status param for dynamic staleTime
[x] TSDoc notes data?.items (not data?.runs) per task 33 deviation
[x] toSearchParams filters null/undefined before serializing
