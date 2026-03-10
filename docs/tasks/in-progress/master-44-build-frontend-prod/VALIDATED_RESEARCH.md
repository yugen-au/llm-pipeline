# Research Summary

## Executive Summary

Three research outputs validated against actual codebase. Core findings are sound: NFR-009 passes at ~210KB gzip (58% headroom), StaticFiles serving is already correctly implemented in cli.py, and the manualChunks strategy is appropriate for cache efficiency. Validation uncovered three contradictions (bundle size estimate mismatch, GZipMiddleware claimed but absent, misleading zod chunk placement rationale), one build-ordering gap (no npm->hatch orchestration), and a missing dependency in the bundle analysis (@tanstack/zod-adapter). All five CEO questions resolved -- task 44 scope now includes: vite.config.ts production config, GZipMiddleware addition, scripts/build.sh orchestration, rollup-plugin-visualizer, and sourcemap: false.

## Domain Findings

### Vite Build Configuration
**Source:** step-1-vite-build-research.md, step-3-bundle-performance.md

- Current vite.config.ts uses object-form `defineConfig` with `build.outDir: 'dist'` and no rollupOptions -- CONFIRMED
- Conversion to function-form `defineConfig(({ mode }) => ({...}))` required for conditional visualizer plugin -- standard Vite pattern, low risk
- manualChunks splitting react/react-dom, @tanstack/react-router, @tanstack/react-query is appropriate for cache efficiency, not size reduction
- autoCodeSplitting (route-level) and manualChunks (library-level) are complementary, not conflicting -- CONFIRMED via Vite/Rollup architecture
- Vite 7 uses `rollupOptions` (NOT `rolldownOptions` which is Vite 8+) -- CONFIRMED via package.json `"vite": "^7.3.1"`
- **DECISION:** Keep `^7.3.1` (caret). Rely on lockfile for stability. Accept minor bump risk.
- **DECISION:** sourcemap: false. No error tracking planned.

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

**DECISION (StaticFiles location):** Keep cli.py approach. Skip app.py changes from original task spec. cli.py correctly keeps create_app() as a pure testable factory.

**DECISION (GZipMiddleware):** Add GZipMiddleware to FastAPI app for standalone compression. This is NEW SCOPE for task 44 -- research incorrectly claimed it was already present. Implementation: `app.add_middleware(GZipMiddleware, minimum_size=1000)` in app.py's create_app().

### Bundle Size & Performance
**Source:** step-3-bundle-performance.md

- Measured build: 483.62KB raw / 152.77KB gzip (main JS), ~130KB raw / 43.47KB gzip (15 route chunks), 60.72KB raw / 13.26KB gzip (CSS)
- Total: ~675KB raw / 209.91KB gzip -- well under 500KB NFR-009 budget
- 15 auto-split route chunks from TanStack Router autoCodeSplitting -- CONFIRMED (6 route files + shared component chunks)
- ReactQueryDevtools excluded from production via `import.meta.env.DEV` guard in main.tsx -- CONFIRMED at main.tsx lines 11-17
- Radix-UI imports match research: Slot, Label, Checkbox, ScrollArea, Separator, Dialog (Sheet), Select, Tabs, Tooltip -- CONFIRMED via grep

**FACTUAL ERROR (now resolved):** Step 3 stated "FastAPI's GZipMiddleware handles dynamic compression" as if already active. It was NOT configured. CEO approved adding it -- now in scope.

### Hatchling Build Integration
**Source:** step-1-vite-build-research.md, step-2-fastapi-static-serving.md

- `artifacts = ["llm_pipeline/ui/frontend/dist/**"]` includes dist/ in wheel even if gitignored -- CONFIRMED at pyproject.toml line 38
- Excludes for node_modules, src, config files -- CONFIRMED at pyproject.toml lines 40-54
- `packages = ["llm_pipeline"]` -- CONFIRMED

**DECISION (build orchestration):** Add `scripts/build.sh` chaining `npm run build` -> `hatch build`. No CI task exists yet, so this script is in scope for task 44. Hatchling's `artifacts` silently includes nothing if dist/ missing -- the build script must ensure correct ordering.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Build orchestration: include scripts/build.sh chaining npm->hatch? | YES, add scripts/build.sh. No CI task exists yet. | Adds new deliverable to task 44: scripts/build.sh |
| GZipMiddleware: add to app.py or expect reverse proxy? | YES, add GZipMiddleware for standalone compression. | Adds new deliverable: GZipMiddleware in app.py create_app() |
| StaticFiles location: keep cli.py or move to app.py per task spec? | Keep cli.py. Skip app.py changes. cli.py is correct. | Confirms deviation from task spec is intentional. No StaticFiles work needed. |
| Vite version pinning: tilde (~7.3.1) or keep caret (^7.3.1)? | Keep ^7.3.1 (caret). Rely on lockfile. | No change to package.json version range |
| Sourcemaps: false or 'hidden' for error tracking? | false. No error tracking planned. | Simple config: sourcemap: false |

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
- [x] cli.py is correct location for StaticFiles (CEO confirmed)
- [x] sourcemap: false appropriate (no error tracking planned)
- [x] Caret versioning (^7.3.1) acceptable with lockfile discipline

## Open Items
- @tanstack/zod-adapter compatibility with @zod/mini unverified (deferred -- future optimization, not task 44 scope)

## Recommendations for Planning
1. Trust step 3's measured bundle sizes (~210KB gzip), not step 1's estimates (~90-120KB gzip)
2. Keep StaticFiles mount in cli.py (not app.py) -- confirmed by CEO, no work needed here
3. Task 44 final scope (5 deliverables):
   - vite.config.ts: function-form defineConfig, manualChunks, emptyOutDir, sourcemap: false
   - package.json: add build:analyze script
   - rollup-plugin-visualizer: install as devDependency, conditional load in vite.config.ts
   - app.py: add GZipMiddleware(minimum_size=1000) to create_app()
   - scripts/build.sh: chain `cd frontend && npm run build` -> `hatch build`, fail-fast on missing dist/
4. Verify build succeeds and total gzip < 500KB after all changes applied
5. Defer @zod/mini optimization to future task (zod-adapter compatibility unknown)
