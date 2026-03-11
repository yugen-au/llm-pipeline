# Step 1: Frontend Component Analysis

## Project Overview

- **Location**: `llm_pipeline/ui/frontend/`
- **Stack**: React 19, TypeScript 5.9, Vite 7, TanStack Query v5, TanStack Router, Zustand v5, TailwindCSS v4, Radix UI (shadcn)
- **Test Stack**: Vitest 3.2 + jsdom 26 + @testing-library/react 16 + @testing-library/user-event 14 + @testing-library/jest-dom 6

## Test Infrastructure

### Vitest Config (`vitest.config.ts`)
- `globals: true` (vi, describe, it, expect available globally)
- `environment: 'jsdom'`
- `setupFiles: ['./src/test/setup.ts']`
- `include: ['src/**/*.{test,spec}.{ts,tsx}']`
- Path alias: `@` -> `./src`

### Setup File (`src/test/setup.ts`)
- Imports `@testing-library/jest-dom/vitest` for custom matchers
- Polyfills: `hasPointerCapture`, `setPointerCapture`, `releasePointerCapture`, `scrollIntoView` (required by Radix UI in jsdom)

---

## Component Inventory

### Already Tested (9 files)

| File | Component/Function | Test File |
|------|-------------------|-----------|
| `src/test/smoke.test.ts` | Infrastructure | Same |
| `src/lib/time.ts` | formatRelative, formatAbsolute, formatDuration | `src/lib/time.test.ts` |
| `src/components/runs/FilterBar.tsx` | FilterBar | `FilterBar.test.tsx` |
| `src/components/runs/Pagination.tsx` | Pagination | `Pagination.test.tsx` |
| `src/components/runs/StatusBadge.tsx` | StatusBadge | `StatusBadge.test.tsx` |
| `src/components/runs/RunsTable.tsx` | RunsTable | `RunsTable.test.tsx` |
| `src/components/runs/StepTimeline.tsx` | StepTimeline + deriveStepStatus | `StepTimeline.test.tsx` |
| `src/components/runs/StepDetailPanel.tsx` | StepDetailPanel | `StepDetailPanel.test.tsx` |
| `src/components/runs/ContextEvolution.tsx` | ContextEvolution | `ContextEvolution.test.tsx` |

### Not Yet Tested (14 components + 2 pure functions)

#### Tier 1: Pure/Presentational Components

**1. JsonDiff** (`src/components/JsonDiff.tsx`)
- Props: `{ before: Record<string,unknown>, after: Record<string,unknown>, maxDepth?: number }`
- Deps: `microdiff` library, `memo`, `useMemo`, `useState`, `useCallback`
- Internals: `buildDiffTree()`, `DiffNode` (recursive, memo-wrapped), `countDiffs()`, `formatValue()`
- Renders: green CREATE (+), red REMOVE (-), yellow CHANGE diffs; collapsible branch nodes
- Empty state: "No changes" when diffs.length === 0
- Used by: ContextEvolution, StepDetailPanel (ContextDiffTab)

**2. FormField** (`src/components/live/FormField.tsx`)
- Props: `{ name, fieldSchema: JsonSchema, value, onChange, error?, required }`
- Renders different inputs based on `fieldSchema.type`:
  - `string` -> `<Input>`
  - `integer`/`number` -> `<Input type="number">`
  - `boolean` -> `<Checkbox>` with inline label
  - fallback -> `<Textarea>` with JSON parsing
- Shows: label, required indicator (*), description, error message
- Sets `aria-invalid` on error

**3. InputForm** (`src/components/live/InputForm.tsx`)
- Props: `{ schema: JsonSchema | null, values, onChange, fieldErrors, isSubmitting }`
- Returns `null` when schema is null
- Renders `<FormField>` for each property in `schema.properties`
- Wraps in `<fieldset disabled={isSubmitting}>`
- Has `data-testid="input-form"`
- **Exported pure function**: `validateForm(schema, values)` -> `Record<string, string>`

**4. EventStream** (`src/components/live/EventStream.tsx`)
- Props: `{ events: EventItem[], wsStatus: WsConnectionStatus, runId: string | null }`
- States: runId=null ("Waiting for run..."), events=[] ("No events yet"), events populated
- Shows `ConnectionIndicator` with colored dot + label per status
- Event rows: timestamp, type badge (color-coded), step name
- Auto-scroll via sentinel ref (internal useEffect)

**5. PromptFilterBar** (`src/components/prompts/PromptFilterBar.tsx`)
- Props: `{ promptTypes[], pipelineNames[], selectedType, selectedPipeline, onTypeChange, onPipelineChange, searchText, onSearchChange }`
- Contains: text Input (search), Select (type filter), Select (pipeline filter)
- Uses `ALL_SENTINEL = '__all'` pattern (same as FilterBar)

**6. PromptList** (`src/components/prompts/PromptList.tsx`)
- Props: `{ prompts: Prompt[], selectedKey, onSelect, isLoading, error }`
- States: loading (skeleton), error, empty ("No prompts match filters"), data
- Renders: button per prompt with name + type badge, highlight on selection

**7. PipelineList** (`src/components/pipelines/PipelineList.tsx`)
- Props: `{ pipelines: PipelineListItem[], selectedName, onSelect, isLoading, error }`
- States: loading (skeleton), error, empty, data
- Renders: button per pipeline with name + step count badge + strategy count badge
- Shows destructive badge when `pipeline.error != null`

**8. StrategySection** (`src/components/pipelines/StrategySection.tsx`)
- Props: `{ strategy: PipelineStrategyMetadata, pipelineName: string }`
- Renders: strategy header (display_name, class_name, error badge)
- Error state: shows error text
- Normal: ordered list of `StepRow` components (expand/collapse accordion)
- StepRow shows: step_name, class_name; expanded: prompt keys (links to /prompts), schemas (JsonTree), extractions, transformation, action_after

**9. JsonTree** (`src/components/pipelines/JsonTree.tsx`)
- Props: `{ data: Record<string,unknown> | unknown[] | null, depth?: number }`
- Recursive: `JsonTreeNode` with expand/collapse for objects/arrays
- PrimitiveValue: color-coded by type (green strings, blue numbers, orange booleans, italic null)
- Auto-expand depth < 2

#### Tier 2: Components with Data Fetching Hooks

**10. PipelineSelector** (`src/components/live/PipelineSelector.tsx`)
- Props: `{ selectedPipeline: string | null, onSelect, disabled? }`
- Uses: `usePipelines()` hook internally
- States: loading (skeleton), error, empty ("No pipelines registered"), data (Select dropdown)

**11. PromptViewer** (`src/components/prompts/PromptViewer.tsx`)
- Props: `{ promptKey: string | null }`
- Uses: `usePromptDetail(promptKey)` hook internally
- States: no key selected, loading, error, no data, single variant (no tabs), multiple variants (Tabs)
- `highlightVariables()` function: splits content on `{variable}` patterns, wraps in highlighted spans

**12. PipelineDetail** (`src/components/pipelines/PipelineDetail.tsx`)
- Props: `{ pipelineName: string | null }`
- Uses: `usePipeline(pipelineName)` hook internally
- States: no pipeline selected, loading (skeleton), error, data
- Renders: pipeline_name, registry_models badges, execution_order, pipeline_input_schema (JsonTree), strategies (StrategySection[])

#### Tier 3: Route Pages (integration-heavy, lower priority)

| Route | Key Hooks | Complexity |
|-------|-----------|-----------|
| `routes/index.tsx` RunListPage | useRuns, useFiltersStore, Route.useSearch, useNavigate | Medium |
| `routes/runs/$runId.tsx` RunDetailPage | useRun, useSteps, useEvents, useRunContext, useWebSocket, useUIStore | High |
| `routes/live.tsx` LivePage | useCreateRun, usePipeline, useSteps, useEvents, useWebSocket, useRunNotifications, useUIStore, useWsStore | Very High |
| `routes/prompts.tsx` PromptsPage | usePrompts, usePipelines, useQueries, useNavigate | High |
| `routes/pipelines.tsx` PipelinesPage | usePipelines, useNavigate | Medium |

#### Pure Functions/Classes (no UI)

**13. toSearchParams** (`src/api/types.ts`)
- Input: `Record<string, string | number | boolean | undefined | null>`
- Returns: empty string or `?key=value&...`
- Omits null/undefined values

**14. ApiError** (`src/api/types.ts`)
- Constructor: `(status: number, detail: string)`
- Properties: `name='ApiError'`, `status`, `detail`
- Extends Error

---

## State Management

### Zustand Stores

**useWsStore** (`stores/websocket.ts`)
- State: `status: WsConnectionStatus`, `error: string | null`, `reconnectCount: number`
- Actions: `setStatus`, `setError`, `incrementReconnect`, `reset`
- No middleware (plain create)

**useFiltersStore** (`stores/filters.ts`)
- State: `pipelineName`, `startedAfter`, `startedBefore`
- Actions: `setPipelineName`, `setDateRange`, `resetFilters`
- Middleware: devtools (DEV only)

**useUIStore** (`stores/ui.ts`)
- State: `sidebarCollapsed`, `theme`, `selectedStepId`, `stepDetailOpen`
- Actions: `toggleSidebar`, `setTheme`, `selectStep`, `closeStepDetail`
- Middleware: devtools + persist (localStorage, partializes sidebar + theme only)

---

## Data Fetching Patterns

### TanStack Query Hooks

| Hook | File | Endpoint | Dynamic staleTime | Polling |
|------|------|----------|-------------------|---------|
| useRuns | runs.ts | GET /api/runs | No (30s default) | No |
| useRun | runs.ts | GET /api/runs/{id} | Infinity for terminal, 5s for active | 3s for active |
| useCreateRun | runs.ts | POST /api/runs | N/A (mutation) | N/A |
| useRunContext | runs.ts | GET /api/runs/{id}/context | Infinity for terminal | No |
| useSteps | steps.ts | GET /api/runs/{id}/steps | Infinity for terminal, 5s | 3s for active |
| useStep | steps.ts | GET /api/runs/{id}/steps/{n} | Infinity for terminal, 30s | No |
| useEvents | events.ts | GET /api/runs/{id}/events | Infinity for terminal, 5s | 3s for active |
| useStepEvents | events.ts | (wraps useEvents) | Same | Same |
| usePipelines | pipelines.ts | GET /api/pipelines | No (30s default) | No |
| usePipeline | pipelines.ts | GET /api/pipelines/{name} | No (30s default) | No |
| useStepInstructions | pipelines.ts | GET /api/pipelines/{name}/steps/{step}/prompts | Infinity | No |
| usePrompts | prompts.ts | GET /api/prompts | No (30s default) | No |
| usePromptDetail | prompts.ts | GET /api/prompts/{key} | No (30s default) | No |

### Query Key Factory (`src/api/query-keys.ts`)
- `queryKeys.runs.all`, `.list(filters)`, `.detail(runId)`, `.context(runId)`, `.steps(runId)`, `.step(runId, n)`, `.events(runId, filters)`
- `queryKeys.prompts.all`, `.list(filters)`, `.detail(key)`
- `queryKeys.pipelines.all`, `.detail(name)`, `.stepPrompts(name, stepName)`
- `isTerminalStatus(status)` -> boolean (completed|failed)

### WebSocket Hooks
- `useWebSocket(runId)` - Per-run WS with TanStack Query cache integration + Zustand store
- `useRunNotifications()` - Global /ws/runs for run_created events, useState only

---

## Existing Test Patterns (for consistency)

### Mocking Strategy
```typescript
// Hook mocking
const mockUseStep = vi.fn()
vi.mock('@/api/steps', () => ({
  useStep: (...args: unknown[]) => mockUseStep(...args),
}))

// Router mocking
const mockNavigate = vi.fn()
vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => mockNavigate,
}))

// Time utils mocking (avoid flaky tests)
vi.mock('@/lib/time', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/time')>()
  return { ...actual, formatRelative: (iso: string) => `relative(${iso})` }
})
```

### Fake Timer Pattern
```typescript
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(new Date(NOW)) })
afterEach(() => { vi.useRealTimers() })
// IMPORTANT: vi.useRealTimers() before userEvent.setup() for Radix interactions
```

### Radix Portal Queries
```typescript
// Sheet content via data-slot (renders in portal, not in component tree)
document.querySelector('[data-slot="sheet-content"]')
document.querySelector('[data-slot="sheet-overlay"]')
```

### Assertions
- `screen.getByRole('combobox', { name: /pattern/ })` for Select triggers
- `screen.getByRole('option', { name: 'Label' })` for Select items
- `container.querySelectorAll('.animate-pulse')` for skeleton counts
- `element.dataset.variant` for Radix Badge variant checks

---

## Recommended Test Priority

### HIGH (core functionality, pure presentational)
1. **JsonDiff** - Core diff visualization; complex but fully deterministic
2. **FormField + InputForm + validateForm** - Form generation from JSON Schema
3. **EventStream** - Live event display (3 states: no run, no events, events)

### MEDIUM (data-fetching components, need hook mocking)
4. **PipelineSelector** - Loading/error/empty/data states
5. **PromptFilterBar** - Search + multi-select filters
6. **PromptList** - List with selection
7. **PipelineList** - List with badges and selection
8. **PromptViewer** - Detail view with variant tabs
9. **PipelineDetail** - Full metadata view

### LOWER (recursive/complex UI, lower ROI)
10. **JsonTree** - Recursive JSON viewer
11. **StrategySection** - Accordion with nested content
12. **Sidebar** - Navigation (needs router + media query mocks)

### PURE FUNCTIONS
13. **toSearchParams** - Unit test
14. **ApiError** - Unit test
