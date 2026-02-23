# Research Summary

## Executive Summary

Both research documents (step-1 frontend patterns, step-2 backend API integration) are well-grounded and verified against the actual codebase. The proposed two-store architecture (ui.ts + filters.ts) is sound. The Zustand v5 patterns, middleware composition, and TanStack Query separation are all correct and consistent with the existing websocket.ts store. Four architectural ambiguities were identified and resolved via CEO Q&A. All assumptions are now validated and the research is ready for planning.

## Domain Findings

### Zustand v5 Pattern Consistency
**Source:** step-1-frontend-state-patterns.md, websocket.ts
Existing `useWsStore` in `src/stores/websocket.ts` uses `create<WsState>()((set) => ({...}))` -- the v5 double-call pattern. Research correctly identifies this as the baseline. Adding `devtools` and `persist` middleware (not in existing store) is additive. Middleware composition order `devtools(persist(...))` is correct per Zustand docs.

### Theme Implementation
**Source:** step-1-frontend-state-patterns.md, main.tsx, index.css
Verified: `main.tsx` line 17 has hardcoded `document.documentElement.classList.add('dark')`. CSS has both `:root` (light) and `.dark` (dark) OKLCH token sets. Research correctly identifies that `setTheme` must toggle `.dark` class as a side-effect (task spec omits this). FOUC prevention via module-level store creation is sound as long as the ui store is imported at root level (not lazily).

### Backend API Contract Alignment
**Source:** step-2-backend-api-integration.md, runs.py, pipelines.py, types.ts
Backend `RunListParams` verified: `pipeline_name`, `status`, `started_after`, `started_before`, `offset`, `limit`. Response uses `items` field (not `runs`). All Pydantic models match research descriptions exactly.

### Type Discrepancy (Out of Scope but Noted)
**Source:** step-2-backend-api-integration.md, pipelines.py, types.ts
Backend `PipelineListItem` has `strategy_count: Optional[int]`, `step_count: Optional[int]`, `registry_model_count: Optional[int]`, `error: Optional[str]`. Frontend `types.ts` types `strategy_count` and `step_count` as non-optional `number`, and omits `registry_model_count` and `error` entirely. Not blocking for task 32 but is a real type safety issue for downstream pipeline views.

### Task 30 Upstream Deviations
**Source:** master-30 SUMMARY.md
No deviations from plan. Design tokens in use (`bg-sidebar`, `bg-background`), not raw gray classes. Sidebar placeholder text confirms task 41 dependency. Zod 4 peer dep mismatch with `@tanstack/zod-adapter` accepted (runtime works).

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Filter store defaults: `''` (empty string) vs `null`? | **`null` -- omit from API query when unset** | Filters store uses `null` defaults. `toSearchParams` already skips null/undefined, so unset filters produce clean queries without empty-string params. Research step-1 code samples must use `null` not `''`. |
| selectedStepId type: `string \| null` vs `number \| null`? | **`number \| null` -- matches backend step_number: int** | UI store types `selectedStepId: number \| null`. No string-to-number conversion needed when calling GET /api/runs/{run_id}/steps/{step_number}. Research step-1 code sample must be updated from `string` to `number`. |
| Status filter: URL search param vs Zustand store ownership? | **URL-only via existing Zod search param -- filters store omits status** | Filters store does NOT include `status`. Status lives in URL search params (index.tsx Zod schema), making it shareable/bookmarkable. Filters store holds only: pipelineName, startedAfter, startedBefore. Simplifies store shape and avoids dual-ownership bugs. |
| Pagination: in filters store or URL-only? | **URL-only -- keep in URL search params, not in filters store** | Pagination stays in URL via existing `page` Zod search param. Filters store has no offset/limit fields. Task 33 computes offset from page number when calling useRuns(). |

## Assumptions Validated

- [x] Zustand v5 double-call `create<T>()()` pattern matches existing codebase (websocket.ts)
- [x] Actions co-located with state (consistent with websocket.ts)
- [x] Export naming `useXxxStore` matches existing convention
- [x] No semicolons, single quotes code style confirmed across all frontend files
- [x] TanStack Query owns all server state; Zustand is UI-only
- [x] `document.documentElement.classList.add('dark')` is hardcoded in main.tsx line 17
- [x] OKLCH design token system uses `.dark` class selector in index.css
- [x] `__root.tsx` sidebar is static `w-60` placeholder awaiting task 41
- [x] Backend RunListParams matches proposed filter fields exactly
- [x] Backend RunListResponse uses `items` (not `runs`)
- [x] devtools middleware addition is additive improvement over task spec (non-breaking)
- [x] `partialize` correctly excludes ephemeral state (selectedStepId, stepDetailOpen) from persistence
- [x] onRehydrateStorage will fire before first React render (store created at module-level import time)
- [x] PipelineListResponse uses `pipelines` field (for pipeline name dropdown in filters)
- [x] Filter store defaults use `null` (CEO confirmed) -- prevents empty-string params in API queries
- [x] `selectedStepId` typed as `number | null` (CEO confirmed) -- matches backend `step_number: int`
- [x] Status filter owned by URL search params only (CEO confirmed) -- filters store omits status
- [x] Pagination owned by URL search params only (CEO confirmed) -- filters store omits offset/limit

## Open Items

- PipelineListItem type discrepancy in types.ts (out of scope for task 32, track for future task)
- FOUC edge case: ui store must be imported at root level, not via lazy/code-split route, to ensure hydration before first paint

## Recommendations for Planning

1. **Filters store shape (resolved):** `{ pipelineName: string | null, startedAfter: string | null, startedBefore: string | null }` with `null` defaults. No `status` field (URL-owned). No `offset`/`limit` (URL-owned). Actions: `setPipelineName`, `setDateRange`, `resetFilters`.
2. **UI store shape (resolved):** `{ sidebarCollapsed: boolean, theme: 'dark' | 'light', selectedStepId: number | null, stepDetailOpen: boolean }`. `selectedStepId` is `number` to match backend `step_number: int`.
3. **Theme side-effect:** `setTheme` must toggle `document.documentElement.classList` between adding/removing `'dark'`. Remove hardcoded `classList.add('dark')` from `main.tsx` -- let `onRehydrateStorage` in persist middleware apply the persisted theme.
4. **Root-level import:** Import ui store in `__root.tsx` (or a layout-level component) so persist hydration fires before first paint, preventing FOUC on theme.
5. **devtools middleware:** Add to both stores with `enabled: import.meta.env.DEV` guard. Name stores `'ui'` and `'filters'` for DevTools panel clarity.
6. **persist partialize:** Only persist `sidebarCollapsed` and `theme` from ui store. Exclude `selectedStepId` and `stepDetailOpen` (ephemeral per-session state). Filters store should NOT use persist (transient working state).
7. **Downstream awareness:** Task 33 (Run List View) will consume filters store + URL search params (status, page) to call `useRuns()`. Task 41 (Sidebar) will consume `sidebarCollapsed` and `toggleSidebar` from ui store. Neither task should need to modify these store shapes.
