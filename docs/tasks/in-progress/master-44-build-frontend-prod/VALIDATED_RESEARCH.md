# Research Summary

## Executive Summary

Three research outputs validated against actual codebase. Core findings are sound: NFR-009 passes at ~210KB gzip (58% headroom), StaticFiles serving is already implemented correctly in cli.py, and the manualChunks strategy is appropriate for cache efficiency. However, validation uncovered three contradictions (bundle size estimate mismatch, GZipMiddleware claimed but absent, misleading zod chunk placement rationale), one build-ordering gap (no npm->hatch orchestration), and a missing dependency in the bundle analysis (@tanstack/zod-adapter). Five questions require CEO input before planning can proceed.

## Domain Findings

### Vite Build Configuration
**Source:** step-1-vite-build-research.md, step-3-bundle-performance.md

- Current vite.config.ts uses object-form `defineConfig` with `build.outDir: 'dist'` and no rollupOptions -- CONFIRMED
- Conversion to function-form `defineConfig(({ mode }) => ({...}))` required for conditional visualizer plugin -- standard Vite pattern, low risk
- manualChunks splitting react/react-dom, @tanstack/react-router, @tanstack/react-query is appropriate for cache efficiency, not size reduction
- autoCodeSplitting (route-level) and manualChunks (library-level) are complementary, not conflicting -- CONFIRMED via Vite/Rollup architecture
- Vite 7 uses `rollupOptions` (NOT `rolldownOptions` which is Vite 8+) -- CONFIRMED via package.json `"vite": "^7.3.1"`

**CONTRADICTION:** Step 1 estimated ~90-120KB gzip total. Step 3 measured ~210KB gzip from actual build. Step 1 underestimated by ~75%. Trust step 3's measured values.

**GAP:** `@tanstack/zod-adapter` (production dependency, used in 4 route files) missing from step 1's dependency table. Small adapter shim but relevant to @zod/mini migration feasibility since zod-adapter may not support @zod/mini.

**MISLEADING:** Step 1 states zod "likely bundled with router chunk naturally" due to zod-adapter usage. This won't happen -- manualChunks only extracts explicitly listed packages. Zod stays in the main app chunk. Functionally fine, but the rationale is incorrect.

### FastAPI Static File Serving
**Source:** step-2-fastapi-static-serving.md

- StaticFiles mount in `cli.py:_run_prod_mode()` at lines 59-73 -- CONFIRMED exact match
- `StaticFiles(directory=str(dist_dir), html=True)` with `name="spa"` -- CONFIRMED
- Path resolution: `Path(__file__).resolve().parent / "frontend" / "dist"` -- CONFIRMED
- Graceful fallback to API-only mode with stderr warning -- CONFIRMED
- Route priority: API routes (/api/*) registered in create_app(), WebSocket (/ws/*) registered without prefix, StaticFiles (/) mounted last in cli.py -- CONFIRMED no conflicts
- create_app() in app.py contains NO StaticFiles mount -- CONFIRMED (app.py is pure API factory)

**DEVIATION FROM TASK SPEC:** Task 44 spec says mount StaticFiles in app.py's create_app(). Current cli.py implementation is architecturally better (keeps create_app testable, static serving is deployment concern). Needs CEO confirmation to keep.

### Bundle Size & Performance
**Source:** step-3-bundle-performance.md

- Measured build: 483.62KB raw / 152.77KB gzip (main JS), ~130KB raw / 43.47KB gzip (15 route chunks), 60.72KB raw / 13.26KB gzip (CSS)
- Total: ~675KB raw / 209.91KB gzip -- well under 500KB NFR-009 budget
- 15 auto-split route chunks from TanStack Router autoCodeSplitting -- CONFIRMED (6 route files + shared component chunks)
- ReactQueryDevtools excluded from production via `import.meta.env.DEV` guard in main.tsx -- CONFIRMED at main.tsx lines 11-17
- Radix-UI imports match research: Slot, Label, Checkbox, ScrollArea, Separator, Dialog (Sheet), Select, Tabs, Tooltip -- CONFIRMED via grep

**FACTUAL ERROR:** Step 3 section 6 states "FastAPI's GZipMiddleware handles dynamic compression" as if already active. Actual app.py has NO GZipMiddleware -- only CORSMiddleware. Static files from dist/ are served uncompressed unless a reverse proxy handles it.

### Hatchling Build Integration
**Source:** step-1-vite-build-research.md, step-2-fastapi-static-serving.md

- `artifacts = ["llm_pipeline/ui/frontend/dist/**"]` includes dist/ in wheel even if gitignored -- CONFIRMED at pyproject.toml line 38
- Excludes for node_modules, src, config files -- CONFIRMED at pyproject.toml lines 40-54
- `packages = ["llm_pipeline"]` -- CONFIRMED

**BUILD ORDERING GAP:** No mechanism chains `npm run build` before `hatch build`. Hatchling's `artifacts` silently includes nothing if dist/ doesn't exist -- the wheel will lack frontend assets without error. No top-level Makefile, build.sh, or similar orchestration exists.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| (pending -- iteration 0, questions below) | | |

## Assumptions Validated
- [x] autoCodeSplitting and manualChunks are complementary mechanisms (route-level vs library-level splitting)
- [x] html=True SPA catch-all correctly serves index.html for all non-file routes
- [x] StaticFiles mount order after API routes prevents path conflicts
- [x] hatchling artifacts config includes dist/ in wheel when present
- [x] ReactQueryDevtools excluded from production build via import.meta.env.DEV
- [x] Vite 7 uses rollupOptions (not rolldownOptions)
- [x] NFR-009 passes: 209.91KB gzip vs 500KB budget (58% headroom)
- [x] Current package.json "build" script is correct (tsc -b && vite build)
- [x] tsconfig.app.json has noEmit: true (tsc -b is type-check only)
- [x] Radix-UI primitives are correctly tree-shaken via sub-path exports

## Open Items
- GZipMiddleware not present in app.py despite research claiming it handles compression
- No build orchestration (npm build -> hatch build) documented or scripted
- @tanstack/zod-adapter compatibility with @zod/mini unverified (blocks future optimization recommendation)
- Vite ^7.3.1 semver range could theoretically allow Vite 8 if published under ^7 (unlikely but undocumented risk)
- sourcemap strategy (false vs 'hidden') depends on error tracking plans

## Recommendations for Planning
1. Trust step 3's measured bundle sizes (~210KB gzip), not step 1's estimates (~90-120KB gzip)
2. Keep StaticFiles mount in cli.py (not app.py) per current implementation -- better separation of concerns
3. Scope task 44 to: vite.config.ts changes (manualChunks, function form, visualizer), package.json script additions (build:analyze), rollup-plugin-visualizer devDep installation
4. Defer GZipMiddleware and build orchestration decisions to CEO input
5. Consider adding `build:check` script that verifies dist/ exists and measures gzip size for CI
6. Pin Vite to `~7.3.1` (tilde, not caret) to prevent accidental Vite 8 upgrade that would break rollupOptions config
