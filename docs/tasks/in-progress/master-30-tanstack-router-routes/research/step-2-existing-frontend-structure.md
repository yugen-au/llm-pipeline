# Step 2: Existing Frontend Structure Analysis

## Frontend Location

Project lives at `llm_pipeline/ui/frontend/` (NOT `frontend/` at project root).

## Directory Structure (src/)

```
llm_pipeline/ui/frontend/
  .gitignore
  .prettierrc          # semi=false, singleQuote, trailingComma=all, tabWidth=2, printWidth=100
  .prettierignore      # routeTree.gen.ts, dist/
  components.json      # shadcn: new-york, neutral, rsc=false, cssVariables=true, lucide icons
  eslint.config.ts     # ESLint 9 flat: ts-eslint, react-hooks, react-refresh, prettier; ignores routeTree.gen.ts
  index.html           # Entry: title="llm-pipeline", no favicon
  package.json
  tsconfig.json        # Solution file: references app + node, @/* path alias
  tsconfig.app.json    # ES2020, DOM, react-jsx, strict, bundler moduleResolution
  tsconfig.node.json   # ES2023, includes vite.config.ts + eslint.config.ts
  vite.config.ts
  src/
    index.css          # Tailwind v4 CSS-first + shadcn OKLCH tokens + dark mode
    main.tsx           # StrictMode > QueryClientProvider > RouterProvider
    queryClient.ts     # staleTime=30s, retry=2, refetchOnWindowFocus=false
    router.ts          # createRouter(routeTree) + Register augmentation
    routeTree.gen.ts   # Auto-generated, currently only / route
    lib/
      utils.ts         # cn() = clsx + tailwind-merge
    routes/
      __root.tsx       # createRootRoute, bare <Outlet /> (no layout yet)
      index.tsx        # "/" placeholder: "llm-pipeline ui" text
```

No `src/components/` directory. No shadcn components installed yet. No `public/` assets.

## Installed Dependencies

### Production

| Package | Version | Notes |
|---|---|---|
| react | ^19.2.0 | React 19 |
| react-dom | ^19.2.0 | |
| @tanstack/react-router | ^1.161.3 | Installed: 1.161.3 |
| @tanstack/react-query | ^5.90.21 | |
| zustand | ^5.0.11 | |
| tailwindcss | ^4.2.0 | v4 CSS-first, no config file |
| @tailwindcss/vite | ^4.2.0 | Vite plugin replaces postcss/autoprefixer |
| radix-ui | ^1.4.3 | shadcn primitive |
| class-variance-authority | ^0.7.1 | shadcn dep |
| clsx | ^2.1.1 | shadcn dep |
| tailwind-merge | ^3.5.0 | shadcn dep |
| lucide-react | ^0.575.0 | Icon library |

### Dev Dependencies

| Package | Version | Notes |
|---|---|---|
| @tanstack/router-plugin | ^1.161.3 | File-based route generation |
| @tanstack/react-query-devtools | ^5.91.3 | |
| @vitejs/plugin-react | ^5.1.1 | |
| vite | ^7.3.1 | |
| typescript | ~5.9.3 | |
| shadcn | ^3.8.5 | CLI tool for adding components |
| tw-animate-css | ^1.4.0 | Replaces tailwindcss-animate |
| eslint | ^9.39.1 | + typescript-eslint, react-hooks, react-refresh, prettier config |
| prettier | ^3.8.1 | |
| @types/node | ^24.10.1 | |
| @types/react | ^19.2.7 | |
| @types/react-dom | ^19.2.3 | |

### NOT Installed (Needed for Task 30)

| Package | Why Needed |
|---|---|
| `zod` | Search params validation schemas (only transitive dep currently) |
| `@tanstack/zod-adapter` | Connects Zod schemas to TanStack Router's validateSearch |

## Vite Configuration

```typescript
plugins: [tanstackRouter(), react(), tailwindcss()]
```

- TanStack Router plugin runs BEFORE react() (correct order per docs)
- `autoCodeSplitting` NOT enabled (Context7 recommends enabling it)
- Path alias: `@` -> `./src`
- Proxy: `/api` -> `http://localhost:${VITE_API_PORT}`, `/ws` -> WebSocket
- Build output: `dist/`

## TanStack Router Setup

- **File-based routing**: Working. routeTree.gen.ts auto-generated.
- **Router creation**: `src/router.ts` creates router from generated route tree
- **Type registration**: `Register` module augmentation in router.ts
- **Current routes**: Only `__root__` and `/` (index)
- **Root route**: Bare `<Outlet />`, no layout. Task 29 summary explicitly states "layout deferred to task 30."

## Tailwind CSS v4 / Theme

- CSS-first config in `src/index.css`
- `@import "tailwindcss"` + `@import "tw-animate-css"` + `@import "shadcn/tailwind.css"`
- `@custom-variant dark (&:where(.dark, .dark *))` for class-based dark mode
- `@theme inline` maps CSS variables to Tailwind tokens
- Dark mode activated in `main.tsx`: `document.documentElement.classList.add('dark')`
- Full OKLCH color palette in `:root` (light) and `.dark` (dark) selectors
- Sidebar-specific tokens present: `--sidebar`, `--sidebar-foreground`, `--sidebar-primary`, etc.

**Key for task 30**: Use design tokens (`bg-background`, `text-foreground`, `bg-sidebar`, etc.) NOT raw Tailwind gray classes (bg-gray-900, text-gray-100) from task description.

## shadcn/ui Configuration

From `components.json`:
- Style: `new-york`
- Base color: `neutral`
- RSC: `false` (Vite, not Next.js)
- Icon library: `lucide`
- Aliases: `@/components`, `@/components/ui`, `@/lib`, `@/hooks`
- No components installed yet (no `src/components/ui/` directory)

## Entry Point Flow

```
index.html
  -> src/main.tsx
    -> document.documentElement.classList.add('dark')
    -> StrictMode
      -> QueryClientProvider (queryClient)
        -> RouterProvider (router)
          -> routeTree.gen.ts routes
            -> __root.tsx (<Outlet />)
              -> index.tsx (placeholder)
```

## Code Style Conventions (from task 29)

- No semicolons (Prettier: semi=false)
- Single quotes
- Trailing commas everywhere
- 2-space indent
- 100 char print width
- Named function components (not arrow): `function IndexPage() {}`
- `createFileRoute` with path string: `createFileRoute('/')(...)`
- Exports: `export const Route = createFileRoute(...)(...)`

## Route Files Needed (from task 30 description)

| File | URL | Page |
|---|---|---|
| `routes/__root.tsx` | - | Layout shell with Sidebar + Outlet (MODIFY existing) |
| `routes/index.tsx` | `/` | Run List (MODIFY existing placeholder) |
| `routes/runs/$runId.tsx` | `/runs/$runId` | Run Detail (CREATE) |
| `routes/live.tsx` | `/live` | Live Execution (CREATE) |
| `routes/prompts.tsx` | `/prompts` | Prompt Browser (CREATE) |
| `routes/pipelines/index.tsx` | `/pipelines` | Pipeline Structure (CREATE) |

## Dependency Between Tasks 30 and 41

Task 30 __root.tsx layout references `<Sidebar />` but task 41 "Create Sidebar Navigation Component" is downstream (depends on 30 + 32). Task 30 should create a **minimal stub Sidebar** in the layout, and task 41 will replace it with the full implementation.

## Implementation Prerequisites

1. Install `zod` and `@tanstack/zod-adapter` as production dependencies
2. Consider enabling `autoCodeSplitting: true` in tanstackRouter() plugin options
3. Create `routes/runs/` and `routes/pipelines/` subdirectories
4. After creating route files, routeTree.gen.ts will auto-regenerate on `npm run dev`

## Zod Search Params Pattern (from Context7)

```typescript
import { createFileRoute } from '@tanstack/react-router'
import { zodValidator, fallback } from '@tanstack/zod-adapter'
import { z } from 'zod'

const searchSchema = z.object({
  page: fallback(z.number(), 1).default(1),
  filter: fallback(z.string(), 'all').default('all'),
})

export const Route = createFileRoute('/example')({
  validateSearch: zodValidator(searchSchema),
  component: ExamplePage,
})

function ExamplePage() {
  const { page, filter } = Route.useSearch()
  // ...
}
```
