# IMPLEMENTATION - STEP 4: CONFIGURE VITE
**Status:** completed

## Summary
Replaced vite.config.ts with full config: TanStack Router plugin (first), React, Tailwind CSS v4 plugins; path alias `@` -> `./src`; explicit `build.outDir: "dist"`; dev server proxy for `/api` and `/ws` reading `VITE_API_PORT` env var (default 8642); dev server port from `VITE_PORT` (default 5173).

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/vite.config.ts`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/vite.config.ts`
Full replacement of scaffold default with production config.

```
# Before
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
})

# After
import path from 'path'
import { defineConfig } from 'vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const apiPort = process.env.VITE_API_PORT || '8642'
const devPort = Number(process.env.VITE_PORT || '5173')

export default defineConfig({
  plugins: [tanstackRouter(), react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  build: {
    outDir: 'dist',
  },
  server: {
    port: devPort,
    proxy: {
      '/api': {
        target: `http://localhost:${apiPort}`,
        changeOrigin: true,
      },
      '/ws': {
        target: `ws://localhost:${apiPort}`,
        ws: true,
      },
    },
  },
})
```

## Decisions
### TanStack Router export name
**Choice:** `tanstackRouter` (lowercase)
**Rationale:** Verified from `node_modules/@tanstack/router-plugin/dist/esm/vite.d.ts` line 164/257. `TanStackRouterVite` exists but is marked `@deprecated`.

### Plugin ordering
**Choice:** `tanstackRouter()` first, then `react()`, then `tailwindcss()`
**Rationale:** TanStack Router plugin must run before React plugin per TanStack docs (generates route tree before JSX transform). Tailwind order is not critical but placed last by convention.

### WebSocket proxy target protocol
**Choice:** `ws://` protocol for `/ws` proxy target
**Rationale:** Vite proxy requires explicit `ws://` scheme and `ws: true` for WebSocket upgrade handling. `/ws` has no `/api` prefix per app.py line 80.

## Verification
[x] `tanstackRouter` export confirmed in vite.d.ts (line 164, default export line 257)
[x] `TanStackRouterVite` is deprecated (line 210-211)
[x] `tsc --noEmit --project tsconfig.node.json` passes (0 errors)
[x] Plugin order: tanstackRouter -> react -> tailwindcss
[x] Path alias `@` resolves to `./src`
[x] `build.outDir` set to `"dist"`
[x] `/api` proxy targets `http://localhost:${VITE_API_PORT}`
[x] `/ws` proxy targets `ws://localhost:${VITE_API_PORT}` with `ws: true`
[x] Server port reads `VITE_PORT` env var, defaults 5173
