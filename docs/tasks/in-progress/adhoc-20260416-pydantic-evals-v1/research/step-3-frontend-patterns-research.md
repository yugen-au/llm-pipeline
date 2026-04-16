# Step 3: Frontend Patterns Research (Evals Tab)

## 1. Navigation / Routing

### Router Setup
- **TanStack Router** with file-based routing in `src/routes/`
- `routeTree.gen.ts` auto-generated -- lists all routes, typed via `FileRoutesByTo`
- Router created in `src/router.ts` with module augmentation for type safety
- `src/main.tsx`: `QueryClientProvider` wraps `RouterProvider`

### Route File Pattern
Each route file exports `Route` via `createFileRoute`:
```ts
export const Route = createFileRoute('/reviews')({
  component: ReviewsPage,
})
```
For parameterized routes: `createFileRoute('/review/$token')`.

### Search Params (URL query)
Some routes validate search params with zod:
```ts
const schema = z.object({ key: fallback(z.string(), '').default('') })
export const Route = createFileRoute('/prompts')({
  validateSearch: zodValidator(schema),
  component: PromptsPage,
})
// Usage: const { key } = Route.useSearch()
```

### Root Layout
`__root.tsx`: flex row with `<Sidebar />` + `<main><Outlet /></main>` + `<Toaster>`.

### Sidebar Navigation
`src/components/Sidebar.tsx`:
- `navItems` array of `{ to, label, icon }` typed as `NavItem`
- `to` is `keyof FileRoutesByTo` (compile-time route safety)
- Uses `<Link>` with `activeProps`/`inactiveProps` for active state styling
- Icons from `lucide-react`
- Collapsible sidebar with tooltip fallback when collapsed
- Mobile: Sheet-based hamburger menu

### How Reviews Tab Was Added
1. Created `src/routes/reviews.tsx` with `createFileRoute('/reviews')`
2. Created `src/routes/review/$token.tsx` with `createFileRoute('/review/$token')`
3. Added entry to `navItems` in Sidebar: `{ to: '/reviews', label: 'Reviews', icon: ClipboardCheck }`
4. `routeTree.gen.ts` auto-regenerated (includes both routes)

### Evals Tab Route Plan
Follow same pattern:
- `src/routes/evals.tsx` -- dataset list page (nav entry: `/evals`)
- `src/routes/evals/$datasetId.tsx` -- dataset detail (case editor + run history)
- `src/routes/evals/$datasetId/runs/$runId.tsx` -- run detail (per-case results)
- Add to `navItems`: `{ to: '/evals', label: 'Evals', icon: FlaskConical }` (or similar lucide icon)

## 2. API Layer

### apiClient (`src/api/client.ts`)
- Shared `fetch` wrapper prepending `/api` to paths
- Returns typed `Promise<T>`, throws `ApiError` on non-OK
- Auto-shows toast on error (configurable via `silent` option)
- Signature: `apiClient<T>(path: string, options?: RequestInit & { silent?: boolean })`

### Query Keys (`src/api/query-keys.ts`)
- Centralized factory: `queryKeys.runs.all`, `queryKeys.runs.detail(id)`, etc.
- Hierarchical for targeted invalidation
- Returns `as const` tuples

### Reviews API Pattern (`src/api/reviews.ts`) -- MODEL FOR EVALS
```ts
// 1. Interface definitions (mirroring backend Pydantic models)
export interface ReviewListItem { ... }
export interface ReviewListResponse { items: ReviewListItem[]; total: number }
export interface ReviewDetail { ... }
export interface ReviewSubmitRequest { ... }

// 2. List hook with filters
export function useReviews(filters: Partial<ReviewListParams> = {}) {
  return useQuery({
    queryKey: ['reviews', filters] as const,
    queryFn: () => apiClient<ReviewListResponse>('/reviews' + toSearchParams(filters)),
  })
}

// 3. Detail hook with enabled guard
export function useReview(token: string) {
  return useQuery({
    queryKey: ['reviews', token] as const,
    queryFn: () => apiClient<ReviewDetail>(`/reviews/${token}`),
    enabled: Boolean(token),
  })
}

// 4. Mutation hook with cache invalidation + toast
export function useSubmitReview(token: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (req) => apiClient<Response>(`/reviews/${token}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
    }),
    onSuccess: (data) => {
      toast.success('...')
      qc.invalidateQueries({ queryKey: [...] })
    },
  })
}
```

### TanStack Query Config (`src/queryClient.ts`)
- `staleTime: 30_000`, `retry: 2`, `refetchOnWindowFocus: false`

### Evals API Plan (`src/api/evals.ts`)
Follow reviews.ts pattern:
- `useDatasets(filters)` -- list datasets
- `useDataset(datasetId)` -- dataset detail with cases
- `useDatasetCases(datasetId)` -- cases for editing
- `useCreateCase(datasetId)` / `useUpdateCase(datasetId)` / `useDeleteCase(datasetId, caseId)` -- mutations
- `useEvalRuns(datasetId, filters)` -- run history for a dataset
- `useEvalRun(runId)` -- run detail with per-case results
- `useTriggerEvalRun(datasetId)` -- start evaluation
- Add `evals` section to `queryKeys`

## 3. UI Components

### Component Library
**shadcn/ui** throughout (Radix primitives + Tailwind). Located in `src/components/ui/`:
- `badge.tsx`, `button.tsx`, `card.tsx`, `checkbox.tsx`, `input.tsx`, `label.tsx`
- `select.tsx`, `separator.tsx`, `sheet.tsx`, `table.tsx`, `tabs.tsx`, `textarea.tsx`
- `tooltip.tsx`, `scroll-area.tsx`, `command.tsx`, `dialog.tsx`, `popover.tsx`

### Table Pattern
Used in RunsTable, ReviewsPage:
```tsx
<Table>
  <TableHeader>
    <TableRow>
      <TableHead>Column</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    {items.map(item => (
      <TableRow key={item.id} className="cursor-pointer hover:bg-muted/50" onClick={...}>
        <TableCell>...</TableCell>
      </TableRow>
    ))}
  </TableBody>
</Table>
```
- Clickable rows navigate to detail pages via `useNavigate()`
- Loading state: skeleton rows with `animate-pulse`
- Empty state: single row spanning all columns
- Error state: destructive text in spanning cell

### Card Pattern
Used in ReviewPage detail:
```tsx
<Card>
  <CardHeader className="pb-3">
    <CardTitle className="text-base">Title</CardTitle>
  </CardHeader>
  <CardContent className="space-y-4">
    ...
  </CardContent>
</Card>
```

### Badge / Status Pattern
`StatusBadge` component maps status strings to colored outline badges:
```tsx
const statusConfig: Record<string, BadgeConfig> = {
  running: { variant: 'outline', className: 'border-status-running text-status-running' },
  completed: { variant: 'outline', className: 'border-status-completed text-status-completed' },
  failed: { variant: 'outline', className: 'border-status-failed text-status-failed' },
}
```
Reviews page uses inline badge functions for status/decision. Evals should follow StatusBadge pattern for pass/fail/error states.

### Filter Pattern
Two approaches used:
1. **Simple Select** (FilterBar, ReviewsPage): `<Select>` with `onValueChange`, `ALL_SENTINEL` for "All" option
2. **Multi-filter bar** (PromptFilterBar): multiple selects + text search in a row

### Page Layout Pattern
All pages follow:
```tsx
<div className="flex h-full flex-col gap-4 p-6">
  <div className="flex items-center justify-between">
    <h1 className="text-2xl font-semibold text-card-foreground">Title</h1>
    {/* filters / actions */}
  </div>
  <Card className="min-h-0 flex-1 overflow-hidden">
    <ScrollArea className="h-full">
      {/* content */}
    </ScrollArea>
  </Card>
</div>
```

### ScrollArea
`<ScrollArea>` from shadcn/ui wraps all scrollable content. `TabScrollArea` helper: `h-[calc(100vh-220px)]`.

### Shared Components (`src/components/shared/`)
- `EmptyState` -- simple muted text
- `LoadingSkeleton` -- loading placeholder
- `TabScrollArea` -- scroll area sized for tab content
- `BadgeSection` -- grouped badges
- `LabeledPre` -- labeled preformatted text

## 4. Data Display Patterns

### DisplayField Renderer (review/$token.tsx)
Renders structured data from `review_data.display_data` array:
- Each field has `{ label, value, type }` where type is: `progress`, `badge`, `table`, `code`, `number`, `text`
- `table` type renders inline `<table>` with dynamic headers from first row's keys
- Pattern: label as `text-xs text-muted-foreground`, value rendered by type

### JSON/Dict Data (JsonViewer)
`src/components/JsonViewer.tsx`:
- Two modes: **DataView** (plain expandable tree) and **DiffView** (microdiff-powered)
- Recursive `DataNode` component with expand/collapse
- Color-coded primitives: green=string, blue=number, orange=boolean
- Used for raw_data expansion in review detail

### Raw Data Collapsible
```tsx
<Card>
  <button onClick={toggle}>
    {expanded ? <ChevronDown /> : <ChevronRight />}
    Raw Data
  </button>
  {expanded && <CardContent><JsonViewer data={rawData} /></CardContent>}
</Card>
```

## 5. State Management

### Zustand (`src/stores/ui.ts`)
- `useUIStore`: sidebar, theme, step-detail panel state
- `persist` middleware for localStorage (sidebar + theme only)
- `devtools` middleware in DEV mode
- Pattern: `create<State>()(devtools(persist(...)))`

### Filters Store
- `useFiltersStore`: run list filter state (pipeline name, date range)
- Kept separate from URL search params

## 6. Evals-Specific UI Mapping

### Dataset List Page (`/evals`)
**Model: reviews.tsx**
- Table with columns: Name, Step Target, Case Count, Last Run Score, Last Run Date, Status
- Click row -> navigate to `/evals/$datasetId`
- Filter by step target (Select dropdown)
- Score column: colored badge (green >80%, yellow 50-80%, red <50%)

### Dataset Detail Page (`/evals/$datasetId`)
**Model: prompts.tsx (split panel) + review/$token.tsx (cards)**
- Header: dataset name, step target badge, case count, action buttons (Run Eval, Add Case)
- Two sections via Tabs component: "Cases" tab + "Run History" tab

#### Cases Tab (THE KEY NOVEL UI)
- Tabular case editor -- columns derived from step's `instructions_schema` (JSON Schema)
- `instructions_schema` already available via `PipelineStepMetadata.instructions_schema`
- Each field in the JSON Schema `properties` = one column
- Plus `expected_output` column (freeform or structured)
- Rows are editable inline: `<Input>` / `<Textarea>` / `<Select>` based on field type from schema
- Add/delete row buttons
- Save button triggers mutation (PUT/PATCH per case or batch)
- **Implementation approach**: Use existing `<Table>` component with editable `<TableCell>` content. Map JSON Schema types to input components:
  - `string` -> `<Input>` or `<Textarea>` (if long)
  - `number`/`integer` -> `<Input type="number">`
  - `boolean` -> `<Checkbox>`
  - `enum` -> `<Select>` with enum values
  - `object`/`array` -> `<Textarea>` with JSON editing (or JsonViewer for display)

#### Run History Tab
- Simple table: Run ID, Started, Duration, Score, Status
- Click row -> navigate to `/evals/$datasetId/runs/$runId`

### Run Detail Page (`/evals/$datasetId/runs/$runId`)
**Model: runs/$runId.tsx + review/$token.tsx**
- Header: run metadata (dataset name, started, duration, overall score)
- Per-case results table:
  - Columns: Case Name/ID, each evaluator name, Overall Pass/Fail
  - Cells: pass/fail badge per evaluator
  - Click row -> expand to show evaluator details (scores, reasoning)
- Use collapsible row pattern (ChevronDown/ChevronRight) similar to JsonViewer

## 7. File Checklist for Implementation

### New Files
- `src/routes/evals.tsx` -- dataset list page
- `src/routes/evals/$datasetId.tsx` -- dataset detail page
- `src/routes/evals_.$datasetId.runs.$runId.tsx` -- run detail (flat file naming for deep nested route)
- `src/api/evals.ts` -- all hooks + types
- `src/components/evals/DatasetList.tsx` -- table component (optional, can inline in route)
- `src/components/evals/CaseEditor.tsx` -- the dynamic schema-driven table editor
- `src/components/evals/RunResultsTable.tsx` -- per-case results grid
- `src/components/evals/EvalScoreBadge.tsx` -- score/pass-fail badge

### Modified Files
- `src/components/Sidebar.tsx` -- add evals NavItem
- `src/api/query-keys.ts` -- add `evals` section
- `routeTree.gen.ts` -- auto-regenerated

### Reusable Existing Components
- `Table/*`, `Badge`, `Card/*`, `ScrollArea`, `Select`, `Button`, `Input`, `Textarea`, `Checkbox`
- `Tabs/TabsList/TabsTrigger/TabsContent` (for Cases/Run History tabs)
- `JsonViewer` (for displaying complex case data)
- `StatusBadge` pattern (extend or create EvalScoreBadge)
- `Pagination` (if dataset list grows large)
- `EmptyState`, `LoadingSkeleton`
- `Tooltip/TooltipProvider` (for truncated content)
