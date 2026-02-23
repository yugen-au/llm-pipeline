# IMPLEMENTATION - STEP 1: CREATE UI STORE
**Status:** completed

## Summary
Created `src/stores/ui.ts` Zustand v5 store for UI-only state: sidebar collapse, theme, step selection, detail panel. Uses `devtools(persist(...))` middleware with localStorage persistence for sidebar+theme, `onRehydrateStorage` for theme class application.

## Files
**Created:** `llm_pipeline/ui/frontend/src/stores/ui.ts`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/stores/ui.ts`
New file. Exports `Theme` type and `useUIStore` Zustand store with:
- State: `sidebarCollapsed`, `theme`, `selectedStepId`, `stepDetailOpen`
- Actions: `toggleSidebar`, `setTheme` (with classList side-effect), `selectStep`, `closeStepDetail`
- Middleware: `devtools(persist(storeImpl, persistOpts), { name: 'ui', enabled: import.meta.env.DEV })`
- Persist: key `'llm-pipeline-ui'`, partialize excludes ephemeral fields, `onRehydrateStorage` applies `.dark` class

## Decisions
### Code style alignment
**Choice:** Matched existing `websocket.ts` conventions exactly
**Rationale:** No semicolons, single quotes, 2-space indent, JSDoc comment header, `create<T>()()` pattern -- all consistent with existing store

### onRehydrateStorage callback form
**Choice:** Used `() => (state) => {}` (returning a callback that runs after hydration)
**Rationale:** Zustand persist v5 `onRehydrateStorage` accepts a function that returns a post-hydration callback. The outer function runs before hydration, the returned callback receives hydrated state. Applying theme in the returned callback ensures we have the persisted value.

## Verification
[x] `tsc -b --noEmit` passes with zero errors
[x] Code style: no semicolons, single quotes, 2-space indent
[x] `Theme` type exported as `'dark' | 'light'`
[x] `selectedStepId` typed as `number | null`
[x] Persist key is `'llm-pipeline-ui'`
[x] Partialize returns only `sidebarCollapsed` and `theme`
[x] `onRehydrateStorage` applies `.dark` class with `'dark'` fallback
[x] `setTheme` toggles `classList` as side-effect
[x] `devtools` uses `enabled: import.meta.env.DEV`
[x] Defaults: sidebarCollapsed=false, theme='dark', selectedStepId=null, stepDetailOpen=false
