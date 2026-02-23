# Research Summary

## Executive Summary

Both research documents (step-1 frontend architecture, step-2 existing codebase patterns) are **verified accurate** against actual source files. All type definitions, API shapes, store interfaces, route schemas, and upstream task outputs match the codebase exactly. Two factual errors in the task 33 spec are confirmed: `data.runs` should be `data.items`, and `pending` status does not exist in the backend. No hidden architectural assumptions were found. All three CEO decisions received and incorporated: vitest included in scope, PAGE_SIZE=25, strict 3-status mapping.

## Domain Findings

### API Response Shape
**Source:** step-1, step-2, `src/api/types.ts`, `src/api/runs.ts`
- `RunListResponse.items` (not `.runs`) confirmed in types.ts line 30 and useRuns hook
- `RunListItem.status` typed as `string` (not `RunStatus` union) -- intentional for forward-compatibility
- Response includes `total`, `offset`, `limit` for pagination metadata
- Backend sorts by `started_at DESC`

### Status Values
**Source:** step-2, `llm_pipeline/state.py`, backend tests
- Backend `PipelineRun.status` default = `"running"`, described as "running, completed, failed"
- `RunStatus` type = `'running' | 'completed' | 'failed'` -- no `pending`
- `isTerminalStatus()` checks `completed || failed` in query-keys.ts
- Backend tests seed only `completed`, `failed`, `running` statuses
- **CEO decision:** strict 3-status mapping only. Step-1's defensive "pending" row is discarded. Unknown values get fallback gray but no named "pending" case.

### Filter Architecture (Hybrid URL + Zustand)
**Source:** step-1, step-2, `src/routes/index.tsx`, `src/stores/filters.ts`
- `page` and `status` are URL search params via TanStack Router + Zod validation (confirmed in index.tsx)
- `pipelineName`, `startedAfter`, `startedBefore` are Zustand ephemeral state (confirmed in filters.ts)
- Merge pattern: component reads both sources and constructs `RunListParams` for `useRuns()`
- Offset conversion: `(page - 1) * PAGE_SIZE`

### Upstream Task Outputs
**Source:** task 31 SUMMARY.md, task 32 SUMMARY.md, actual source files
- Task 31 (API hooks): all hooks verified working, `useRuns` uses global 30s staleTime, `apiClient` throws typed `ApiError`
- Task 32 (Zustand stores): `useUIStore` and `useFiltersStore` verified, `selectedStepId` is `number | null` (not `string`), bare side-effect import in main.tsx
- Both upstream tasks documented deviations from their original specs -- all handled correctly

### Component Infrastructure
**Source:** step-1, package.json, components.json, filesystem check
- `src/components/` directory is empty -- no shadcn components installed yet
- `shadcn` v3.8.5 is a devDependency, `components.json` configured (new-york style, neutral base, lucide icons)
- Install command documented: `npx shadcn@latest add table badge button select tooltip`
- `cn()` utility exists in `src/lib/utils.ts`

### Testing Infrastructure
**Source:** step-2, package.json
- No frontend test runner (no vitest, jest, or testing-library in package.json)
- Task 33 testStrategy requires rendering tests, filter tests, pagination tests, navigation tests
- Backend tests use starlette TestClient with in-memory SQLite -- not usable for frontend
- **CEO decision:** vitest setup is in-scope for task 33. Must add vitest, @testing-library/react, @testing-library/jest-dom, jsdom as devDependencies and configure vitest.config.ts

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should task 33 add vitest or defer frontend testing? | Include vitest setup in task 33 scope | Task 33 must add vitest + testing-library as a prerequisite step; testStrategy is fully in-scope |
| Default page size: 25 or 50? | 25 rows (more scannable, faster loads) | PAGE_SIZE = 25 constant; matches CEO preference for scannability over matching backend default |
| Include defensive "pending" color mapping in StatusBadge? | Strict 3 statuses only: running, completed, failed. No pending. | StatusBadge maps exactly 3 colors; unknown values get fallback gray but "pending" is not a named case |

## Assumptions Validated
- [x] `RunListResponse` uses `items` field (not `runs`) -- types.ts line 30
- [x] `RunStatus` has exactly 3 values: running, completed, failed -- types.ts line 15, state.py line 167
- [x] Status filter is URL param, not Zustand -- index.tsx line 7, filters.ts has no status field
- [x] Page is URL param (1-indexed), offset computed as (page-1)*limit -- index.tsx line 6
- [x] `selectedStepId` is `number | null` (not `string | null`) -- ui.ts line 17
- [x] shadcn configured but 0 components installed -- components.json exists, src/components/ empty
- [x] No frontend test runner installed -- package.json has no vitest/jest/testing-library
- [x] TanStack Router file-based routing with auto-generated route tree -- confirmed vite config + routeTree.gen.ts
- [x] Root layout provides flex-1 overflow-auto main area -- __root.tsx line 9
- [x] apiClient prepends /api, throws typed ApiError -- client.ts lines 11, 23
- [x] Query key factory matches documented structure -- query-keys.ts
- [x] Filters store fields default to null (omitted by toSearchParams) -- filters.ts lines 23-25
- [x] Zod v4 in use (not v3) -- package.json "zod": "^4.3.6"
- [x] No date utility library installed -- must use native Date/Intl for relative timestamps

## Open Items
- Empty state UI (0 runs) not specified in either research doc -- implementer must decide
- Error state UI (API failure) not specified -- useRuns returns isError/error but no error component pattern exists
- Loading state UI (isLoading) not specified -- no skeleton/spinner pattern established
- `useRunListSearch()` convenience hook mentioned in task 31 recommendations but not implemented -- task 33 should use `Route.useSearch()` directly per step-1 patterns

## Recommendations for Planning
1. **Update task 33 spec** to correct `data?.runs` to `data?.items` and remove `pending` from status color list
2. **Add vitest + testing-library** as first implementation step: install devDependencies, create vitest.config.ts, add test script to package.json
3. **Install shadcn components** as prerequisite step: `npx shadcn@latest add table badge button select tooltip`
4. **Use PAGE_SIZE = 25** (CEO confirmed)
5. **Strict 3-status StatusBadge** mapping running/completed/failed with fallback gray for truly unknown values (CEO confirmed no pending)
6. **Define loading/error/empty states** as sub-steps in the implementation plan -- use `text-muted-foreground` centered text for empty/error, simple spinner or skeleton rows for loading
7. **Stick with Route.useSearch()** directly rather than creating a wrapper hook -- matches existing patterns
