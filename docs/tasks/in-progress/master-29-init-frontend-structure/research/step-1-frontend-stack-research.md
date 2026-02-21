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

---

## Appendix: Cross-Step Validation & Latest Findings (Feb 21, 2026 Re-research)

### 1. Version Confirmation (Live Web/NPM Research)

| Package | Confirmed Version | Source |
|---------|------------------|--------|
| React | 19.2.4 | [npm](https://www.npmjs.com/package/react), [react.dev blog](https://react.dev/blog/2025/10/01/react-19-2) |
| Vite | `npm create vite@latest` scaffolds latest (7.x) | [vite.dev](https://vite.dev/guide/) |
| @tanstack/react-router | 1.161.1 | [npm](https://www.npmjs.com/package/@tanstack/react-router) |
| @tanstack/router-plugin | 1.161.3 | [npm](https://www.npmjs.com/package/@tanstack/router-plugin) |
| TailwindCSS | 4.x stable (since Jan 2025) | [tailwindcss.com](https://tailwindcss.com/blog/tailwindcss-v4) |
| Zustand | 5.0.11 (React 19 compatible) | [npm](https://www.npmjs.com/package/zustand) |
| shadcn/ui CLI | `npx shadcn@latest` (Tailwind v4 + React 19 support) | [ui.shadcn.com](https://ui.shadcn.com/docs/installation/vite) |

### 2. Cross-Reference Corrections (Step-1 vs Step-3)

| Issue | Step-1 | Step-3 | Resolution |
|-------|--------|--------|------------|
| `@tailwindcss/vite` plugin | Included in vite.config.ts | **MISSING** from vite.config.ts | Step-1 is correct. Required for Tailwind v4. Step-3 vite.config.ts must add `tailwindcss()` plugin. |
| Vite version | Lists 7.3.1, recommends latest | Says pin to ^6.0.0 per contract | Use latest (`npm create vite@latest`). Vite 7 is backward-compatible. Note deviation from task description. |
| `@theme` vs `@theme inline` | Uses `@theme` | Not covered | shadcn/ui Tailwind v4 uses `@theme inline`. See section 3. |

### 3. shadcn/ui + Tailwind v4 CSS Structure (Updated)

When `npx shadcn@latest init` runs on a Tailwind v4 project, it generates CSS using OKLCH colors and the `@theme inline` directive. The actual generated CSS structure:

```css
@import "tailwindcss";
@import "tw-animate-css";

@custom-variant dark (&:where(.dark, .dark *));

:root {
  --background: oklch(1 0 0);
  --foreground: oklch(0.145 0 0);
  --card: oklch(1 0 0);
  --card-foreground: oklch(0.145 0 0);
  --primary: oklch(0.205 0 0);
  --primary-foreground: oklch(0.985 0 0);
  --secondary: oklch(0.97 0 0);
  --secondary-foreground: oklch(0.205 0 0);
  --muted: oklch(0.97 0 0);
  --muted-foreground: oklch(0.556 0 0);
  --accent: oklch(0.97 0 0);
  --accent-foreground: oklch(0.205 0 0);
  --destructive: oklch(0.577 0.245 27.325);
  --border: oklch(0.922 0 0);
  --input: oklch(0.922 0 0);
  --ring: oklch(0.708 0 0);
  --radius: 0.625rem;
  /* ... more variables */
}

.dark {
  --background: oklch(0.145 0 0);
  --foreground: oklch(0.985 0 0);
  --card: oklch(0.145 0 0);
  --card-foreground: oklch(0.985 0 0);
  --primary: oklch(0.985 0 0);
  --primary-foreground: oklch(0.205 0 0);
  --secondary: oklch(0.269 0 0);
  --secondary-foreground: oklch(0.985 0 0);
  --muted: oklch(0.269 0 0);
  --muted-foreground: oklch(0.708 0 0);
  --accent: oklch(0.269 0 0);
  --accent-foreground: oklch(0.985 0 0);
  --destructive: oklch(0.396 0.141 25.723);
  --border: oklch(0.269 0 0);
  --input: oklch(0.269 0 0);
  --ring: oklch(0.439 0 0);
  /* ... more variables */
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-ring: var(--ring);
  --radius-sm: calc(var(--radius) - 0.125rem);
  --radius-md: var(--radius);
  --radius-lg: calc(var(--radius) + 0.125rem);
  --radius-xl: calc(var(--radius) + 0.25rem);
  /* ... more mappings */
}
```

Key points:
- **OKLCH** replaces HSL (better perceptual uniformity, wider gamut)
- **`@theme inline`** maps CSS variables to Tailwind utilities WITHOUT creating standalone `--tw-*` custom properties
- **`:root`** and **`.dark`** define the actual color values outside `@theme`
- **`tw-animate-css`** replaces deprecated `tailwindcss-animate`
- **`@custom-variant dark`** enables class-based dark mode (`.dark` on `<html>`)
- Custom status colors (from step-1 `@theme` block) should be added INSIDE the `@theme inline` block after shadcn init

### 4. Corrected Implementation Order

1. `npm create vite@latest . -- --template react-ts` (scaffold)
2. `npm install` core deps (react, react-dom, @tanstack/react-router, @tanstack/react-query, zustand)
3. `npm install tailwindcss @tailwindcss/vite` (Tailwind v4)
4. `npm install -D @tanstack/router-plugin @types/node`
5. Configure `tsconfig.json` + `tsconfig.app.json` (add path aliases)
6. Configure `vite.config.ts` (tanstackRouter + tailwindcss + react plugins, proxy, aliases)
7. Replace `src/index.css` with `@import "tailwindcss";`
8. **`npx shadcn@latest init`** (creates CSS variables, components.json, lib/utils.ts -- MODIFIES index.css)
9. Add custom status color tokens to the `@theme inline` block in `src/index.css`
10. Add `class="dark"` to `<html>` in `index.html`
11. Create `src/routes/__root.tsx` and `src/routes/index.tsx`
12. Replace `src/main.tsx` with router + query providers

Step 8 (shadcn init) must come AFTER steps 5-7 because it expects the Tailwind/Vite/path setup to already exist. Custom tokens (step 9) must come AFTER shadcn init to avoid being overwritten.

### 5. TanStack Router Plugin API (Context7 Confirmed)

```typescript
// CORRECT (current API)
import { tanstackRouter } from '@tanstack/router-plugin/vite'

// WRONG (deprecated, from older docs / task 29 description)
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
```

Config options confirmed:
- `target: 'react'` -- required for React projects
- `autoCodeSplitting: true` -- recommended, enables lazy route loading
- Plugin must be listed BEFORE `react()` in Vite plugins array

### 6. shadcn/ui Key Changes for Tailwind v4

| Change | Old (v3) | New (v4) |
|--------|----------|----------|
| Animation lib | `tailwindcss-animate` | `tw-animate-css` |
| Color format | HSL `hsl(0 0% 100%)` | OKLCH `oklch(1 0 0)` |
| Theme config | `tailwind.config.ts` extend | `@theme inline` in CSS |
| Component refs | `React.forwardRef` | Direct props `React.ComponentProps<>` |
| Element IDs | None | `data-slot` attribute on all primitives |
| Config file | `tailwind.config.ts` | CSS-only (no config file) |

### 7. Additional Dependencies (shadcn/ui + Tailwind v4)

shadcn init installs these automatically:
- `tw-animate-css` (animation CSS)
- `class-variance-authority` (variant management)
- `clsx` (conditional classes)
- `tailwind-merge` (class merging)
- `lucide-react` (icon library, if selected)

### Sources (Additional)

- [shadcn/ui Tailwind v4 migration](https://ui.shadcn.com/docs/tailwind-v4)
- [shadcn/ui Vite installation (latest)](https://ui.shadcn.com/docs/installation/vite)
- [Tailwind CSS v4 dark mode](https://tailwindcss.com/docs/dark-mode)
- [Tailwind CSS v4 upgrade guide](https://tailwindcss.com/docs/upgrade-guide)
- [TanStack Router releases](https://github.com/TanStack/router/releases)
- [Zustand npm](https://www.npmjs.com/package/zustand)

---

## Appendix B: Context7 Documentation Validation (Feb 21, 2026 - Agent Re-research)

### 1. Context7 Sources Queried

| Library | Context7 ID | Version | Snippet Count |
|---------|-------------|---------|---------------|
| Vite | /vitejs/vite | v7.0.0 | 867 |
| TanStack Router | /tanstack/router | v1.114.3 | 2634 |
| shadcn/ui | /shadcn-ui/ui | shadcn@3.2.1 | 1025 |

### 2. TanStack Router Import Name - Evidence from Context7

Context7 v1.114.3 docs show **multiple import patterns** depending on package:

```typescript
// Pattern A: @tanstack/router-vite-plugin (DEPRECATED compat package)
import TanStackRouterVitePlugin from '@tanstack/router-vite-plugin'

// Pattern B: @tanstack/router-plugin/vite (CURRENT recommended package)
// v1.114.3 docs show:
import { TanStackRouterVite } from '@tanstack/router-plugin/vite'
```

However, the existing step-1 research (and web search results) indicate that in versions >= 1.150.x, the export was renamed to `tanstackRouter` (lowercase). Context7 only has v1.114.3, which predates this rename.

**Resolution for implementation:**
- Install `@tanstack/router-plugin` (NOT `@tanstack/router-vite-plugin`)
- At implementation time, verify the actual export name by checking `node_modules/@tanstack/router-plugin/dist/vite.d.ts`
- If `tanstackRouter` is not found, fall back to `TanStackRouterVite`
- The plugin functionality is identical regardless of export name

### 3. Vite v7 Proxy Configuration (Context7 Confirmed)

Context7 Vite v7.0.0 docs confirm the proxy configuration pattern:

```typescript
server: {
  proxy: {
    '/ws': {
      target: 'ws://localhost:3000',
      ws: true,  // enables WebSocket upgrade handling
    },
  },
}
```

This matches the existing step-1 proxy config exactly. No changes needed.

Additionally confirmed: for `middlewareMode` with WebSocket proxying, the parent HTTP server must be provided. This is NOT relevant to our setup (we use standalone Vite dev server, not middleware mode).

### 4. shadcn/ui Vite Setup (Context7 Confirmed)

Context7 shadcn@3.2.1 docs confirm:

1. **Tailwind CSS installation**: `npm install tailwindcss @tailwindcss/vite` (matches step-1)
2. **Vite config**: Requires `tailwindcss()` plugin from `@tailwindcss/vite` + `react()` + path alias (matches step-1)
3. **CSS**: `@import "tailwindcss"` single import (matches step-1)
4. **Init command**: `npx shadcn@latest init` (matches step-1)
5. **components.json**: Generated with `rsc: false` for Vite projects (matches step-1)

### 5. shadcn/ui ThemeProvider Pattern (Out of Scope - Task 42 Reference)

Context7 docs provide a complete ThemeProvider implementation for Vite+React dark mode:
- React context + `useEffect` + `localStorage` persistence
- Supports `"dark" | "light" | "system"` themes
- Adds/removes `.dark` class on `document.documentElement`
- Uses `window.matchMedia("(prefers-color-scheme: dark)")` for system detection

This pattern is relevant to task 42 (dark mode theme), NOT task 29. Noted here for downstream awareness. Task 29 only needs `class="dark"` on `<html>` in `index.html`.

### 6. Cross-Step Consistency Issues Identified

| Issue | Location | Correction |
|-------|----------|------------|
| Step-3 says pyproject.toml "already has" `[tool.hatch.build.targets.wheel.shared-data]` | Step-3 section 7 | WRONG. Step-2 correctly identifies `artifacts` as the right approach. `shared-data` was never implemented. |
| Step-3 says "pin to ^6.0.0 per contract" for Vite | Step-3 section 8 | OUTDATED. Step-1 appendix resolves: use `npm create vite@latest` (scaffolds Vite 7). Vite 7 is backward-compatible. |
| Step-3 missing `@tailwindcss/vite` plugin in vite.config.ts | Step-3 section 2 | Step-1 appendix already flags this. Step-3 vite.config.ts must include `tailwindcss()` plugin. |

These are cross-reference notes only. Step-3 content itself is not modified here.

### 7. TanStack Router File-Based Routing Config (Context7 Full Reference)

Context7 v1.114.3 provides complete config option enumeration. Key defaults already matching step-1:

| Option | Default | Step-1 Value | Match |
|--------|---------|-------------|-------|
| routesDirectory | `"./src/routes"` | `"./src/routes"` | YES |
| generatedRouteTree | `"./src/routeTree.gen.ts"` | `"./src/routeTree.gen.ts"` | YES |
| routeFileIgnorePrefix | `"-"` | `"-"` | YES |
| autoCodeSplitting | undefined | `true` (explicitly set) | OK - explicit enable |
| quoteStyle | `"single"` | Not set (uses default) | OK |
| semicolons | `false` | Not set (uses default) | OK |

Additional options available but not needed for task 29:
- `virtualRouteConfig` - for programmatic route definitions (not using)
- `routeFileIgnorePattern` - regex-based ignore (default `-` prefix sufficient)
- `indexToken` / `routeToken` - defaults match expected behavior
- `disableManifestGeneration` - keep default (generates manifest)

### 8. Implementation Readiness Assessment

All research across steps 1-3 is consistent (with noted corrections above). No CEO input needed. The implementation phase can proceed with:

1. **Scaffold**: `npm create vite@latest . -- --template react-ts` in `llm_pipeline/ui/frontend/`
2. **Dependencies**: As documented in step-1 section "Step 2: Install Dependencies"
3. **Config**: vite.config.ts, tsconfig.json, tsconfig.node.json per steps 1+3
4. **shadcn init**: `npx shadcn@latest init` after Tailwind/Vite configured
5. **Routes**: `__root.tsx` + `index.tsx` minimal stubs
6. **Entry point**: `main.tsx` with Router + Query providers
7. **pyproject.toml**: Add `artifacts` + `exclude` per step-2 findings

### Context7 Sources

- Context7 /vitejs/vite v7.0.0 - Proxy config, createServer API, build function
- Context7 /tanstack/router v1.114.3 - File-based routing config, Vite plugin setup, route tree generation
- Context7 /shadcn-ui/ui shadcn@3.2.1 - Vite installation, Tailwind v4 setup, ThemeProvider pattern, dark mode
