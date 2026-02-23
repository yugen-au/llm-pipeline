# Research: Zustand UI State Patterns for LLM Pipeline Dashboard

## 1. Existing Codebase State

### Frontend Structure
- **Location**: `llm_pipeline/ui/frontend/src/`
- **Stack**: React 19.2, Vite 7.3, TypeScript 5.9, TanStack Router 1.161, TanStack Query 5.90, Zustand 5.0.11
- **Design system**: shadcn/ui with OKLCH tokens, Tailwind v4 CSS-first config
- **Theme**: `.dark` class on `<html>`, hardcoded in `main.tsx` via `document.documentElement.classList.add('dark')`
- **Code style**: No semicolons, single quotes, named functions, 2-space indent, 100 char width

### Existing Store: `src/stores/websocket.ts`
```typescript
import { create } from 'zustand'

export const useWsStore = create<WsState>()((set) => ({
  status: 'idle',
  error: null,
  reconnectCount: 0,
  setStatus: (status) => set({ status }),
  // ...actions co-located in store
}))
```

**Pattern observations**:
- Zustand v5 `create<T>()()` double-call (required for TS in v5)
- No middleware (persist, devtools) used
- Actions co-located with state
- Export naming: `useXxxStore`
- Ephemeral state only (connection status resets on reload)

### Server State Separation
TanStack Query handles all API/server state:
- `src/api/runs.ts` - useRuns, useRun, useCreateRun, useRunContext
- `src/api/steps.ts` - useSteps, useStep
- `src/api/events.ts` - useEvents
- `src/api/prompts.ts` - usePrompts
- `src/api/pipelines.ts` - usePipelines, usePipeline
- `src/api/query-keys.ts` - centralized query key factory

Zustand stores are strictly UI-only state. No server state duplication.

### URL Search Params
TanStack Router already owns some UI state via Zod-validated search params:
- `index.tsx`: `page` (number), `status` (string) for run list
- `runs/$runId.tsx`: `tab` (string, default 'steps') for run detail

### Design Token System
`index.css` defines OKLCH color tokens for both `:root` (light) and `.dark` (dark):
- Background/foreground, card, popover, primary, secondary, muted, accent, destructive
- Sidebar-specific: `--sidebar`, `--sidebar-foreground`, `--sidebar-primary`, etc.
- Tailwind v4 `@theme inline` maps vars to utility classes (`bg-sidebar`, `text-muted-foreground`)
- Theme switching = toggling `.dark` class on `document.documentElement`

---

## 2. Proposed Store Architecture

### 2.1 `src/stores/ui.ts` (useUIStore)

**State**:
| Field | Type | Default | Persisted | Purpose |
|---|---|---|---|---|
| `sidebarCollapsed` | `boolean` | `false` | Yes | Sidebar width toggle |
| `theme` | `'dark' \| 'light'` | `'dark'` | Yes | Color scheme preference |
| `selectedStepId` | `string \| null` | `null` | No | Currently selected step in run detail |
| `stepDetailOpen` | `boolean` | `false` | No | Step detail panel visibility |

**Actions**:
| Action | Signature | Notes |
|---|---|---|
| `toggleSidebar` | `() => void` | Flips `sidebarCollapsed` |
| `setTheme` | `(theme: 'dark' \| 'light') => void` | Sets theme + syncs `.dark` class |
| `selectStep` | `(stepId: string \| null) => void` | Sets selectedStepId + opens/closes panel |

**Middleware stack**: `devtools(persist(store, options))`

**Persistence config**:
```typescript
persist(
  (set) => ({ ... }),
  {
    name: 'llm-pipeline-ui',
    partialize: (state) => ({
      sidebarCollapsed: state.sidebarCollapsed,
      theme: state.theme,
    }),
    onRehydrateStorage: () => (state) => {
      // Sync theme class on hydration
      if (state?.theme === 'dark') {
        document.documentElement.classList.add('dark')
      } else {
        document.documentElement.classList.remove('dark')
      }
    },
  }
)
```

**Key design decisions**:
- `partialize` excludes `selectedStepId` and `stepDetailOpen` from persistence -- ephemeral per-session state that would be stale across reloads
- `onRehydrateStorage` syncs `.dark` class immediately on store hydration, replacing the hardcoded `classList.add('dark')` in main.tsx
- `setTheme` action must also toggle `.dark` class as a side-effect (not just set state)

### 2.2 `src/stores/filters.ts` (useFiltersStore)

**State**:
| Field | Type | Default | Purpose |
|---|---|---|---|
| `pipelineName` | `string` | `''` | Filter runs by pipeline name |
| `status` | `string` | `''` | Filter runs by status |
| `startedAfter` | `string` | `''` | ISO date string lower bound |
| `startedBefore` | `string` | `''` | ISO date string upper bound |

**Actions**:
| Action | Signature | Notes |
|---|---|---|
| `setFilter` | `(patch: Partial<FilterState>) => void` | Partial update, merges with current |
| `resetFilters` | `() => void` | Resets all to defaults |

**Middleware**: `devtools` only (no persist)

**Why no persistence**: Filter state is session-specific. Users expect fresh filter state on reload. Additionally, the route's search params (`page`, `status`) already capture shareable/bookmarkable filter state -- the Zustand store holds transient working state that feeds into TanStack Query hooks.

**Integration with TanStack Query**:
```typescript
// In RunList component (task 33):
const filters = useFiltersStore((s) => ({
  pipelineName: s.pipelineName,
  status: s.status,
  startedAfter: s.startedAfter,
  startedBefore: s.startedBefore,
}))
const { data } = useRuns({
  pipeline_name: filters.pipelineName || undefined,
  status: filters.status || undefined,
  started_after: filters.startedAfter || undefined,
  started_before: filters.startedBefore || undefined,
})
```

---

## 3. Zustand v5 Best Practices Applied

### 3.1 TypeScript Pattern
Zustand v5 requires double-call for proper type inference:
```typescript
// Correct (v5):
export const useUIStore = create<UIState>()(devtools(persist((set) => ({ ... }), options)))

// Wrong (v4 style):
export const useUIStore = create<UIState>(devtools(persist((set) => ({ ... }), options)))
```

### 3.2 Selector Pattern
Always use selectors to avoid unnecessary re-renders:
```typescript
// Good - only re-renders when theme changes:
const theme = useUIStore((s) => s.theme)

// Bad - re-renders on any store change:
const store = useUIStore()
```

For multi-value selectors, use `useShallow`:
```typescript
import { useShallow } from 'zustand/react/shallow'

const { sidebarCollapsed, theme } = useUIStore(
  useShallow((s) => ({ sidebarCollapsed: s.sidebarCollapsed, theme: s.theme }))
)
```

### 3.3 Middleware Composition Order
Outer middleware wraps inner. For devtools + persist:
```typescript
create<T>()(
  devtools(           // outermost - sees all state changes
    persist(          // inner - handles localStorage
      (set) => ({}),  // store definition
      { name: '...' }
    ),
    { name: 'UIStore' }  // devtools label
  )
)
```

### 3.4 Actions Co-located with State
Consistent with existing `websocket.ts` pattern. Actions are defined inside `create()` alongside state, not in separate files.

### 3.5 Devtools Middleware
Add `devtools` wrapper with descriptive `name` for Redux DevTools visibility:
```typescript
devtools(storeImpl, { name: 'UIStore', enabled: import.meta.env.DEV })
```

`enabled: import.meta.env.DEV` prevents devtools overhead in production.

---

## 4. Downstream Consumer Requirements

### Task 33 - Run List View (depends on task 32)
```typescript
import { useFiltersStore } from '../stores/filters'
// Needs: pipelineName, status, startedAfter, startedBefore
// Needs: setFilter, resetFilters
```

### Task 41 - Sidebar Navigation (depends on task 32)
```typescript
import { useUIStore } from '../stores/ui'
// Needs: sidebarCollapsed, toggleSidebar
// Theme toggle likely in sidebar footer
```

### Root Layout (`__root.tsx`)
- Currently: static `<aside className="w-60 ...">` placeholder
- Will consume: `sidebarCollapsed` for dynamic width class (`w-60` vs `w-12`)
- Task 41 replaces placeholder `<aside>` with `<Sidebar />` component

---

## 5. Theme Implementation Details

### Current State
`main.tsx` line 17: `document.documentElement.classList.add('dark')` -- hardcoded dark mode

### Proposed Change
1. Remove hardcoded line from `main.tsx`
2. UI store `onRehydrateStorage` sets class based on persisted preference
3. `setTheme` action toggles class:
```typescript
setTheme: (theme) => {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
  set({ theme })
}
```
4. Default theme: `'dark'` (matches current behavior, OKLCH dark tokens are the primary palette)

### Flash-of-wrong-theme Prevention
Zustand persist uses localStorage synchronously via `getItem` before React renders. The `onRehydrateStorage` callback fires after store hydration, which happens during module load (before first render). No FOUC expected.

---

## 6. Scope Boundaries

### IN SCOPE (task 32)
- `src/stores/ui.ts` with persist + devtools middleware
- `src/stores/filters.ts` with devtools middleware
- Proper TypeScript interfaces for both stores
- Selector patterns documented for downstream consumers

### OUT OF SCOPE
- Server state (TanStack Query -- tasks 31, 33+)
- WebSocket state (already done in `src/stores/websocket.ts`)
- Actual Sidebar component (task 41)
- Actual RunList component (task 33)
- URL search param sync logic (task 33 route-level concern)
- shadcn/ui component installation (separate concern)

---

## 7. File Structure After Task 32

```
src/stores/
  websocket.ts   # existing - WS connection state (no changes)
  ui.ts          # NEW - sidebar, theme, step selection
  filters.ts     # NEW - run list filters
```

---

## 8. Deviation from Task Description

### Task description uses `create<UIState>()(persist(...))`
The task description omits `devtools` middleware. Recommendation: add `devtools` wrapper to both stores for better DX. This is additive and non-breaking.

### Task description setTheme does not sync DOM class
The `setTheme` action in the task description only calls `set({ theme })`. Implementation must also toggle `.dark` class on `document.documentElement` for the OKLCH design token system to respond.
