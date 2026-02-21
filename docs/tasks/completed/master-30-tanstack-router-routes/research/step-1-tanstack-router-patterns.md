# Research: TanStack Router v1 File-Based Routing Patterns

## 1. Current State (from Task 29)

Frontend lives at `llm_pipeline/ui/frontend/`. Key existing files:

| File | Purpose |
|------|---------|
| `vite.config.ts` | `tanstackRouter()` plugin (no options), `react()`, `tailwindcss()`, `@/` alias, proxy config |
| `src/routes/__root.tsx` | Bare `createRootRoute` with `<Outlet />` only |
| `src/routes/index.tsx` | Placeholder `createFileRoute('/')` with centered text |
| `src/routeTree.gen.ts` | Auto-generated route tree (2 routes: root + index) |
| `src/router.ts` | `createRouter({ routeTree })` + `Register` module augmentation |
| `src/main.tsx` | `QueryClientProvider` > `RouterProvider`, dark class applied |
| `src/queryClient.ts` | Shared QueryClient (staleTime=30s, retry=2) |

Installed versions:
- `@tanstack/react-router`: ^1.161.3
- `@tanstack/router-plugin`: ^1.161.3 (devDep)
- `zod`: NOT installed
- `@tanstack/zod-adapter`: NOT installed

## 2. Vite Plugin Configuration

### Current
```ts
plugins: [tanstackRouter(), react(), tailwindcss()]
```

### Recommended
```ts
plugins: [
  tanstackRouter({
    target: 'react',
    autoCodeSplitting: true,
  }),
  react(),
  tailwindcss(),
]
```

Key options per Context7 docs:
- `target: 'react'` -- explicit target (default is react but best to be explicit)
- `autoCodeSplitting: true` -- automatically code-splits every route's component, loader, etc. into separate chunks without manual `.lazy.tsx` files
- Plugin MUST come before `react()` (already correct in current config)

### Optional: tsr.config.json
Can also configure via `tsr.config.json` at frontend root:
```json
{
  "routesDirectory": "./src/routes",
  "generatedRouteTree": "./src/routeTree.gen.ts",
  "routeFileIgnorePrefix": "-",
  "routeFileIgnorePattern": "\\.(test|spec)\\.",
  "quoteStyle": "single",
  "semicolons": false,
  "autoCodeSplitting": true
}
```
**Recommendation:** Pass options directly in `vite.config.ts` rather than a separate config file -- fewer files, same effect.

## 3. Route File Conventions

### File naming to URL mapping

| File | URL Path | Notes |
|------|----------|-------|
| `routes/__root.tsx` | n/a | Root layout, wraps all routes |
| `routes/index.tsx` | `/` | Index route for root |
| `routes/about.tsx` | `/about` | Static segment |
| `routes/runs/$runId.tsx` | `/runs/:runId` | Dynamic param segment |
| `routes/runs/index.tsx` | `/runs` | Index for /runs (if needed) |
| `routes/_layout.tsx` | n/a | Pathless layout route (underscore prefix) |
| `routes/_layout/dashboard.tsx` | `/dashboard` | Child of pathless layout |

### Key conventions
- `__root.tsx` -- the root route (double underscore), always at `src/routes/__root.tsx`
- `index.tsx` -- index route for its directory
- `$param.tsx` -- dynamic route parameter (the `$` prefix)
- `_prefix` -- pathless layout routes (single underscore), used for shared layouts without adding a URL segment
- `-prefix` -- ignored files (won't become routes)
- `.test.` / `.spec.` patterns -- ignored by default config

### Export pattern
Every route file must export `Route` using `createFileRoute`:
```tsx
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/path')({
  component: MyComponent,
})
```

The path string argument to `createFileRoute` is auto-filled by the codegen -- you write it for type inference but the plugin overwrites it during generation.

## 4. Proposed Route File Structure

Target routes: `/` (run list), `/runs/$runId` (run detail), `/live` (live execution), `/prompts` (prompt browser), `/pipelines` (pipeline structure)

```
src/routes/
  __root.tsx          # Root layout: sidebar shell + <Outlet /> in main area
  index.tsx           # / -> RunListPage (already exists, needs update)
  live.tsx            # /live -> LiveExecutionPage
  prompts.tsx         # /prompts -> PromptBrowserPage
  pipelines.tsx       # /pipelines -> PipelineStructurePage
  runs/
    $runId.tsx        # /runs/$runId -> RunDetailPage
```

### Why this structure
- No `runs/index.tsx` needed -- the root `index.tsx` at `/` IS the run list
- `/runs/$runId` needs a directory because `$runId` is a dynamic segment under `/runs`
- `/live`, `/prompts`, `/pipelines` are top-level flat files (no nesting needed)
- No pathless layout routes (`_layout`) needed at this stage -- the root layout handles the sidebar/main structure

### Expected routeTree.gen.ts output
After codegen, the route tree will register these routes:
- `__root__` (root layout)
- `/` (index)
- `/live`
- `/prompts`
- `/pipelines`
- `/runs/$runId`

## 5. routeTree.gen.ts Auto-Generation

### How it works
- The `@tanstack/router-plugin` Vite plugin watches `src/routes/` during dev
- On file add/remove/rename, it regenerates `src/routeTree.gen.ts`
- The generated file imports all route files and wires parent-child relationships
- **Never edit manually** -- it has `@ts-nocheck` and `eslint-disable` headers
- Should be committed to git (already is) so builds work without the plugin running
- Already excluded from ESLint and Prettier via task 29 config

### Triggering regeneration
- Automatically on `npm run dev` (Vite dev server)
- Automatically on `npm run build` (Vite build)
- Manually: the plugin can be run standalone but typically not needed

## 6. Zod Search Params Integration

### Packages to install
```bash
npm install zod @tanstack/zod-adapter
```

### Pattern: Validated search params with fallback defaults
```tsx
import { createFileRoute } from '@tanstack/react-router'
import { fallback, zodValidator } from '@tanstack/zod-adapter'
import { z } from 'zod'

const runListSearchSchema = z.object({
  page: fallback(z.number(), 1).default(1),
  pageSize: fallback(z.number(), 20).default(20),
  status: fallback(z.enum(['all', 'running', 'completed', 'failed']), 'all').default('all'),
  pipeline: z.string().optional(),
  search: z.string().optional(),
})

export const Route = createFileRoute('/')({
  validateSearch: zodValidator(runListSearchSchema),
  component: RunListPage,
})

function RunListPage() {
  const { page, pageSize, status, pipeline, search } = Route.useSearch()
  // fully type-safe, validated, with defaults applied
}
```

### Key points
- `fallback(schema, defaultValue)` from `@tanstack/zod-adapter` -- provides a safe default when URL param is invalid/missing (no error thrown, just uses fallback)
- `zodValidator(schema)` -- wraps the Zod schema for TanStack Router's `validateSearch`
- `Route.useSearch()` -- hook to read validated search params in components
- Search params update via `<Link search={...}>` or `navigate({ search: ... })`
- Can share search params across routes by defining them in `__root.tsx` `validateSearch`

### Routes that likely need search params
| Route | Likely search params |
|-------|---------------------|
| `/` (run list) | page, pageSize, status, pipeline, search, sort, order |
| `/runs/$runId` | tab (for detail sub-views) |
| `/prompts` | search, pipeline |
| `/pipelines` | search |
| `/live` | filter |

Actual schemas are implementation concerns -- this documents the pattern.

## 7. Code Splitting Patterns

### Auto code splitting (recommended)
With `autoCodeSplitting: true` in the Vite plugin config, TanStack Router automatically:
- Splits each route's `component` into a lazy-loaded chunk
- Splits `loader`, `pendingComponent`, `errorComponent` similarly
- Keeps `validateSearch`, `beforeLoad`, path params validation in the critical (non-lazy) chunk
- No manual `.lazy.tsx` files needed

This is the recommended approach for this project. Each route file stays as a single file with `createFileRoute`.

### Manual code splitting (alternative, NOT recommended here)
Split a route into two files:
- `routes/posts.tsx` -- critical exports (loader, validateSearch)
- `routes/posts.lazy.tsx` -- lazy exports (component) using `createLazyFileRoute`

```tsx
// routes/posts.lazy.tsx
import { createLazyFileRoute } from '@tanstack/react-router'

export const Route = createLazyFileRoute('/posts')({
  component: Posts,
})
```

**Not needed** when `autoCodeSplitting: true` is enabled -- the plugin handles this automatically.

## 8. Root Layout Pattern

### Current __root.tsx
```tsx
import { createRootRoute, Outlet } from '@tanstack/react-router'

export const Route = createRootRoute({
  component: () => <Outlet />,
})
```

### Proposed __root.tsx (sidebar + main content shell)
```tsx
import { createRootRoute, Outlet } from '@tanstack/react-router'

export const Route = createRootRoute({
  component: RootLayout,
})

function RootLayout() {
  return (
    <div className="flex h-screen overflow-hidden bg-background text-foreground">
      {/* Sidebar placeholder -- actual Sidebar component is task 41 */}
      <aside className="w-60 shrink-0 border-r border-border bg-sidebar" />
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
```

### Key decisions
- `h-screen` + `overflow-hidden` on outer div -- prevents double scrollbar
- `overflow-auto` on `<main>` -- page content scrolls independently
- Sidebar is a placeholder `<aside>` -- task 41 replaces with full `<Sidebar />` component
- Uses shadcn CSS variables (`bg-background`, `bg-sidebar`, `border-border`) already defined in `index.css`
- No sidebar state logic here (that's task 32 Zustand stores)

### Global search params in root (optional)
Could add global search params (e.g., debug mode) to root:
```tsx
export const Route = createRootRoute({
  validateSearch: zodValidator(globalSearchSchema),
  component: RootLayout,
})
```
Not needed initially -- individual route search params suffice.

## 9. Dependencies to Install

```bash
cd llm_pipeline/ui/frontend
npm install zod @tanstack/zod-adapter
```

These are runtime dependencies (not devDeps) because:
- `zod` -- schema validation runs at runtime in the browser
- `@tanstack/zod-adapter` -- adapter wraps zod for router's validateSearch at runtime

## 10. Scope Boundaries

### IN scope (task 30)
- Update `vite.config.ts` to enable `autoCodeSplitting`
- Update `__root.tsx` with sidebar+main layout shell
- Create route files: `live.tsx`, `prompts.tsx`, `pipelines.tsx`, `runs/$runId.tsx`
- Update `index.tsx` with search params pattern
- Install `zod` + `@tanstack/zod-adapter`
- Verify `routeTree.gen.ts` regenerates correctly
- Add Zod search param validation to routes that need it

### OUT of scope
- Task 31: TanStack Query API hooks (src/api/ directory)
- Task 32: Zustand UI state stores (sidebar state, filters state)
- Task 41: Sidebar navigation component (actual `<Sidebar />` with nav links, icons, collapse logic)
- Actual page content/components beyond placeholder scaffolds
- WebSocket integration
- Any data fetching logic

## 11. Implementation Notes

### Route component pattern
Each route file should follow this pattern for consistency:
```tsx
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/path')({
  component: PageName,
})

function PageName() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold">Page Title</h1>
      <p className="text-muted-foreground">Placeholder</p>
    </div>
  )
}
```

### Dynamic param access
```tsx
// In runs/$runId.tsx
function RunDetailPage() {
  const { runId } = Route.useParams()
  return <div>Run: {runId}</div>
}
```

### TanStack DevTools
Consider adding TanStack Router DevTools in dev mode (already have React Query DevTools in devDeps):
```tsx
// In __root.tsx, conditionally
import { TanStackRouterDevtools } from '@tanstack/router-devtools'
```
This is optional and can be added during implementation if helpful for debugging.
