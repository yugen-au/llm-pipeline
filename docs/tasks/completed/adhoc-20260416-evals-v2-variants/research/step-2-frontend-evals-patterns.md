# Step 2: Frontend Evals UI Patterns Research

## Routing Structure

### Current evals routes (TanStack Router, file-based, dot notation)
- `evals.tsx` -- layout wrapper, renders `<Outlet />`
- `evals.index.tsx` -- dataset list page
- `evals.$datasetId.tsx` -- layout wrapper for dataset, renders `<Outlet />`
- `evals.$datasetId.index.tsx` -- dataset detail (tabs: Cases + Run History)
- `evals.$datasetId.runs.$runId.tsx` -- run detail page

### Route pattern
- Layout routes export `createFileRoute` with `<Outlet />`
- Leaf routes export component function
- Params accessed via `Route.useParams()`, converted with `Number(rawId)`
- Navigation: `useNavigate()` with `navigate({ to: '/evals/${id}' as string })`
- Back links: `<Link to="/evals/$datasetId" params={{ datasetId: String(datasetId) }}>`

### New routes needed
- `evals.$datasetId.variants.$variantId.tsx` -- variant editor page
- `evals.$datasetId.compare.tsx` -- comparison view
- `routeTree.gen.ts` auto-regenerates on file creation

## API Hook Patterns

### File: `src/api/evals.ts`
- Standard pattern: `useQuery`/`useMutation` with `apiClient` wrapper
- `apiClient<T>(path, options)` prepends `/api`, throws typed `ApiError`, shows toast
- Query keys via factory: `queryKeys.evals.detail(id)`, `queryKeys.evals.runs(datasetId)`
- Mutations: `useMutation` + `toast.success()` + `qc.invalidateQueries()`
- Filters passed as search params via `toSearchParams()` helper (reuse for variant filters)
- `enabled` guard: `enabled: id > 0` for numeric IDs, `enabled: Boolean(token)` for strings

### Query key structure (src/api/query-keys.ts)
```ts
evals: {
  all: ['evals'],
  list: (filters?) => ['evals', filters],
  detail: (id) => ['evals', id],
  runs: (datasetId) => ['evals', datasetId, 'runs'],
  run: (datasetId, runId) => ['evals', datasetId, 'runs', runId],
  schema: (targetType, targetName) => ['evals', 'schema', targetType, targetName],
}
```

New keys needed:
```ts
variants: (datasetId) => ['evals', datasetId, 'variants'],
variant: (datasetId, variantId) => ['evals', datasetId, 'variants', variantId],
variantDiff: (datasetId, variantId) => ['evals', datasetId, 'variants', variantId, 'diff'],
```

### Existing hooks to extend
- `useTriggerEvalRun` -- add `variant_id` to `TriggerRunRequest`
- `useEvalRuns` -- add variant filter param
- `RunListItem` / `RunDetail` -- add `variant_id`, `variant_name` fields

### New hooks needed
- `useVariants(datasetId)` -- list variants
- `useVariant(datasetId, variantId)` -- single variant detail
- `useCreateVariant(datasetId)` -- create
- `useUpdateVariant(datasetId)` -- update delta
- `useDeleteVariant(datasetId)` -- delete
- `useVariantDiff(datasetId, variantId)` -- production vs delta diff
- `useAcceptVariant(datasetId, variantId)` -- accept workflow

## Component Architecture

### Dataset detail page (evals.$datasetId.index.tsx)
- Uses `<Tabs defaultValue="cases">` with `<TabsList>` + `<TabsTrigger>` + `<TabsContent>`
- Currently 2 tabs: Cases, Run History
- Add third tab: Variants
- Header: back button + title + target badge + delete button

### Case editor pattern (reusable for variant instructions editor)
- `useCaseEditor(cases)` hook: manages `Map<id, RowState>` with dirty tracking
- Temp IDs for new rows (negative integers, decrementing)
- `addRow()`, `updateRow(id, patch)`, `removeRow(id)` callbacks
- Sync from server via `useMemo` watching `cases` array
- Row-level save/delete buttons, only shown when dirty
- **Directly reusable** for instructions field add/remove/modify UI

### Schema-driven field inputs (FieldInput component)
- `extractFieldsFromJsonSchema()` parses JSON schema properties into `FieldDef[]`
- `FieldInput` renders appropriate control per type: boolean->Checkbox, number->Input[type=number], object/array->Textarea(JSON), string->Input
- Used in CasesTab for both input and expected_output fields
- **Reusable** for variant instructions field editor (type-aware editing per field)

### JSON fallback input (JsonInput component)
- Raw JSON textarea with parse validation, red border on invalid
- Used when schema not available
- **Reusable** for delta JSON editing fallback

## Editor Components

### Monaco editor (lazy-loaded)
- `@monaco-editor/react` via `lazy(() => import(...))`
- Used in: `CreatorEditor.tsx` (Python), `PromptViewer.tsx` (Markdown)
- PromptViewer has variable highlighting, hover provider, completion provider
- Editor options: `minimap: false, wordWrap: 'on', fontSize: 13, scrollBeyondLastLine: false`
- Dark mode detection via `useIsDark()` hook (MutationObserver on document.documentElement class)
- **Reuse** `PromptContentEditor` pattern for variant prompt editing

### PromptViewer form pattern
- `VariantFormState` + `formFromVariant()` + `formDirty()` for dirty tracking
- `MetadataGrid` component: labeled grid of inputs (grid-cols-2 gap-3 lg:grid-cols-3)
- Save/Discard/Delete button bar at bottom
- `useEffect` resets form when upstream data changes (after save)
- **Reuse pattern** for variant editor save/discard flow

## Diff/Comparison Components

### JsonViewer (src/components/JsonViewer.tsx)
- Two modes: DataView (plain tree) and DiffView (microdiff-based)
- DiffView: `diff(before, after)` from `microdiff`, builds tree of changes
- Color coding: CREATE=green, REMOVE=red+strikethrough, CHANGE=yellow
- Expandable/collapsible nodes, changes sorted to top
- **Directly reusable** for variant delta diff panel in comparison view
- Usage: `<JsonViewer before={prodConfig} after={variantConfig} />`

### Run detail stat cards
- 4-card grid: `grid grid-cols-2 sm:grid-cols-4 gap-3`
- Each card: number + label, color-coded (green=passed, red=failed, yellow=errored)
- **Reuse** for comparison view aggregate stats (side-by-side stat cards)

### Expandable result rows
- `CaseResultRow` with chevron toggle, detail panel below
- Per-evaluator score columns, ScoreCell with color thresholds
- **Reuse** for side-by-side comparison (two score columns per evaluator)

## Shared Components Available

| Component | Location | Reuse For |
|-----------|----------|-----------|
| Badge | ui/badge.tsx | variant name badges on runs |
| Card | ui/card.tsx | variant list cards, stat cards |
| Table | ui/table.tsx | instructions field table, results grid |
| Tabs | ui/tabs.tsx | variant tab on dataset detail |
| Select | ui/select.tsx | model selector, variant filter |
| Dialog | ui/dialog.tsx | accept confirmation, new variant |
| ScrollArea | ui/scroll-area.tsx | page scroll wrapping |
| Input/Textarea | ui/input.tsx, ui/textarea.tsx | field editors |
| Checkbox | ui/checkbox.tsx | field boolean inputs |
| Command/Popover | ui/command.tsx, ui/popover.tsx | model selector (combobox) |
| EmptyState | shared/EmptyState.tsx | empty variant list |
| LoadingSkeleton | shared/LoadingSkeleton.tsx | loading states |
| JsonViewer | JsonViewer.tsx | delta diff display |

## Filter/Badge Patterns

### Status badge pattern (multiple implementations)
- `runStatusBadge(status)` in dataset detail -- `Badge variant="outline"` with color map
- `statusBadge(status)` in reviews -- same pattern
- `passRateBadge(rate)` in dataset list -- percentage with threshold colors
- **Pattern**: `Badge variant="outline" className={colorMap[value]}`

### Filter pattern (reviews page)
- `useState<string>('all')` for filter state
- `Select` dropdown in header area
- Filter object passed to query hook: `useReviews(filters)`
- Conditional filter: `statusFilter === 'all' ? {} : { status: statusFilter }`
- **Reuse** for variant filter on run history tab

## Variant Editor Page Architecture

Based on patterns found, the variant editor should follow:

### Layout
```
+----------------------------------+----------------------------------+
| Production (read-only)           | Variant (editable)               |
|                                  |                                  |
| Model: anthropic:claude-...      | Model: [Select dropdown]         |
|                                  |                                  |
| System Prompt:                   | System Prompt:                   |
| [Monaco read-only]               | [Monaco editable]                |
|                                  |                                  |
| User Prompt:                     | User Prompt:                     |
| [Monaco read-only]               | [Monaco editable]                |
|                                  |                                  |
| Instructions Fields:             | Instructions Fields:             |
| [Table read-only]                | [Table editable + add/remove]    |
+----------------------------------+----------------------------------+
                    [Save]  [Discard]  [Run with Variant]
```

### Implementation approach
- CSS grid `grid-cols-2 gap-4` for split view
- Left panel: production data from `useVariantDiff` or `useInputSchema`, all inputs disabled
- Right panel: editable form using PromptViewer patterns (MetadataGrid, Monaco, FieldInput table)
- Model selector: `Select` with available models (new endpoint or existing pipeline model config)
- Instructions editor: reuse `useCaseEditor` pattern for field row management
- Dirty tracking: `formDirty()` pattern from PromptViewer
- Save: PUT variant delta, Discard: reset to server state

### Comparison page architecture
- Header: Variant A vs Variant B names
- Delta diff: `<JsonViewer before={deltaA} after={deltaB} />`
- Results: side-by-side Table with per-case scores for each variant
- Aggregate: stat card grid comparing pass rates
- Accept button: Dialog confirmation then POST accept endpoint

## No Questions

All patterns are well-established and consistent. The v2 plan aligns cleanly with existing component architecture. No architectural ambiguities found.
