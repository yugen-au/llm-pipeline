# PLANNING

## Summary

Create two Zustand v5 stores for UI-only state in the LLM pipeline dashboard: `src/stores/ui.ts` (sidebar, theme, step selection, detail panel) and `src/stores/filters.ts` (run list filters: pipeline name and date range). The ui store uses `devtools(persist(...))` middleware to persist sidebar and theme preferences across reloads; filters store uses `devtools` only. The hardcoded `classList.add('dark')` in `main.tsx` is replaced by `onRehydrateStorage` in the ui store. Status, pagination remain URL-owned (out of scope).

## Plugin & Agents

**Plugin:** frontend-mobile-development
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Implementation**: Create both store files and update main.tsx theme bootstrap

## Architecture Decisions

### Store Count and File Separation
**Choice:** Two stores: `ui.ts` and `filters.ts`
**Rationale:** Single-responsibility separation. UI preferences (persisted) have fundamentally different lifecycle from transient filter state (session-only). Matches research and downstream consumer expectations from tasks 33 and 41.
**Alternatives:** Single combined store (rejected -- would require partial persistence over a heterogeneous shape, harder to reason about)

### Filter Field Set
**Choice:** `pipelineName: string | null`, `startedAfter: string | null`, `startedBefore: string | null` only
**Rationale:** CEO confirmed status is URL-owned (Zod search param in index.tsx), pagination is URL-owned (`page` search param). Null defaults omit fields from API query cleanly since `toSearchParams` skips null/undefined.
**Alternatives:** Include `status` in filters store (rejected -- dual ownership with URL causes sync bugs); empty string defaults (rejected -- produces empty-string params in API query)

### selectedStepId Type
**Choice:** `number | null`
**Rationale:** CEO confirmed. Matches backend `step_number: int` on GET /api/runs/{run_id}/steps/{step_number}. Avoids string-to-number conversion at call site.
**Alternatives:** `string | null` (rejected -- mismatches backend type)

### Persist Partialize
**Choice:** Only `sidebarCollapsed` and `theme` persisted; `selectedStepId` and `stepDetailOpen` excluded
**Rationale:** Step selection and panel state are ephemeral per-session. Restoring them across reloads would produce stale UI pointing to a step from a previous session.
**Alternatives:** Persist all ui state (rejected -- stale ephemeral state on reload)

### Theme Bootstrap
**Choice:** Remove hardcoded `classList.add('dark')` from `main.tsx`; replace with `onRehydrateStorage` in ui store that applies persisted theme to `document.documentElement`
**Rationale:** Enables true theme switching. `onRehydrateStorage` fires at module-load time (synchronous localStorage read), before first React render, so no FOUC. Default `'dark'` maintains current behavior for first-time visitors.
**Alternatives:** Keep hardcoded line and set theme separately (rejected -- two sources of truth for `.dark` class; switching would be overridden on reload)

### Middleware Composition
**Choice:** `devtools(persist(...), devtools_opts)` for ui store; `devtools(storeImpl, devtools_opts)` for filters store
**Rationale:** Outer devtools sees all state changes including persist-hydrated state. `enabled: import.meta.env.DEV` prevents production overhead. Names `'ui'` and `'filters'` for DevTools panel clarity.
**Alternatives:** Reversed order `persist(devtools(...))` (rejected -- devtools would not see hydration events)

## Implementation Steps

### Step 1: Create src/stores/ui.ts
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/ui/frontend/src/stores/ui.ts` with the following:
   - Export type `Theme = 'dark' | 'light'`
   - Interface `UIState` with fields: `sidebarCollapsed: boolean`, `theme: Theme`, `selectedStepId: number | null`, `stepDetailOpen: boolean`; actions: `toggleSidebar: () => void`, `setTheme: (theme: Theme) => void`, `selectStep: (stepId: number | null) => void`, `closeStepDetail: () => void`
   - Store creation: `create<UIState>()(devtools(persist(storeImpl, persistOpts), { name: 'ui', enabled: import.meta.env.DEV }))`
   - `persistOpts`: `name: 'llm-pipeline-ui'`, `partialize` returning only `{ sidebarCollapsed, theme }`, `onRehydrateStorage` applying/removing `.dark` class based on hydrated theme (fallback to `'dark'` if undefined)
   - `storeImpl` defaults: `sidebarCollapsed: false`, `theme: 'dark'`, `selectedStepId: null`, `stepDetailOpen: false`
   - `toggleSidebar`: flips `sidebarCollapsed`
   - `setTheme`: adds/removes `document.documentElement.classList` `'dark'` then `set({ theme })`
   - `selectStep`: sets `selectedStepId` to arg; sets `stepDetailOpen: true` if arg non-null, `false` if null
   - `closeStepDetail`: sets `stepDetailOpen: false`, `selectedStepId: null`
   - Imports: `create` from `'zustand'`, `persist` from `'zustand/middleware'`, `devtools` from `'zustand/middleware'`
   - Code style: no semicolons, single quotes, named function for store init if needed

### Step 2: Create src/stores/filters.ts
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Create `llm_pipeline/ui/frontend/src/stores/filters.ts` with the following:
   - Interface `FiltersState` with fields: `pipelineName: string | null`, `startedAfter: string | null`, `startedBefore: string | null`; actions: `setPipelineName: (name: string | null) => void`, `setDateRange: (startedAfter: string | null, startedBefore: string | null) => void`, `resetFilters: () => void`
   - Store creation: `create<FiltersState>()(devtools(storeImpl, { name: 'filters', enabled: import.meta.env.DEV }))`
   - `storeImpl` defaults: `pipelineName: null`, `startedAfter: null`, `startedBefore: null`
   - `setPipelineName`: `set({ pipelineName: name })`
   - `setDateRange`: `set({ startedAfter, startedBefore })`
   - `resetFilters`: resets all three fields to `null`
   - Imports: `create` from `'zustand'`, `devtools` from `'zustand/middleware'`
   - Code style: no semicolons, single quotes

### Step 3: Update main.tsx to remove hardcoded theme class
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/ui/frontend/src/main.tsx`, remove line 17: `document.documentElement.classList.add('dark')`
2. Add import of `useUIStore` from `'@/stores/ui'` (import triggers module-level store creation and `onRehydrateStorage` hydration before first render)
3. No other changes to main.tsx

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| FOUC on theme if ui store imported lazily | Medium | Import `useUIStore` (or the store module directly) at top of `main.tsx` so localStorage sync fires before first paint |
| First-time visitor has no persisted theme, `onRehydrateStorage` state is undefined | Medium | `onRehydrateStorage` callback guards with `state?.theme ?? 'dark'`; default is `'dark'` matching prior behavior |
| TypeScript error if `devtools`/`persist` types conflict with `create<T>()()` | Low | Follow exact Zustand v5 pattern from websocket.ts baseline: `create<T>()()` outermost; middleware types inferred from imports |
| Middleware import path wrong (v4 vs v5 paths differ) | Low | Import from `'zustand/middleware'` (correct for v5); verified against installed `zustand@^5.0.11` |
| Step 3 group B depends on Step 1 completing | Low | Group B runs after Group A; main.tsx import of the store requires store file to exist first |

## Success Criteria

- [ ] `src/stores/ui.ts` exists and exports `useUIStore` with `sidebarCollapsed`, `theme`, `selectedStepId`, `stepDetailOpen` state and `toggleSidebar`, `setTheme`, `selectStep`, `closeStepDetail` actions
- [ ] `src/stores/filters.ts` exists and exports `useFiltersStore` with `pipelineName`, `startedAfter`, `startedBefore` state and `setPipelineName`, `setDateRange`, `resetFilters` actions
- [ ] `selectedStepId` typed as `number | null` (not `string | null`)
- [ ] `pipelineName`, `startedAfter`, `startedBefore` default to `null` (not `''`)
- [ ] `status` and pagination fields absent from filters store
- [ ] ui store persist key is `'llm-pipeline-ui'`
- [ ] Only `sidebarCollapsed` and `theme` are persisted (partialize excludes ephemeral fields)
- [ ] `onRehydrateStorage` applies `.dark` class from persisted theme on page load
- [ ] `setTheme` toggles `document.documentElement.classList` as a side-effect
- [ ] Hardcoded `document.documentElement.classList.add('dark')` removed from `main.tsx`
- [ ] Both stores use `devtools` middleware with `enabled: import.meta.env.DEV`
- [ ] `tsc -b --noEmit` passes with no type errors
- [ ] Code style matches existing: no semicolons, single quotes, 2-space indent

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Pure new-file additions (2 files) plus one line removal in main.tsx. No API changes, no schema changes, no existing logic modified except removing one hardcoded DOM call. All architectural decisions resolved via CEO Q&A. Downstream tasks 33 and 41 are pending and cannot regress.
**Suggested Exclusions:** testing, review
