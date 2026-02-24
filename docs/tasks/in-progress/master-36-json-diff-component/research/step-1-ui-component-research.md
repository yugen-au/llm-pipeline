# Research: UI Component Architecture for JSON Diff (Task 36)

## Frontend Stack

| Layer | Technology | Version |
|---|---|---|
| Build | Vite | 7.3.1 |
| Framework | React | 19.2.0 |
| Language | TypeScript | 5.9.3 |
| Router | TanStack Router | 1.161.3 |
| Data fetching | TanStack Query | 5.90.21 |
| State management | Zustand | 5.0.11 |
| UI components | shadcn/ui (new-york, neutral) | 3.8.5 |
| Styling | Tailwind CSS v4 | 4.2.0 |
| Icons | lucide-react | 0.575.0 |
| Testing | Vitest + React Testing Library | 3.2.1 |
| Path alias | `@/*` -> `./src/*` | tsconfig.json |

**NOT Next.js.** Pure Vite + React SPA.

## Directory Structure

```
llm_pipeline/ui/frontend/src/
  api/
    client.ts          # fetch wrapper (apiClient<T>)
    types.ts           # all TS interfaces (mirrors backend Pydantic)
    runs.ts            # useRuns, useRun, useCreateRun, useRunContext hooks
    steps.ts           # useStep, useSteps hooks
    events.ts          # useEvents, useStepEvents hooks
    pipelines.ts       # usePipelines, useStepInstructions hooks
    query-keys.ts      # centralized query key factory
    websocket.ts       # useWebSocket hook
    useRunNotifications.ts
  components/
    runs/
      ContextEvolution.tsx      ** TARGET: replace internals
      ContextEvolution.test.tsx ** TARGET: update tests
      StepTimeline.tsx
      StepTimeline.test.tsx
      StepDetailPanel.tsx       ** INTEGRATION: ContextDiffTab uses snapshots
      StepDetailPanel.test.tsx
      StatusBadge.tsx
      StatusBadge.test.tsx
      RunsTable.tsx
      RunsTable.test.tsx
      FilterBar.tsx
      FilterBar.test.tsx
      Pagination.tsx
      Pagination.test.tsx
    live/
      EventStream.tsx
      PipelineSelector.tsx
    ui/                         # shadcn primitives
      badge.tsx
      button.tsx
      card.tsx
      scroll-area.tsx
      select.tsx
      separator.tsx
      sheet.tsx
      table.tsx
      tabs.tsx
      tooltip.tsx
  lib/
    utils.ts           # cn() - clsx + tailwind-merge
    time.ts            # formatDuration, formatRelative, formatAbsolute
  stores/
    ui.ts              # useUIStore (sidebar, theme, selectedStepId, stepDetailOpen)
    filters.ts
    websocket.ts
  routes/
    __root.tsx         # RootLayout with sidebar + main outlet
    index.tsx          # Runs list page
    pipelines.tsx
    prompts.tsx
    live.tsx           # Live execution view (task 37)
    runs/$runId.tsx    # Run detail page -- USES ContextEvolution
  main.tsx
  index.css            # Tailwind + shadcn theme variables
```

## Component Patterns

All existing components follow these conventions:

### Export style
Named function exports, never default. Example: `export function ContextEvolution(...)`.

### Props interfaces
Defined inline above the component:
```typescript
interface ContextEvolutionProps {
  snapshots: ContextSnapshot[]
  isLoading: boolean
  isError: boolean
}
```

### State pattern: loading / error / empty / content
Every data-driven component handles all 4 states:
- **Loading**: custom skeleton with `animate-pulse` divs and `bg-muted` backgrounds
- **Error**: `<p className="text-destructive">...</p>`
- **Empty**: `<p className="text-muted-foreground">...</p>`
- **Content**: actual render

### Class naming
Tailwind classes via `className`, composed with `cn()` from `@/lib/utils` when conditional.

### shadcn usage
Import from `@/components/ui/*`. Used primitives: Badge, Button, Card, ScrollArea, Select, Separator, Sheet, Table, Tabs, Tooltip.

## Existing ContextEvolution Component

**File**: `src/components/runs/ContextEvolution.tsx`

Current implementation renders raw `JSON.stringify(snapshot.context_snapshot, null, 2)` in `<pre>` tags inside a ScrollArea. No diffing. Task 34 summary explicitly states:

> "Task 36 should replace this with a collapsible JsonDiff view. The `ContextEvolutionProps` interface (`snapshots`, `isLoading`, `isError`) and ScrollArea structure can be preserved as the scaffold."

### Current props interface (to preserve):
```typescript
interface ContextEvolutionProps {
  snapshots: ContextSnapshot[]
  isLoading: boolean
  isError: boolean
}
```

### Current layout in RunDetailPage ($runId.tsx):
```tsx
{/* Context evolution - right column */}
<div className="w-80 shrink-0 overflow-hidden rounded-xl border">
  <div className="border-b px-4 py-3">
    <h2 className="text-sm font-semibold">Context Evolution</h2>
  </div>
  <ContextEvolution
    snapshots={context?.snapshots ?? []}
    isLoading={contextLoading}
    isError={contextError}
  />
</div>
```

Panel is **w-80** (320px) wide, with a fixed header and ContextEvolution filling the remaining height.

## StepDetailPanel ContextDiffTab (Second Integration Point)

**File**: `src/components/runs/StepDetailPanel.tsx`, lines 228-290

The `ContextDiffTab` already shows before/after context as side-by-side raw JSON. It gets before/after snapshots and shows "New Keys" badges. This is a natural integration point for JsonDiff:

```typescript
function ContextDiffTab({ step, events, snapshots, snapshotsLoading }) {
  // Gets beforeSnapshot (step N-1) and afterSnapshot (step N)
  // Currently renders side-by-side <pre> blocks
  // Integration: replace grid with <JsonDiff before={...} after={...} />
}
```

## Data Types

### ContextSnapshot (from `src/api/types.ts`)
```typescript
interface ContextSnapshot {
  step_name: string
  step_number: number
  context_snapshot: Record<string, unknown>
}
```

### ContextEvolutionResponse
```typescript
interface ContextEvolutionResponse {
  run_id: string
  snapshots: ContextSnapshot[]
}
```

### ContextUpdatedData (event data)
```typescript
interface ContextUpdatedData {
  new_keys: string[]
  context_snapshot: Record<string, unknown>
}
```

## Theming / Color System

### CSS Variables (oklch-based, in `src/index.css`)
- Uses shadcn neutral theme with both light and dark mode
- Dark mode via `.dark` class on `<html>` (toggled by `useUIStore.setTheme`)
- Default theme is `dark`
- Key semantic colors used in components:
  - `bg-muted` / `text-muted-foreground` -- neutral backgrounds/text
  - `text-destructive` -- error/failure states
  - `border` / `border-border` -- standard borders

### Existing status colors (not from CSS variables, direct Tailwind):
```
green:  border-green-500 text-green-600 dark:text-green-400  (completed)
amber:  border-amber-500 text-amber-600 dark:text-amber-400  (running)
red:    destructive variant (failed)
blue:   border-blue-500 text-blue-600 dark:text-blue-400 (step_started events)
purple: border-purple-500 text-purple-600 dark:text-purple-400 (llm_call events)
teal:   border-teal-500 text-teal-600 dark:text-teal-400 (context events)
```

### Proposed diff colors (following existing pattern):
- **Additions (green)**: `bg-green-500/10 text-green-600 dark:text-green-400` or `bg-green-950/30` for dark mode background
- **Removals (red)**: `bg-red-500/10 text-red-600 dark:text-red-400 line-through`
- **Changes (yellow)**: `bg-yellow-500/10 text-yellow-600 dark:text-yellow-400`

These follow the existing pattern of using Tailwind color utilities with `dark:` variants instead of CSS custom properties for status-specific colors.

## Collapsible/Accordion Components

**None installed.** No collapsible, accordion, or disclosure component exists in `src/components/ui/`.

Options for collapsible JSON nodes:
1. **Install shadcn collapsible**: `npx shadcn@latest add collapsible` -- wraps Radix `@radix-ui/react-collapsible`
2. **Custom disclosure**: Simple `useState` toggle with a chevron icon (lucide `ChevronRight`/`ChevronDown`)
3. **Native `<details>/<summary>`**: Browser-native, no JS needed, but limited styling

Recommendation: Option 2 (custom) is simpler and sufficient for JSON tree nodes. The collapsible pattern only needs open/close state per node, which a simple `useState` handles without bringing in a Radix primitive.

## Diff Libraries (None Installed)

**No diff library in package.json.** Task spec suggests `deep-diff` or `jsondiffpatch`.

| Library | npm weekly | Size (minified) | Output format |
|---|---|---|---|
| `deep-diff` | ~800k | 5 KB | Array of Diff objects (kind: N/D/E/A) |
| `jsondiffpatch` | ~400k | 45 KB | Delta object (nested) |
| Custom implementation | n/a | 0 KB | Custom |

**Recommendation**: `deep-diff` -- smaller, simpler API, returns flat diff array with typed `kind` field (N=new, D=deleted, E=edited, A=array change), widely used, has TypeScript types (`@types/deep-diff`). jsondiffpatch is heavier and its delta format is harder to render into a tree view.

Alternatively, a custom recursive diff for `Record<string, unknown>` is feasible in ~50 lines since the context snapshots are relatively shallow JSON objects (typically 5-20 top-level keys, 1-3 levels deep). This avoids adding a dependency.

## Existing Tests

### ContextEvolution.test.tsx (5 tests)
```
- renders step names as headers
- renders JSON snapshots as formatted text
- shows loading skeleton with animate-pulse elements
- shows error text when isError
- shows empty state message
```

These tests will need updating when ContextEvolution is modified. Current tests assert on raw JSON text (`/"input": "raw data"/`), which will change when switching to diff view.

### Testing patterns used
- `render()` from `@testing-library/react`
- `screen.getByText()`, `screen.getAllByRole()`, `screen.getByRole()`
- `container.querySelectorAll()` for CSS class assertions
- `describe/it/expect` from Vitest
- No router/query provider wrappers in simple component tests (only in route/hook tests)

## Task 37 (Live Execution View) -- Completed

The live page (`src/routes/live.tsx`) uses StepTimeline but does NOT use ContextEvolution. It has its own EventStream panel instead. No changes needed to live.tsx for task 36.

## Summary of Integration Points

1. **ContextEvolution.tsx** (replace): Currently renders raw JSON per step. Replace with JsonDiff between consecutive steps (`snapshots[i-1]` vs `snapshots[i]`). First step shows full snapshot as "all additions". Keep existing props interface.

2. **StepDetailPanel.tsx ContextDiffTab** (enhance): Currently shows side-by-side `<pre>` blocks. Can replace with `<JsonDiff before={beforeSnapshot} after={afterSnapshot} />`. Also shows `new_keys` badges from events.

3. **New file: JsonDiff.tsx** (create): Reusable component at `src/components/runs/JsonDiff.tsx` or `src/components/JsonDiff.tsx` (if intended for broader reuse).

## Open Decisions for Implementation

1. **Diff library vs custom**: deep-diff (add dep) vs custom recursive diff (~50 lines)
2. **JsonDiff file location**: `src/components/runs/JsonDiff.tsx` (scoped to runs) vs `src/components/JsonDiff.tsx` (reusable across features)
3. **Collapsible approach**: shadcn collapsible vs custom useState toggle
4. **Max depth default**: Task spec says `maxDepth = 3`; verify if pipeline context snapshots exceed 3 levels
5. **First step display**: Show full snapshot as "all additions" (green) or as plain JSON (current behavior)
