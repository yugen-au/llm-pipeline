# IMPLEMENTATION - STEP 5: STEPS HOOKS
**Status:** completed

## Summary
Created `src/api/steps.ts` with `useSteps` and `useStep` TanStack Query hooks for the Steps API. Both accept optional `runStatus` param enabling dynamic staleTime without requiring consumers to fetch the run separately.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/steps.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/steps.ts`
New file with two hooks:

- `useSteps(runId, runStatus?)` - fetches step list for a run. Terminal runs get `staleTime: Infinity`, active runs get `staleTime: 5_000` with `refetchInterval: 3_000`.
- `useStep(runId, stepNumber, runStatus?)` - fetches single step detail. Terminal runs get `staleTime: Infinity`, active runs get `staleTime: 30_000` (no polling; list polling handles discovery).

Both import from `./client`, `./query-keys`, `./types` per plan. Pattern matches `events.ts` (step 6) which was implemented first.

## Decisions
### useStep staleTime for active runs
**Choice:** 30s staleTime, no refetchInterval (unlike useSteps which polls at 3s)
**Rationale:** Step detail changes less frequently than the step list. The step list polling at 3s handles discovery of new steps; individual step detail only needs refresh on navigation or manual refetch. This matches the plan spec exactly.

### runStatus param type
**Choice:** `RunStatus | string` union (not just `RunStatus`)
**Rationale:** Consistent with events.ts pattern. Backend may return status values outside the strict `RunStatus` union; accepting `string` prevents type errors from unexpected statuses while `isTerminalStatus` still works correctly.

## Verification
[x] TypeScript compilation passes (`npx tsc --noEmit` - clean)
[x] No semicolons, single quotes throughout
[x] Imports use `import type` for type-only imports per verbatimModuleSyntax
[x] Dynamic staleTime matches plan spec for both hooks
[x] Both hooks accept optional runStatus param
[x] Query keys use centralized factory from query-keys.ts

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] Missing `enabled` guard: `useSteps` and `useStep` lacked `enabled: Boolean(runId)` to prevent fetching with empty string runId (404 on `/runs//steps`)

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/api/steps.ts`
Added `enabled: Boolean(runId)` to both `useSteps` and `useStep` query options, consistent with `useRun` and `useRunContext` in runs.ts.

```
# Before (useSteps)
return useQuery({
  queryKey: queryKeys.runs.steps(runId),
  queryFn: () => ...
  staleTime: ...

# After (useSteps)
return useQuery({
  queryKey: queryKeys.runs.steps(runId),
  queryFn: () => ...
  enabled: Boolean(runId),
  staleTime: ...
```

```
# Before (useStep)
return useQuery({
  queryKey: queryKeys.runs.step(runId, stepNumber),
  queryFn: () => ...
  staleTime: ...

# After (useStep)
return useQuery({
  queryKey: queryKeys.runs.step(runId, stepNumber),
  queryFn: () => ...
  enabled: Boolean(runId),
  staleTime: ...
```

### Verification
[x] TypeScript compilation passes (`npx tsc --noEmit` - clean)
[x] Both hooks now have `enabled: Boolean(runId)` matching runs.ts pattern
[x] No other changes to hook logic
