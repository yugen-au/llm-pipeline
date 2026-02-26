# Step 1: Frontend Patterns Research - Prompt Browser View (Task 39)

## Tech Stack Summary

| Layer | Technology | Version |
|-------|-----------|---------|
| Framework | React | 19.2 |
| Router | TanStack Router (file-based) | 1.161.3 |
| Server state | TanStack Query | 5.90 |
| Client state | Zustand | 5.0 |
| Styling | Tailwind CSS v4 + shadcn/ui | 4.2 |
| Build | Vite | 7.3 |
| Test | Vitest + @testing-library/react | 3.2 / 16.3 |
| Path alias | `@/` -> `./src/*` | tsconfig |

## Frontend Root

All paths below relative to `llm_pipeline/ui/frontend/src/`.

## Routing Pattern

TanStack Router file-based routing. Each route file exports `Route` via `createFileRoute`.

```typescript
// src/routes/prompts.tsx (placeholder -- already exists)
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/prompts')({
  component: PromptsPage,
})

function PromptsPage() { ... }
```

Route tree auto-generated in `src/routeTree.gen.ts`. Router created in `src/router.ts`. Search params validated with zod via `@tanstack/zod-adapter` (see index.tsx, $runId.tsx).

**Key:** prompts.tsx already exists as stub. Just needs to be fleshed out.

## State Management Patterns

### TanStack Query (server state)
- Global QueryClient in `src/queryClient.ts`: staleTime 30s, retry 2, refetchOnWindowFocus false.
- Query key factory in `src/api/query-keys.ts` -- hierarchical for cache invalidation.
- API hooks per resource in `src/api/` files (runs.ts, steps.ts, events.ts, prompts.ts, pipelines.ts).
- `apiClient<T>(path)` in `src/api/client.ts` prepends `/api`, throws typed `ApiError`.

### Zustand (client state)
- `stores/ui.ts` -- sidebar, theme, step detail panel (persisted subset to localStorage).
- `stores/filters.ts` -- ephemeral run list filters (no persistence).
- Pattern: `create<State>()(devtools(persist(...)))` with named devtools.

## Existing API Hooks for Prompts

### Available (`src/api/prompts.ts`)
```typescript
export function usePrompts(filters: Partial<PromptListParams> = {}) {
  return useQuery({
    queryKey: queryKeys.prompts.list(filters),
    queryFn: () => apiClient<PromptListResponse>('/prompts' + toSearchParams(filters)),
  })
}
```

### Missing -- Needs Creation
- **`usePromptDetail(promptKey)`** -- fetches `GET /api/prompts/{prompt_key}` returning `PromptDetail` (grouped variants).
- **Query key** -- `queryKeys.prompts.detail(key)` not in factory yet.

### Backend API Shape
| Endpoint | Response | Filters |
|----------|----------|---------|
| `GET /api/prompts` | `PromptListResponse { items: Prompt[], total, offset, limit }` | prompt_type, category, step_name, is_active, offset, limit |
| `GET /api/prompts/{prompt_key}` | `PromptDetailResponse { prompt_key, variants: PromptVariant[] }` | none |

### TypeScript Types (all in `src/api/types.ts`)
- `Prompt` -- full prompt entity (id, prompt_key, prompt_name, prompt_type, category, step_name, content, required_variables, description, version, is_active, created_at, updated_at, created_by)
- `PromptListResponse` -- paginated list wrapper
- `PromptListParams` -- query param interface (prompt_type?, category?, step_name?, is_active?, offset?, limit?)
- `PromptDetail` -- grouped detail (prompt_key + variants[])
- `PromptVariant` -- identical shape to Prompt (system/user variant)

## Component & Styling Patterns

### shadcn/ui Components Available
Card, Badge, Button, Select, ScrollArea, Sheet, Tabs, Separator, Tooltip, Table, Input, Label, Checkbox, Textarea.

### CSS Approach
- Tailwind v4 utility classes exclusively. No CSS modules.
- `cn()` helper from `src/lib/utils.ts` (clsx + tailwind-merge).
- Dark mode via `.dark` class on `<html>`. Theme managed by Zustand ui store.
- Design tokens via CSS custom properties (oklch color space).

### Monospace / Code Display Pattern
Consistent across StepDetailPanel, EventStream:
```tsx
<pre className="whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs">
  {content}
</pre>
```
For inline code: `<code className="font-mono text-xs">`.

### Filter Pattern (FilterBar)
Uses shadcn Select with `ALL_SENTINEL = '__all'` (Radix requires non-empty string values):
```tsx
<Select value={selectValue} onValueChange={handleChange}>
  <SelectTrigger id="filter-id" className="w-[160px]">
    <SelectValue placeholder="All" />
  </SelectTrigger>
  <SelectContent>
    {OPTIONS.map(opt => <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>)}
  </SelectContent>
</Select>
```

### Loading State Pattern
Skeleton using `animate-pulse rounded bg-muted` divs with fixed dimensions:
```tsx
<div className="h-5 w-40 animate-pulse rounded bg-muted" />
```

### Error State Pattern
```tsx
<p className="text-sm text-destructive">Failed to load ...</p>
```

### Empty State Pattern
```tsx
<p className="text-sm text-muted-foreground">No items found</p>
```

## Split-Pane Layout Precedents

### RunDetailPage (`routes/runs/$runId.tsx`)
Flex layout with main column + fixed-width sidebar:
```tsx
<div className="flex min-h-0 flex-1 gap-4">
  {/* Main column */}
  <CardContent className="flex-1 overflow-auto rounded-xl border p-0">...</CardContent>
  {/* Right sidebar */}
  <div className="w-80 shrink-0 overflow-hidden rounded-xl border">...</div>
</div>
```

### LivePage (`routes/live.tsx`)
3-column desktop grid + mobile tabs:
```tsx
{/* Desktop */}
<div className="hidden min-h-0 flex-1 lg:grid lg:grid-cols-3 lg:gap-4">...</div>
{/* Mobile */}
<div className="flex min-h-0 flex-1 flex-col lg:hidden">
  <Tabs>...</Tabs>
</div>
```

### Root Layout (`routes/__root.tsx`)
Full-height flex with sidebar:
```tsx
<div className="flex h-screen bg-background text-foreground overflow-hidden">
  <aside className="w-60 shrink-0 bg-sidebar border-r border-sidebar-border">...</aside>
  <main className="flex-1 overflow-auto"><Outlet /></main>
</div>
```

## Recommended Implementation Approach

### Layout: Split-Pane for Prompt Browser
Follow RunDetailPage pattern -- flex with fixed-width left sidebar + flex-1 detail:
```tsx
<div className="flex h-full flex-col gap-4 p-6">
  <h1>...</h1>
  <div className="flex min-h-0 flex-1 gap-4">
    {/* Left: prompt list + filters */}
    <div className="w-80 shrink-0 overflow-hidden rounded-xl border">
      <PromptFilterBar />
      <PromptList />
    </div>
    {/* Right: prompt detail viewer */}
    <div className="flex-1 overflow-auto rounded-xl border">
      <PromptViewer />
    </div>
  </div>
</div>
```

### Variable Highlighting Strategy
Task description uses `dangerouslySetInnerHTML`. Safer approach -- split content on `{variable_name}` regex and render React elements:
```tsx
function highlightVariables(content: string): React.ReactNode[] {
  const parts = content.split(/(\{[\w.]+\})/)
  return parts.map((part, i) =>
    /^\{[\w.]+\}$/.test(part)
      ? <span key={i} className="text-blue-400 bg-blue-900/30 rounded px-0.5">{part}</span>
      : part
  )
}
```
Wrap in `<pre className="whitespace-pre-wrap font-mono text-xs">` for monospace.

### Filtering by "Pipeline Association"
Backend prompts API has no `pipeline_name` filter. Prompts have `step_name` field (steps belong to pipelines). Two options:
1. **Filter by step_name** -- direct, uses existing API param. This is the straightforward approach.
2. **Cross-reference pipelines API** -- fetch pipeline metadata, extract step names, filter prompts by matched step_name. Adds complexity.

**Recommendation:** Use step_name filter directly. It provides pipeline association implicitly (each step name is unique to a pipeline context). The prompt_type filter covers the "type" dimension.

### New API Artifacts Needed
1. Add `queryKeys.prompts.detail(key)` to `src/api/query-keys.ts`
2. Add `usePromptDetail(promptKey)` to `src/api/prompts.ts`

### New Files
- `src/routes/prompts.tsx` -- overwrite placeholder with full Prompt Browser page
- `src/components/PromptViewer.tsx` -- prompt detail viewer component

### Testing
Follow existing patterns: Vitest + @testing-library/react + userEvent. Tests colocated with components (`*.test.tsx`).

## No Dependencies to Add
All needed components (Select, ScrollArea, Badge, Card, Tabs) already installed via shadcn/ui. No new npm packages required.
