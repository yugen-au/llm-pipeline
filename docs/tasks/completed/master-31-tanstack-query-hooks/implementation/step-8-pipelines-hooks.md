# IMPLEMENTATION - STEP 8: PIPELINES HOOKS
**Status:** completed

## Summary
Created TanStack Query hooks for the Pipelines API: `usePipelines()` for listing all pipelines and `usePipeline(name)` for fetching single pipeline metadata. Both are provisional hooks that will 404 until backend task 24 lands.

## Files
**Created:** `llm_pipeline/ui/frontend/src/api/pipelines.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/api/pipelines.ts`
New file with two hooks following the same patterns as existing hooks (events.ts, etc.):
- `usePipelines()` - queries `queryKeys.pipelines.all`, fetches `GET /pipelines`, returns `{ pipelines: PipelineListItem[] }`, uses default staleTime (static config data)
- `usePipeline(name)` - queries `queryKeys.pipelines.detail(name)`, fetches `GET /pipelines/{name}`, returns `PipelineMetadata`, conditionally enabled via `enabled: Boolean(name)`
- File-level TSDoc with `@remarks` noting task 24 dependency and `@provisional` marker
- Imports from `./client`, `./query-keys`, `./types` per plan

## Decisions
### Response shape for usePipelines
**Choice:** Typed as `{ pipelines: PipelineListItem[] }` (object wrapper, not bare array)
**Rationale:** Matches PLAN.md step 8 spec exactly. Consistent with anticipated backend response shape from task 24 which wraps the array in an object.

### No custom staleTime override
**Choice:** Rely on default QueryClient staleTime (30s) for both hooks
**Rationale:** Pipeline definitions are static configuration data that rarely change at runtime. The plan explicitly states "static config data, use default staleTime" for both hooks.

## Verification
[x] File created at correct path `src/api/pipelines.ts`
[x] File-level TSDoc includes `@remarks` about task 24 dependency
[x] `usePipelines()` uses `queryKeys.pipelines.all` and returns `{ pipelines: PipelineListItem[] }`
[x] `usePipeline(name)` uses `queryKeys.pipelines.detail(name)` with `enabled: Boolean(name)`
[x] Imports from `./client`, `./query-keys`, `./types` only
[x] No semicolons, single quotes throughout
[x] TypeScript strict compilation passes (`npx tsc --noEmit` clean)
[x] Pattern consistent with existing hooks (events.ts)
