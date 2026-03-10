# Step 1: Vite Production Build Research

## Current State

### Existing vite.config.ts
- Plugins: `tanstackRouter({ autoCodeSplitting: true })`, `react()`, `tailwindcss()`
- `build.outDir`: `'dist'` (already configured)
- No `emptyOutDir`, `sourcemap`, `rollupOptions`, or `build.target` specified
- Dev server proxy configured for `/api` and `/ws`
- Path alias `@` -> `./src`

### Existing package.json Scripts
- `"build": "tsc -b && vite build"` -- already exists, matches task spec
- `"build:analyze"` -- NOT present, task spec requires it
- `"preview": "vite preview"` -- exists for local production preview

### Existing Hatch Build Config (pyproject.toml)
- `artifacts = ["llm_pipeline/ui/frontend/dist/**"]` -- dist included in wheel
- Source files (src/, node_modules/, config files) excluded from wheel
- No changes needed to pyproject.toml for build integration

### TypeScript Build
- `tsconfig.app.json` has `noEmit: true` -- `tsc -b` does type-checking only
- Target: ES2020, module: ESNext, bundler moduleResolution
- Strict mode enabled with all lint flags

## Production Dependencies (Bundle Impact)

| Package | Approx Min Size | Tree-Shakeable | Notes |
|---------|----------------|----------------|-------|
| react + react-dom 19.2 | ~140KB | No (runtime) | Must be in vendor chunk |
| @tanstack/react-router 1.161 | ~50-80KB | Partial | Core router runtime |
| @tanstack/react-query 5.90 | ~40-50KB | Yes | Data fetching layer |
| radix-ui 1.4.3 | ~30-50KB used | Yes | Unified package; only imports: Slot, Label, Checkbox, ScrollArea, Separator, Dialog, Select, Tabs, Tooltip |
| lucide-react 0.575 | ~5KB used | Yes | Only ~10 icons imported individually |
| zod 4.3 | ~15-20KB | Yes | Used by router zod-adapter + forms |
| zustand 5.0 | ~3KB | Yes | Tiny state management |
| class-variance-authority 0.7 | ~3KB | Yes | CVA for component variants |
| tailwind-merge 3.5 | ~5KB | Yes | Runtime class merging |
| clsx 2.1 | ~300B | Yes | Tiny utility |
| microdiff 1.5 | ~1KB | Yes | JSON diff |
| @fontsource-variable/jetbrains-mono | 0KB JS | N/A | CSS + woff2 assets only |
| tailwindcss 4.2 | 0KB JS | N/A | Build-time only via @tailwindcss/vite |
| tw-animate-css | 0KB JS | N/A | CSS only, imported via @import |

**Estimated total JS (minified, pre-gzip): ~290-360KB**
**Estimated gzip: ~90-120KB** (well under 500KB target)

## Recommended Vite Build Configuration

### build Options

```typescript
build: {
  outDir: 'dist',
  emptyOutDir: true,
  sourcemap: false,
  rollupOptions: {
    output: {
      manualChunks: {
        vendor: ['react', 'react-dom'],
        router: ['@tanstack/react-router'],
        query: ['@tanstack/react-query'],
      },
    },
  },
}
```

### Option Rationale

| Option | Value | Rationale |
|--------|-------|-----------|
| `outDir` | `'dist'` | Already set; matches pyproject.toml artifacts path |
| `emptyOutDir` | `true` | Vite default when outDir inside root; explicit for clarity |
| `sourcemap` | `false` | Default; no error tracking service in scope. Use `'hidden'` if Sentry/similar added later |
| `build.target` | (default) | `['chrome107', 'edge107', 'firefox104', 'safari16']` -- adequate for dev tool dashboard |
| `build.minify` | (default `'esbuild'`) | Fast, sufficient minification; terser not needed |
| `build.cssCodeSplit` | (default `true`) | Correct for route-based CSS loading |
| `chunkSizeWarningLimit` | (default `500`) | 500KB uncompressed per chunk; reasonable |

## Manual Chunk Splitting Strategy

### Three-Chunk Approach (from task spec)

1. **vendor** (`react`, `react-dom`): React runtime. Loaded on every page. Changes rarely (only on React version bumps). Excellent long-term cache hit rate.

2. **router** (`@tanstack/react-router`): Router runtime. Loaded on every page (needed for navigation). Separate from vendor because it updates more frequently than React.

3. **query** (`@tanstack/react-query`): Data fetching layer. Loaded on every page (QueryClientProvider in main.tsx). Separate chunk allows independent cache invalidation on version bumps.

### Interaction with autoCodeSplitting

TanStack Router's `autoCodeSplitting: true` plugin operates at the **route level** -- it splits each route file into critical (component) and non-critical (loader, beforeLoad, etc.) chunks. The `manualChunks` config operates at the **library level** -- grouping vendor packages into named chunks.

These two mechanisms are **complementary, not conflicting**:
- autoCodeSplitting: `/routes/live.tsx` -> lazy-loaded chunk on navigation
- manualChunks: `react` + `react-dom` -> `vendor-[hash].js` shared chunk

**Result**: Initial page load fetches `vendor.js` + `router.js` + `query.js` + active route chunk. Other routes lazy-load on navigation.

### Packages NOT Given Dedicated Chunks (and why)

| Package | Reason |
|---------|--------|
| `radix-ui` | Tree-shaken to only used primitives; shared across routes, will naturally land in common chunk |
| `lucide-react` | ~5KB after tree-shaking; too small for dedicated chunk |
| `zod` | ~15-20KB; used by router adapter so likely bundled with router chunk naturally |
| `zustand` | ~3KB; negligible overhead |

## Tree-Shaking and Dead Code Elimination

### Already Working
- Vite uses Rollup for production builds; Rollup has excellent tree-shaking
- `radix-ui` unified package uses sub-path exports -- unused primitives eliminated
- `lucide-react` uses named exports per icon -- unused icons eliminated
- `@tanstack/react-query-devtools` is already dev-only via `import.meta.env.DEV` guard in `main.tsx` -- completely eliminated in production build
- `tailwindcss` and `tw-animate-css` are CSS-only/build-time -- zero JS in output

### Vite/Rollup Default Behavior
- `build.minify: 'esbuild'` removes dead code, minifies identifiers
- ES module format enables static analysis for tree-shaking
- `tsconfig.app.json` uses `verbatimModuleSyntax: true` -- ensures type-only imports are properly erased

### No Additional Configuration Needed
Tree-shaking works out of the box with the current setup. No `sideEffects` overrides or custom Rollup plugins required.

## Asset Hashing (Cache Busting)

### Vite Default Behavior
- All output files use content-based hashing: `[name]-[hash].js`, `[name]-[hash].css`
- Hash changes when file content changes, busting browser cache
- `index.html` is NOT hashed (entry point, served with no-cache headers)
- Font files (woff2) are hashed and placed in `assets/` subdirectory
- Images/static assets are hashed

### Default Output Structure
```
dist/
  index.html
  assets/
    vendor-abc123.js
    router-def456.js
    query-ghi789.js
    index-jkl012.js          (app entry)
    [route]-mno345.js         (lazy route chunks)
    index-pqr678.css          (main CSS)
    [route]-stu901.css         (route CSS if cssCodeSplit)
    jetbrains-mono-*.woff2    (font files)
```

### No Custom Configuration Needed
Vite's default `build.assetsDir: 'assets'` and content hashing are optimal. No need to customize `rollupOptions.output.entryFileNames`, `chunkFileNames`, or `assetFileNames`.

## Plugins Assessment

### Existing Plugins (Keep All)
1. **`tanstackRouter({ autoCodeSplitting: true })`** -- Route generation + route-level code splitting
2. **`react()`** -- JSX transform, React Fast Refresh (dev only)
3. **`@tailwindcss/vite`** -- Tailwind CSS v4 processing

### Recommended Addition: rollup-plugin-visualizer (devDependency)
For the `build:analyze` script from task spec:

```bash
npm install -D rollup-plugin-visualizer
```

Conditional activation in vite.config.ts:
```typescript
import { visualizer } from 'rollup-plugin-visualizer'

// In plugins array, conditionally:
...(process.env.ANALYZE ? [visualizer({ open: true, gzipSize: true })] : [])
```

Or use Vite's `mode` parameter:
```typescript
export default defineConfig(({ mode }) => ({
  plugins: [
    tanstackRouter({ autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    ...(mode === 'analyze' ? [visualizer({ open: true, gzipSize: true, filename: 'dist/stats.html' })] : []),
  ],
  // ...
}))
```

### Not Recommended
| Plugin | Reason |
|--------|--------|
| `vite-plugin-compression` | Gzip/Brotli should be handled by server (FastAPI GZipMiddleware or reverse proxy), not build-time pre-compression |
| `@rollup/plugin-terser` | esbuild minification is sufficient and faster |
| `vite-plugin-pwa` | No PWA requirements in scope |
| `vite-plugin-legacy` | Modern browser targets sufficient for dev tool |

## Build Script Changes

### Current (package.json)
```json
"build": "tsc -b && vite build",
"preview": "vite preview"
```

### Additions Needed
```json
"build:analyze": "vite build --mode analyze"
```

The `build` script is already correct. Only `build:analyze` needs to be added.

## Summary of Changes Required

### vite.config.ts
1. Add `emptyOutDir: true` to build config (explicit)
2. Add `rollupOptions.output.manualChunks` with vendor/router/query
3. Convert to function form `defineConfig(({ mode }) => ...)` if adding visualizer plugin
4. Conditionally add `rollup-plugin-visualizer` in analyze mode

### package.json
1. Add `"build:analyze": "vite build --mode analyze"` to scripts
2. Add `rollup-plugin-visualizer` to devDependencies (if adding analyze support)

### No Changes Needed
- `pyproject.toml` -- artifacts config already correct
- `tsconfig.json` / `tsconfig.app.json` -- already optimal
- `index.html` -- no changes
- Existing plugins -- all kept, none removed
- `build.sourcemap` -- false (default) is appropriate
- `build.target` -- default modern browsers is appropriate
