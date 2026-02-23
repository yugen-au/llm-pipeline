# Task Summary

## Work Completed

Created two Zustand v5 UI-only state stores for the LLM pipeline dashboard and removed the hardcoded dark theme bootstrap from main.tsx.

- `src/stores/ui.ts`: persisted store for sidebar collapse, theme, step selection, detail panel. Uses `devtools(persist(...))` middleware; `onRehydrateStorage` applies saved theme class before first render; `partialize` restricts persistence to `sidebarCollapsed` and `theme` only.
- `src/stores/filters.ts`: ephemeral store for run list filters (pipeline name, date range). Uses `devtools` only (no persist); all fields default to `null` so `toSearchParams` omits them cleanly.
- `src/main.tsx`: removed `document.documentElement.classList.add('dark')`; replaced with side-effect import `import '@/stores/ui'` to trigger `onRehydrateStorage` hydration before first React render.

Architecture review passed with no critical, high, or medium issues. Build (`tsc -b --noEmit`) passes clean.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/frontend/src/stores/ui.ts` | Zustand v5 store: sidebar, theme (persisted), selectedStepId, stepDetailOpen |
| `llm_pipeline/ui/frontend/src/stores/filters.ts` | Zustand v5 store: pipelineName, startedAfter, startedBefore (ephemeral, no persist) |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/ui/frontend/src/main.tsx` | Removed hardcoded `classList.add('dark')`; added `import '@/stores/ui'` side-effect import |

## Commits Made

| Hash | Message |
| --- | --- |
| `1d45313` | docs(implementation-A): master-32-zustand-ui-stores (filters.ts + step-2 doc) |
| `36a3f63` | docs(implementation-A): master-32-zustand-ui-stores (ui.ts + step-1 doc) |
| `5a7497b` | docs(implementation-B): master-32-zustand-ui-stores (main.tsx + step-3 doc) |

## Deviations from Plan

- Step 3 used `import '@/stores/ui'` (bare side-effect import) instead of `import { useUIStore } from '@/stores/ui'`. Plan said "Add import of `useUIStore`"; the bare form was chosen to avoid an unused-import lint warning since main.tsx does not consume any store export. Functionally identical -- module executes and `onRehydrateStorage` fires either way.

## Issues Encountered

None

## Success Criteria

- [x] `src/stores/ui.ts` exists and exports `useUIStore` with `sidebarCollapsed`, `theme`, `selectedStepId`, `stepDetailOpen` state and `toggleSidebar`, `setTheme`, `selectStep`, `closeStepDetail` actions
- [x] `src/stores/filters.ts` exists and exports `useFiltersStore` with `pipelineName`, `startedAfter`, `startedBefore` state and `setPipelineName`, `setDateRange`, `resetFilters` actions
- [x] `selectedStepId` typed as `number | null` (not `string | null`)
- [x] `pipelineName`, `startedAfter`, `startedBefore` default to `null` (not `''`)
- [x] `status` and pagination fields absent from filters store
- [x] ui store persist key is `'llm-pipeline-ui'`
- [x] Only `sidebarCollapsed` and `theme` are persisted (partialize excludes ephemeral fields)
- [x] `onRehydrateStorage` applies `.dark` class from persisted theme on page load
- [x] `setTheme` toggles `document.documentElement.classList` as a side-effect
- [x] Hardcoded `document.documentElement.classList.add('dark')` removed from `main.tsx`
- [x] Both stores use `devtools` middleware with `enabled: import.meta.env.DEV`
- [x] `tsc -b --noEmit` passes with no type errors
- [x] Code style matches existing: no semicolons, single quotes, 2-space indent

## Recommendations for Follow-up

1. Downstream task 33 (run list component) should consume `useFiltersStore` for filter state; `toSearchParams` integration should skip null fields as intended.
2. Downstream task 41 (step detail panel) should consume `useUIStore` selectors `selectStep`, `closeStepDetail`, and `stepDetailOpen` to drive panel open/close state.
3. `UIState` and `FiltersState` interfaces are non-exported (matching `WsState` convention). If downstream tasks need typed selector props, use `typeof useUIStore` / `typeof useFiltersStore` via Zustand's `StoreApi` inference rather than importing the interfaces directly.
4. Theme toggle UI (a button to call `setTheme`) is not yet implemented -- the store is ready but no component surfaces it to the user yet.
