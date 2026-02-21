# Step 1: Frontend Stack Research

## Current Stable Versions (Feb 2026)

| Package | Version | Notes |
|---------|---------|-------|
| React | 19.2.4 | Stable since Dec 2024, 19.2.x since Oct 2025 |
| ReactDOM | 19.2.4 | Paired with React |
| Vite | 7.3.1 | Stable; dropped Node 18 (EOL Apr 2025); requires Node 20+ |
| TypeScript | 5.7.x | Latest stable |
| TailwindCSS | 4.2.0 | CSS-first config, no tailwind.config.js/ts needed |
| @tailwindcss/vite | 4.2.0 | First-party Vite plugin (replaces postcss/autoprefixer) |
| @tanstack/react-router | 1.161.1 | File-based routing, type-safe |
| @tanstack/router-plugin | 1.161.1 | Vite plugin for route tree generation |
| @tanstack/react-query | 5.x | Server state management |
| Zustand | 5.x | Client state management |
| shadcn/ui | latest CLI | Installed via `npx shadcn@latest init`, NOT an npm dependency |
| @vitejs/plugin-react | latest | React Fast Refresh for Vite |

## Deviations from Task 29 Description

Task 29 was written before several major releases. The following corrections are needed:

| Task Description Says | Actual Current Best Practice | Impact |
|----------------------|----------------------------|--------|
| Vite 6.x | Vite 7.3.1 (6.x is outdated) | Use `npm create vite@latest` which scaffolds with Vite 7 |
| `npm install @shadcn/ui` | `npx shadcn@latest init` (CLI tool, not npm dep) | shadcn/ui components are copied into project, not imported from node_modules |
| `TanStackRouterVite` import | `tanstackRouter` (lowercase) from `@tanstack/router-plugin/vite` | Import name changed in recent versions |
| `npm install tailwindcss postcss autoprefixer` | `npm install tailwindcss @tailwindcss/vite` | Tailwind v4 uses first-party Vite plugin, no postcss/autoprefixer needed |
| `tailwind.config.ts` with JS object | CSS-first `@theme` directive in CSS file | Tailwind v4 eliminated config file; all config in CSS |
| `@tailwind base; @tailwind components; @tailwind utilities;` | `@import "tailwindcss";` | Single import replaces three directives in v4 |

## Project Initialization

### Step 1: Scaffold Vite Project

```bash
cd llm_pipeline/ui/frontend
npm create vite@latest . -- --template react-ts
```

This creates: `package.json`, `vite.config.ts`, `tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`, `index.html`, `src/main.tsx`, `src/App.tsx`, etc.

### Step 2: Install Dependencies

```bash
# Core
npm install react@^19.2.0 react-dom@^19.2.0
npm install @tanstack/react-router @tanstack/react-query zustand

# Tailwind v4
npm install tailwindcss @tailwindcss/vite

# Dev
npm install -D @tanstack/router-plugin @types/node typescript
```

### Step 3: Configure TypeScript Paths

**tsconfig.json** - Add `compilerOptions` with path aliases:
```json
{
  "files": [],
  "references": [
    { "path": "./tsconfig.app.json" },
    { "path": "./tsconfig.node.json" }
  ],
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

**tsconfig.app.json** - Also add paths:
```json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    }
  }
}
```

### Step 4: Configure Vite

```typescript
import path from "path"
import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import { tanstackRouter } from "@tanstack/router-plugin/vite"

export default defineConfig({
  plugins: [
    // TanStack Router MUST be before react()
    tanstackRouter({
      target: "react",
      autoCodeSplitting: true,
    }),
    tailwindcss(),
    react(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8642",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8642",
        ws: true,
      },
    },
  },
  build: {
    outDir: "dist",
  },
})
```

Key notes:
- `tanstackRouter` plugin MUST come before `react()` plugin
- No proxy rewrite needed for `/api` since backend already prefixes routes with `/api`
- WebSocket proxy at `/ws` matches backend's `ws_router` (no `/api` prefix per `app.py` line 80)
- `outDir: "dist"` matches what `cli.py` expects (line 64: `frontend/dist`)

### Step 5: Initialize shadcn/ui

```bash
npx shadcn@latest init
```

Interactive prompts will ask for:
- Style (recommend: "new-york" or "default")
- Base color (recommend: "neutral" or "zinc" for dark-first design)
- CSS variables: Yes

This creates `components.json`:
```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/index.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

Key: `rsc: false` since this is a client-side Vite app, not Next.js.

### Step 6: Set Up CSS (Tailwind v4 + Dark Mode)

**src/index.css:**
```css
@import "tailwindcss";

@custom-variant dark (&:where(.dark, .dark *));

@theme {
  --color-status-pending: oklch(0.71 0.01 261);
  --color-status-running: oklch(0.62 0.21 255);
  --color-status-completed: oklch(0.72 0.19 150);
  --color-status-failed: oklch(0.63 0.24 25);
  --color-status-skipped: oklch(0.80 0.15 85);
  --color-status-cached: oklch(0.65 0.18 293);
}
```

Notes:
- `@import "tailwindcss"` replaces old `@tailwind base/components/utilities` directives
- `@custom-variant dark` enables class-based dark mode (`.dark` class on html)
- `@theme` defines custom design tokens available as Tailwind utilities (e.g. `bg-status-running`)
- Status colors defined here but detailed theming is task 42 scope (OUT OF SCOPE for task 29)
- Dark class applied to `<html>` in `index.html` by default

**index.html** (add dark class):
```html
<html lang="en" class="dark">
```

## TanStack Router File-Based Routing

### Route Structure

Default config generates routes from `src/routes/`:
- `src/routes/__root.tsx` - Root layout (wraps all routes)
- `src/routes/index.tsx` - Home route at `/`
- Auto-generates `src/routeTree.gen.ts`

### Configuration Defaults

```json
{
  "routesDirectory": "./src/routes",
  "generatedRouteTree": "./src/routeTree.gen.ts",
  "routeFileIgnorePrefix": "-",
  "quoteStyle": "single",
  "autoCodeSplitting": true
}
```

### Generated File Handling

`routeTree.gen.ts` should be:
- Git committed (needed for builds)
- Ignored by linters/formatters (add to `.prettierignore`, `.eslintignore`)
- Marked readonly in VSCode settings

### Main Entry Point Pattern

```tsx
// src/main.tsx
import React from "react"
import ReactDOM from "react-dom/client"
import { RouterProvider, createRouter } from "@tanstack/react-router"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { routeTree } from "./routeTree.gen"
import "./index.css"

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30,
      refetchOnWindowFocus: true,
    },
  },
})

const router = createRouter({ routeTree })

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router
  }
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>
)
```

## Zustand Setup Pattern

```typescript
// src/stores/example.ts
import { create } from "zustand"

interface ExampleState {
  count: number
  increment: () => void
}

export const useExampleStore = create<ExampleState>()((set) => ({
  count: 0,
  increment: () => set((state) => ({ count: state.count + 1 })),
}))
```

Zustand v5 uses `create<T>()((set) => ...)` pattern (double parentheses for TypeScript inference).

## Directory Structure

```
llm_pipeline/ui/frontend/
  index.html
  package.json
  vite.config.ts
  tsconfig.json
  tsconfig.app.json
  tsconfig.node.json
  components.json          # shadcn/ui config
  .prettierignore          # ignore routeTree.gen.ts
  src/
    main.tsx               # entry point with providers
    index.css              # Tailwind v4 imports + @theme
    routeTree.gen.ts       # auto-generated by TanStack Router plugin
    routes/
      __root.tsx           # root layout
      index.tsx            # home route "/"
    components/
      ui/                  # shadcn/ui components (added via CLI)
    lib/
      utils.ts             # shadcn cn() utility
    hooks/                 # custom React hooks
    stores/                # Zustand stores
```

## Integration with Python Package

### Existing CLI Support

`llm_pipeline/ui/cli.py` already handles:
- **Dev mode** (`--dev`): Starts Vite dev server as subprocess + FastAPI (lines 76-101)
- **Prod mode**: Mounts `frontend/dist/` as static files via Starlette (lines 59-73)
- **No frontend**: Falls back to API-only mode (lines 84-89)

### Build Integration

The CLI's `_start_vite` function (line 151) runs `npx vite --port <port>` from the `frontend_dir`. The `vite.config.ts` proxy ensures API calls are forwarded to FastAPI during development.

For production, `npm run build` produces `frontend/dist/` which `cli.py` serves via `StaticFiles(directory=str(dist_dir), html=True)`.

### .gitignore Additions Needed

```
llm_pipeline/ui/frontend/node_modules/
llm_pipeline/ui/frontend/dist/
```

### Hatch Build Exclusion

Task 28 summary recommends adding `[tool.hatch.build]` exclusion for `frontend/dist/` and `node_modules/` once frontend exists. This should be addressed in implementation.

## Proxy Configuration Details

| Path | Target | Type | Notes |
|------|--------|------|-------|
| `/api` | `http://localhost:8642` | HTTP | No rewrite; backend routes already have `/api` prefix |
| `/ws` | `ws://localhost:8642` | WebSocket | Backend mounts ws_router without `/api` prefix |

The proxy only applies during `npm run dev` (Vite dev server). In production, FastAPI serves both the API and the SPA from the same origin.

## Sources

- [React v19.2 release](https://react.dev/blog/2025/10/01/react-19-2)
- [Vite releases](https://vite.dev/releases)
- [Tailwind CSS v4.0 announcement](https://tailwindcss.com/blog/tailwindcss-v4)
- [shadcn/ui Vite installation](https://ui.shadcn.com/docs/installation/vite)
- [shadcn/ui Tailwind v4 guide](https://ui.shadcn.com/docs/tailwind-v4)
- [TanStack Router Vite installation](https://tanstack.com/router/latest/docs/framework/react/installation/with-vite)
- [TanStack Router file-based routing](https://tanstack.com/router/latest/docs/how-to/install)
- [Zustand v5 TypeScript guide](https://github.com/pmndrs/zustand/blob/main/docs/guides/beginner-typescript.md)
