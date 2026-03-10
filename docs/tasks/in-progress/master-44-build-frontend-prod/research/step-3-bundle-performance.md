# Step 3: Bundle Size Optimization & Performance Verification

## 1. Current Build Baseline (Measured)

Build command: `tsc -b && vite build` (Vite 7.3.1)
Build time: 7.36s, 2112 modules transformed

### Gzip Size Breakdown

| Category | Raw (KB) | Gzip (KB) |
|----------|----------|-----------|
| Main JS bundle (index-Dayn6vbJ.js) | 483.62 | 152.77 |
| Route chunks (15 files, code-split) | ~130 | 43.47 |
| CSS (index-DLXA3C0D.css) | 60.72 | 13.26 |
| HTML (index.html) | 0.71 | 0.41 |
| **Total (JS + CSS + HTML)** | **~675** | **209.91** |

Font files (woff2, already compressed): 84.21 KB raw -- not gzip-compressible, excluded from bundle budget.

### NFR-009 Compliance

| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Total gzip (JS+CSS+HTML) | 209.91 KB | 500 KB | PASS (58% headroom) |
| Initial load (main+CSS+HTML) | 166.44 KB | -- | Good |

**The 500KB gzip target is easily met with 290 KB headroom.** No aggressive optimization required.

## 2. Code Splitting Status (Already Active)

TanStack Router `autoCodeSplitting: true` is enabled in `vite.config.ts`. Routes are automatically code-split:

| Route Chunk | Gzip (KB) | Content |
|-------------|-----------|---------|
| live.js | 5.77 | Live pipeline page |
| prompts.js | 3.60 | Prompts browser page |
| pipelines.js | 2.49 | Pipelines browser page |
| _runId.js | 1.72 | Run detail page |
| index-ueUg.js | 1.89 | Runs list (index route) |
| index-DmLx.js | 0.59 | Route tree / root layout |

Shared UI component chunks (auto-split by Vite):

| Shared Chunk | Gzip (KB) | Content |
|--------------|-----------|---------|
| select.js | 7.55 | Radix Select primitive |
| card.js | 6.12 | Card + shared components |
| live.js | 5.77 | Live page components |
| badge.js | 4.27 | Badge + StatusBadge |
| scroll-area.js | 4.10 | Radix ScrollArea |
| tabs.js | 3.07 | Radix Tabs primitive |
| time.js | 1.72 | Time formatting utilities |
| input.js | 0.44 | Input component |
| chevron-right.js | 0.14 | Single icon |

## 3. Main Bundle Composition (152.77 KB gzip)

The main bundle (`index-Dayn6vbJ.js`) contains all vendor dependencies. Estimated breakdown:

| Dependency | Est. Gzip (KB) | Notes |
|------------|----------------|-------|
| react + react-dom v19 | ~51.5 | React 19 increased ~26% vs 18 |
| @tanstack/react-router | ~15-20 | Core router + route tree |
| @tanstack/react-query v5 | ~13-16 | Query client + hooks |
| zod v4 | ~17 | Full validation library |
| radix-ui primitives | ~10-15 | Shared primitive internals |
| zustand | ~1 | Minimal state management |
| lucide-react (icons used) | ~2-3 | Tree-shaken, ~200-300 bytes/icon |
| clsx + tailwind-merge + cva | ~3-5 | Utility classes |
| microdiff | ~0.5 | Tiny diff library |
| App bootstrap code | ~15-20 | Stores, API client, query config |

## 4. manualChunks Strategy (For Cache Efficiency)

While not needed for size budget, `manualChunks` improves cache hit rates during deploys (vendor deps change less often than app code):

```typescript
// vite.config.ts -- build.rollupOptions.output.manualChunks
// NOTE: Vite 7 still uses rollupOptions (NOT rolldownOptions, which is Vite 8+)
rollupOptions: {
  output: {
    manualChunks: {
      vendor: ['react', 'react-dom'],
      router: ['@tanstack/react-router'],
      query: ['@tanstack/react-query'],
    }
  }
}
```

Expected result after manualChunks:
- `vendor-[hash].js`: ~51.5 KB gzip (changes rarely)
- `router-[hash].js`: ~15-20 KB gzip (changes on router upgrades)
- `query-[hash].js`: ~13-16 KB gzip (changes on query upgrades)
- `index-[hash].js`: ~70-75 KB gzip (app code, changes frequently)

**Total gzip unchanged** -- manualChunks only reorganizes, does not reduce total size.

## 5. Bundle Analysis Tooling

### rollup-plugin-visualizer (Recommended)

```bash
npm install --save-dev rollup-plugin-visualizer
```

```typescript
// vite.config.ts -- conditional on mode
import { visualizer } from 'rollup-plugin-visualizer'
import type { PluginOption } from 'vite'

export default defineConfig(({ mode }) => ({
  plugins: [
    tanstackRouter({ autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    mode === 'analyze' && visualizer({
      filename: 'dist/stats.html',
      gzipSize: true,
      brotliSize: true,
      template: 'treemap', // or 'sunburst', 'flamegraph'
    }) as PluginOption,
  ].filter(Boolean),
  // ... rest of config
}))
```

Usage: `npx vite build --mode analyze` then open `dist/stats.html`.

### source-map-explorer (Alternative)

```bash
npx source-map-explorer dist/assets/index-*.js
```

Requires `build.sourcemap: true` in vite config. Produces dependency-level treemap.

### vite-bundle-analyzer (Alternative)

```bash
npm install --save-dev vite-bundle-analyzer
```

Interactive analysis in browser during build.

## 6. Compression: Gzip vs Brotli

| Compression | Browser Support | Size vs Raw | Notes |
|-------------|----------------|-------------|-------|
| Gzip | Universal | ~70% reduction | Default, what Vite reports |
| Brotli | All modern browsers | ~75-80% reduction | 10-15% better than gzip |
| None | -- | Baseline | Only for local dev |

### Pre-compression at Build Time

Not recommended for this project. FastAPI's `GZipMiddleware` handles dynamic compression. If pre-compression is desired later:

```bash
npm install --save-dev vite-plugin-compression2
```

```typescript
import { compression } from 'vite-plugin-compression2'

plugins: [
  compression({ algorithm: 'gzip', threshold: 1024 }),
  compression({ algorithm: 'brotliCompress', threshold: 1024 }),
]
```

This generates `.gz` and `.br` files alongside originals. Server must be configured to prefer pre-compressed files.

### FastAPI Compression

```python
from starlette.middleware.gzip import GZipMiddleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
```

This handles on-the-fly gzip. For brotli, use `brotli-asgi` package. For most deployments behind a reverse proxy (nginx, CloudFlare), the proxy handles compression and this is unnecessary.

## 7. CI Build-Time Size Reporting Script

```bash
#!/usr/bin/env bash
# scripts/check-bundle-size.sh
set -euo pipefail

BUDGET_KB=500
BUILD_DIR="llm_pipeline/ui/frontend/dist"

cd "$(dirname "$0")/.."

# Build
(cd llm_pipeline/ui/frontend && npm run build)

# Sum gzip sizes from vite output (or measure with gzip -c)
TOTAL=0
for f in "$BUILD_DIR"/assets/*.js "$BUILD_DIR"/assets/*.css "$BUILD_DIR"/index.html; do
  [ -f "$f" ] || continue
  SIZE=$(gzip -c "$f" | wc -c)
  KB=$(echo "scale=2; $SIZE / 1024" | bc)
  TOTAL=$(echo "$TOTAL + $KB" | bc)
  echo "  $(basename "$f"): ${KB} KB gzip"
done

echo ""
echo "Total gzip: ${TOTAL} KB (budget: ${BUDGET_KB} KB)"

OVER=$(echo "$TOTAL > $BUDGET_KB" | bc)
if [ "$OVER" -eq 1 ]; then
  echo "FAIL: Bundle exceeds ${BUDGET_KB} KB budget"
  exit 1
else
  echo "PASS: Bundle within budget"
fi
```

### package.json Script Addition

```json
{
  "scripts": {
    "build:analyze": "vite build --mode analyze",
    "build:size": "vite build 2>&1 | tail -30"
  }
}
```

## 8. Further Optimization Opportunities (Not Currently Needed)

Ranked by impact if budget becomes tight in the future:

### High Impact
1. **@zod/mini**: Replace `zod` with `@zod/mini` -- saves ~15 KB gzip (17KB -> 1.9KB). Requires checking that `@tanstack/zod-adapter` supports `@zod/mini`.
2. **Dynamic import heavy leaf components**: JsonDiff, ContextEvolution, PromptViewer could be lazy-loaded if they grow large.

### Medium Impact
3. **Radix primitive cherry-picking**: Ensure only used primitives are imported (currently appears correct via shadcn pattern).
4. **React compiler** (when stable): Can reduce re-render overhead and potentially bundle size via memoization removal.

### Low Impact (Diminishing Returns)
5. **Font subsetting**: Subset JetBrains Mono to Latin-only if other character sets not needed (saves ~36 KB raw font data).
6. **CSS purging**: Tailwind v4 already handles this via JIT mode.
7. **Preact alias**: Could replace react+react-dom (~51KB gzip) with preact+preact-compat (~5KB gzip) but introduces compatibility risk.

## 9. Key Findings Summary

1. **NFR-009 PASSES**: 209.91 KB gzip total, well under 500 KB budget (58% headroom)
2. **Auto code-splitting ACTIVE**: TanStack Router's `autoCodeSplitting` already splits routes into 15 separate chunks
3. **ReactQueryDevtools excluded**: Already lazy-loaded and excluded from production builds
4. **manualChunks recommended**: Not for size, but for cache efficiency -- separating vendor/router/query chunks
5. **Vite 7 uses `rollupOptions`**: NOT `rolldownOptions` (that is Vite 8+). Object-form `manualChunks` still works.
6. **rollup-plugin-visualizer**: Best analysis tool for Vite, supports gzip/brotli size display
7. **Compression**: FastAPI `GZipMiddleware` sufficient for dynamic compression; pre-compression optional
8. **Biggest future savings**: Replacing `zod` with `@zod/mini` (~15 KB gzip reduction) if budget tightens

## 10. Vite 7 API Compatibility Notes

The task 44 description specifies:
```typescript
build: {
  rollupOptions: {
    output: { manualChunks: { ... } }
  }
}
```

This is **correct for Vite 7**. Key API notes:
- `build.rollupOptions` is the active config key (Vite 7)
- `build.rolldownOptions` is the Vite 8+ replacement
- Object-form `manualChunks` works in Vite 7 (deprecated in Vite 8, replaced by `codeSplitting`)
- The task description's chunk splitting approach is valid and recommended
