# Step 2: Existing Codebase Patterns Research

## Backend Data Models

### PipelineRun (llm_pipeline/state.py)
SQLModel table `pipeline_runs`. Fields:
- `id`: int PK
- `run_id`: str(36), unique, UUID format
- `pipeline_name`: str(100)
- `status`: str(20), default="running" — values: `running`, `completed`, `failed`
- `started_at`: datetime (utc_now factory)
- `completed_at`: Optional[datetime]
- `step_count`: Optional[int]
- `total_time_ms`: Optional[int]

IMPORTANT: No `pending` status exists in backend. Default is `running`. Task description's mention of `pending` is a spec error.

### PipelineStepState (llm_pipeline/state.py)
SQLModel table `pipeline_step_states`. Key fields relevant to UI:
- `run_id`: str(36)
- `step_name`: str(100)
- `step_number`: int
- `execution_time_ms`: Optional[int]
- `created_at`: datetime

### PipelineRunInstance (llm_pipeline/state.py)
NOT the run tracking model. Tracks which DB instances (model_type/model_id) a run created. Not used by the run list view.

---

## API Endpoints (llm_pipeline/ui/routes/runs.py)

### GET /api/runs
Response `RunListResponse`:
```
items: RunListItem[]
total: int
offset: int
limit: int
```

Each `RunListItem`:
```
run_id: str
pipeline_name: str
status: str
started_at: datetime (ISO 8601 with TZ)
completed_at: datetime | null
step_count: int | null
total_time_ms: int | null
```

Query params (`RunListParams`):
- `pipeline_name`: str (optional)
- `status`: str (optional)
- `started_after`: datetime (optional)
- `started_before`: datetime (optional)
- `offset`: int (default 0, ge=0)
- `limit`: int (default 50, ge=1, le=200)

Ordered by `started_at DESC`.

### GET /api/runs/{run_id}
Response `RunDetail` (superset of RunListItem):
```
run_id, pipeline_name, status, started_at, completed_at, step_count, total_time_ms
steps: StepSummary[]  -- ordered by step_number ASC
```

Each `StepSummary`: `step_name`, `step_number`, `execution_time_ms`, `created_at`

Returns 404 if run_id not found.

### POST /api/runs
Request: `{ pipeline_name: str }`
Response 202: `{ run_id: str, status: "accepted" }`
Returns 404 if pipeline not in registry.

### GET /api/runs/{run_id}/context
Response: `{ run_id: str, snapshots: ContextSnapshot[] }`
Each snapshot: `step_name`, `step_number`, `context_snapshot` (dict)

---

## TypeScript Types (src/api/types.ts)

All types fully implemented and match backend exactly.

```typescript
type RunStatus = 'running' | 'completed' | 'failed'  // NO 'pending'

interface RunListItem {
  run_id: string
  pipeline_name: string
  status: string
  started_at: string       // ISO 8601
  completed_at: string | null
  step_count: number | null
  total_time_ms: number | null
}

interface RunListResponse {
  items: RunListItem[]
  total: number
  offset: number
  limit: number
}

interface RunListParams {
  pipeline_name?: string
  status?: string
  started_after?: string
  started_before?: string
  offset?: number
  limit?: number
}
```

Also defined: `StepSummary`, `RunDetail`, `TriggerRunRequest`, `TriggerRunResponse`,
`ContextEvolutionResponse`, `ContextSnapshot`, `toSearchParams()`, `ApiError`.

---

## API Hooks (src/api/runs.ts)

Four hooks implemented, all production-ready:

### useRuns(filters)
```typescript
export function useRuns(filters: Partial<RunListParams> = {}) {
  return useQuery({
    queryKey: queryKeys.runs.list(filters),
    queryFn: () => apiClient<RunListResponse>(`/runs${toSearchParams(filters)}`),
  })
}
```
- Access items via `data?.items` (NOT `data?.runs` — key deviation from task 33 spec)
- Uses global 30s staleTime

### useRun(runId)
- Dynamic staleTime: `Infinity` for terminal runs, 5_000ms + 3s poll for active
- Uses `isTerminalStatus()` from query-keys.ts

### useCreateRun()
- Mutation, invalidates `queryKeys.runs.all` on success

### useRunContext(runId, status?)
- Optional status param to skip extra fetch for staleTime

---

## Query Key Factory (src/api/query-keys.ts)

```typescript
queryKeys.runs.all          // ['runs']
queryKeys.runs.list(filters) // ['runs', filters]
queryKeys.runs.detail(id)   // ['runs', id]
queryKeys.runs.context(id)  // ['runs', id, 'context']
queryKeys.runs.steps(id)    // ['runs', id, 'steps']

isTerminalStatus(status)    // status === 'completed' || 'failed'
```

---

## Filter State (src/stores/filters.ts)

Zustand store with devtools, NO persist:
```typescript
interface FiltersState {
  pipelineName: string | null
  startedAfter: string | null
  startedBefore: string | null
  setPipelineName(name: string | null): void
  setDateRange(startedAfter: string | null, startedBefore: string | null): void
  resetFilters(): void
}
```

NO status filter in Zustand store. Status lives in URL search params (see below).

---

## UI State (src/stores/ui.ts)

```typescript
interface UIState {
  sidebarCollapsed: boolean
  theme: 'dark' | 'light'
  selectedStepId: number | null   // number, NOT string
  stepDetailOpen: boolean
  toggleSidebar(): void
  setTheme(theme: Theme): void
  selectStep(stepId: number | null): void
  closeStepDetail(): void
}
```

Persists `sidebarCollapsed` + `theme` to localStorage (key `llm-pipeline-ui`).
Ephemeral: `selectedStepId`, `stepDetailOpen`.
Sets `dark` class on `document.documentElement` for Tailwind dark mode.

---

## Route Architecture

### Route Tree
- `/` — index.tsx (Run List — currently placeholder)
- `/live` — live.tsx
- `/pipelines` — pipelines.tsx
- `/prompts` — prompts.tsx
- `/runs/$runId` — runs/$runId.tsx (Run Detail — task 34, OUT OF SCOPE)

### Index Route Search Schema (src/routes/index.tsx)
```typescript
const runListSearchSchema = z.object({
  page: fallback(z.number().int().min(1), 1).default(1),
  status: fallback(z.string(), '').default(''),
})
```

Status filter is a URL search param (TanStack Router), NOT in Zustand store.
Page is also URL search param.

### Run Detail Route Search Schema (src/routes/runs/$runId.tsx)
```typescript
{ tab: fallback(z.string(), 'steps').default('steps') }
```
Uses `Route.useParams()` for runId, `Route.useSearch()` for tab.

---

## Layout (src/routes/__root.tsx)

```tsx
<div className="flex h-screen bg-background text-foreground overflow-hidden">
  <aside className="w-60 shrink-0 bg-sidebar border-r border-sidebar-border">
    Sidebar (task 41)
  </aside>
  <main className="flex-1 overflow-auto">
    <Outlet />
  </main>
</div>
```

Main content area: `flex-1 overflow-auto`. Component fills this space.

---

## API Client (src/api/client.ts)

```typescript
async function apiClient<T>(path: string, options?: RequestInit): Promise<T>
```
- Prepends `/api` to path
- Throws `ApiError(status, detail)` on non-2xx
- Dev proxy: Vite proxies `/api` to `http://localhost:8642`

---

## QueryClient Config (src/queryClient.ts)

```typescript
new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,   // 30s default
      retry: 2,
      refetchOnWindowFocus: false,
    },
  },
})
```

---

## Frontend Dependencies (package.json)

Key libraries available for implementation:
- `react` 19.2, `react-dom` 19.2
- `@tanstack/react-router` 1.161.x (TanStack Router)
- `@tanstack/react-query` 5.90.x
- `@tanstack/zod-adapter` 1.161.x
- `zustand` 5.0.x
- `tailwindcss` 4.2.x (Tailwind v4, @tailwindcss/vite plugin)
- `lucide-react` 0.575.x (icons)
- `radix-ui` 1.4.x (headless UI primitives)
- `clsx` + `tailwind-merge` (via `cn()` from `src/lib/utils.ts`)
- `zod` 4.3.x

NO date library (no date-fns, dayjs, etc.). Relative timestamps need native Date.

NO frontend test framework (no vitest, jest). Task 33 testStrategy tests cannot be written without adding a test runner.

---

## Backend Test Patterns (tests/ui/)

Tests use `starlette.testclient.TestClient` with in-memory SQLite (StaticPool).
Pattern: `seeded_app_client` fixture seeds `PipelineRun` + `PipelineStepState` rows directly via SQLModel `Session`.

Status values in tests: `completed`, `failed`, `running` — confirms no `pending`.

---

## Implementation Notes for Task 33

### Filter Integration Pattern
Merge URL search params + Zustand store into `RunListParams`:
```typescript
const { page, status } = Route.useSearch()
const { pipelineName, startedAfter, startedBefore } = useFiltersStore()
const { data, isLoading } = useRuns({
  pipeline_name: pipelineName ?? undefined,
  status: status || undefined,
  started_after: startedAfter ?? undefined,
  started_before: startedBefore ?? undefined,
  offset: (page - 1) * PAGE_SIZE,
  limit: PAGE_SIZE,
})
```

### Data Access
```typescript
data?.items          // RunListItem[] (NOT data?.runs)
data?.total          // total count for pagination
data?.offset
data?.limit
```

### Status Color Coding
Three states: `running` (yellow/amber), `completed` (green), `failed` (red).
Use `cn()` with conditional classes.

### Run ID Truncation
No utility exists. Implement inline: `runId.slice(0, 8)` with full ID in `title` attr.

### Duration Formatting
`total_time_ms` is raw int milliseconds. Convert: `Math.round(ms / 1000)s` or more granular.
`null` for running/incomplete runs.

### Relative Timestamps
No library available. Use `Date.now() - new Date(started_at).getTime()` with manual bucket logic (seconds/minutes/hours/days).

### Row Navigation
Use TanStack Router `Link` or `useNavigate` to `/runs/$runId`.
```typescript
import { Link } from '@tanstack/react-router'
<Link to="/runs/$runId" params={{ runId: run.run_id }}>
```

### Pagination
URL param `page` (1-indexed). Offset = `(page - 1) * limit`. Use `useNavigate` with `search` update to change page.

### Steps Count Display
`run.step_count` — may be `null` for running runs (display as `-` or spinner).
