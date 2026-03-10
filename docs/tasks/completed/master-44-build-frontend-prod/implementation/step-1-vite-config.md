# IMPLEMENTATION - STEP 1: VITE CONFIG
**Status:** completed

## Summary
Configured vite.config.ts for optimized production builds: function-form defineConfig, emptyOutDir, sourcemap disabled, three vendor chunks (vendor/router/query) via function-form manualChunks, and conditional rollup-plugin-visualizer. Fixed vitest.config.ts compatibility with function-form export.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/vite.config.ts, llm_pipeline/ui/frontend/vitest.config.ts
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/vite.config.ts`
Converted to function-form defineConfig, added visualizer import, production build settings, and manualChunks.

```
# Before
export default defineConfig({
  plugins: [tanstackRouter({ autoCodeSplitting: true }), react(), tailwindcss()],
  build: {
    outDir: 'dist',
  },
  ...
})

# After
export default defineConfig(({ mode: _mode }) => ({
  plugins: [
    tanstackRouter({ autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    ...(process.env.ANALYZE === 'true' ? [visualizer({...})] : []),
  ],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react-dom/') || id.includes('node_modules/react/')) return 'vendor'
          if (id.includes('node_modules/@tanstack/react-router')) return 'router'
          if (id.includes('node_modules/@tanstack/react-query')) return 'query'
        },
      },
    },
  },
  ...
}))
```

### File: `llm_pipeline/ui/frontend/vitest.config.ts`
Removed mergeConfig(viteConfig, ...) pattern (incompatible with function-form vite export). Standalone defineConfig with resolve.alias duplicated.

```
# Before
import { defineConfig, mergeConfig } from 'vitest/config'
import viteConfig from './vite.config'
export default mergeConfig(viteConfig, defineConfig({...}))

# After
import path from 'path'
import { defineConfig } from 'vitest/config'
export default defineConfig({
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  test: { ... },
})
```

## Decisions
### Function-form manualChunks instead of object-form
**Choice:** Used `manualChunks(id)` function matching on `node_modules/` paths instead of object-form `{ vendor: ['react', 'react-dom'] }`
**Rationale:** Object-form produced empty vendor chunk with Vite 7 / Rolldown bundler. Rolldown's module concatenation inlines universally-imported modules (react, react-dom) into entry chunk when using object-form. Function-form matching on module path reliably splits all three chunks.

### rollupOptions instead of rolldownOptions
**Choice:** Used `build.rollupOptions` instead of `build.rolldownOptions`
**Rationale:** Vite 7 Context7 docs show `rolldownOptions` as canonical, but testing showed `rolldownOptions.output.manualChunks` was silently ignored (no chunk splitting occurred). `rollupOptions` is the backward-compatible alias that Vite 7.3.1 still processes for output.manualChunks. Confirmed working with actual build output.

### mode parameter as _mode
**Choice:** `({ mode: _mode })` instead of `({ mode })`
**Rationale:** tsconfig.node.json has `noUnusedParameters: true`. Underscore prefix is idiomatic TS convention for intentionally unused params. Preserves parameter for future conditional config.

### vitest.config.ts standalone with duplicated alias
**Choice:** Removed viteConfig import from vitest.config.ts, duplicated resolve.alias
**Rationale:** Function-form vite.config.ts export is incompatible with vitest's `mergeConfig()` first argument (expects UserConfig object, not function). Vitest does not auto-merge vite.config.ts when vitest.config.ts is present. Alias duplication is minimal (2 lines) and avoids complex workarounds.

## Verification
[x] `npm run build` completes without errors
[x] Three vendor chunks visible: vendor (60.53KB gz), router (27.29KB gz), query (11.41KB gz)
[x] No .map files in dist/
[x] dist/index.html exists
[x] `sourcemap: false` confirmed
[x] `emptyOutDir: true` set
[x] Visualizer plugin conditionally included (ANALYZE env var)
[x] All existing plugins preserved (tanstackRouter, react, tailwindcss)
[x] resolve.alias preserved
[x] server.proxy preserved
[x] Type-check passes (`tsc -b --noEmit`)
[x] Tests pass (8/9 suites; 1 pre-existing StatusBadge failure unrelated)
[x] Total bundle gzip well under 500KB target
