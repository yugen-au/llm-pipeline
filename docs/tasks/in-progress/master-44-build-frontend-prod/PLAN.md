# PLANNING

## Summary
Configure Vite 7 production build with chunk splitting and bundle analysis, add GZipMiddleware to FastAPI `create_app()`, and create `scripts/build.sh` to orchestrate frontend-then-Python builds. No StaticFiles work needed -- cli.py already serves dist/ correctly. Target: total bundle <500KB gzip (currently 209.91KB, 58% headroom).

## Plugin & Agents
**Plugin:** frontend-mobile-development, python-development
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases
1. **Vite config & package.json**: Add manualChunks, sourcemap: false, emptyOutDir, rollup-plugin-visualizer integration; add build:analyze script
2. **FastAPI middleware**: Add GZipMiddleware(minimum_size=1000) to create_app() in app.py
3. **Build orchestration**: Create scripts/build.sh chaining npm run build -> hatch build

## Architecture Decisions

### Function-form defineConfig for conditional visualizer plugin
**Choice:** Convert `defineConfig({...})` to `defineConfig(({ mode }) => ({...}))` in vite.config.ts
**Rationale:** rollup-plugin-visualizer should only run when explicitly requested (via `build:analyze` script or `ANALYZE=true` env var), not on every production build. Function-form allows conditional plugin inclusion based on env/mode. Standard Vite pattern with low risk.
**Alternatives:** Always include visualizer (adds overhead to every build, generates unwanted stats.html artifact in dist/); separate visulaizer config file (more complex, unnecessary)

### GZipMiddleware in app.py create_app() not cli.py
**Choice:** `app.add_middleware(GZipMiddleware, minimum_size=1000)` added to `create_app()` in `llm_pipeline/ui/app.py`
**Rationale:** GZipMiddleware compresses dynamic API responses (JSON) which are served by the FastAPI app regardless of static file setup. Adding to create_app() ensures compression is active in all modes (prod, dev, test). cli.py only handles static file mounting -- a separate concern. minimum_size=1000 avoids compressing tiny responses where overhead exceeds benefit.
**Alternatives:** Add in cli.py _run_prod_mode() (misses API-only mode, wrong separation of concerns); rely on reverse proxy (not available for standalone deployment)

### manualChunks strategy: vendor + router + query
**Choice:** Three explicit vendor chunks: `vendor` (react, react-dom), `router` (@tanstack/react-router), `query` (@tanstack/react-query)
**Rationale:** Largest dependencies by size. Separating them enables long-term browser caching -- each chunk only invalidates when that specific library updates. autoCodeSplitting (already enabled) handles route-level splitting. These two mechanisms are complementary.
**Alternatives:** Single vendor chunk (loses granular cache invalidation); no manualChunks (all vendor code in main chunk, larger cache invalidation on any dep change)

### emptyOutDir: true
**Choice:** Explicitly set `build.emptyOutDir: true` in vite.config.ts
**Rationale:** Vite defaults emptyOutDir to true when outDir is inside project root, but explicit config makes intent clear and prevents stale artifacts if dist/ path ever changes.
**Alternatives:** Rely on default (implicit, fragile if config changes)

### build.sh fail-fast on missing dist/
**Choice:** scripts/build.sh verifies `llm_pipeline/ui/frontend/dist/index.html` exists after npm run build before calling hatch build
**Rationale:** Hatchling's `artifacts = ["llm_pipeline/ui/frontend/dist/**"]` silently includes nothing if dist/ is missing or empty -- the wheel would be built without the frontend with no error. Fail-fast check surfaces this immediately.
**Alternatives:** No check (silent wheel corruption); check in hatchling hook (adds build system complexity, not needed)

## Implementation Steps

### Step 1: Update vite.config.ts with production build settings
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitejs/vite
**Group:** A

1. Convert `export default defineConfig({...})` to function-form `export default defineConfig(({ mode }) => ({...}))` in `llm_pipeline/ui/frontend/vite.config.ts`
2. Add `build.emptyOutDir: true` to the build config object (existing `outDir: 'dist'` stays)
3. Add `build.sourcemap: false` to the build config object
4. Add `build.rollupOptions.output.manualChunks` with three vendor chunks:
   - `vendor`: includes `react`, `react-dom`
   - `router`: includes `@tanstack/react-router`
   - `query`: includes `@tanstack/react-query`
5. Import `visualizer` from `rollup-plugin-visualizer` at top of file
6. Add visualizer plugin conditionally: `...(process.env.ANALYZE === 'true' ? [visualizer({ open: false, filename: 'stats.html', gzipSize: true, brotliSize: true })] : [])` appended to plugins array
7. Preserve all existing config: plugins array (tanstackRouter, react, tailwindcss), resolve.alias, server.proxy

### Step 2: Update package.json with build:analyze script and rollup-plugin-visualizer devDep
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /btd/rollup-plugin-visualizer
**Group:** A

1. Add `"build:analyze": "ANALYZE=true tsc -b && vite build"` to the `scripts` section of `llm_pipeline/ui/frontend/package.json`
2. Add `"rollup-plugin-visualizer": "^5.14.0"` to `devDependencies` in `llm_pipeline/ui/frontend/package.json`
3. Run `npm install` from `llm_pipeline/ui/frontend/` to update package-lock.json (or equivalent lockfile)

### Step 3: Add GZipMiddleware to FastAPI create_app()
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /fastapi/fastapi
**Group:** B

1. Add import `from starlette.middleware.gzip import GZipMiddleware` to `llm_pipeline/ui/app.py` (alongside existing CORSMiddleware import)
2. Add `app.add_middleware(GZipMiddleware, minimum_size=1000)` call in `create_app()` immediately after the CORSMiddleware block and before the database engine setup
3. Verify no existing GZipMiddleware import/call exists in app.py (currently confirmed absent)

### Step 4: Create scripts/build.sh
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Create `scripts/` directory at project root (currently does not exist)
2. Create `scripts/build.sh` with the following logic:
   - `set -euo pipefail` for fail-fast behavior
   - `cd` into `llm_pipeline/ui/frontend/` relative to script location (using `$(dirname "$0")`)
   - Run `npm ci` to ensure deps match lockfile
   - Run `npm run build` (tsc -b && vite build)
   - `cd` back to project root
   - Verify `llm_pipeline/ui/frontend/dist/index.html` exists; if not, print error and exit 1
   - Run `hatch build`
3. Make script executable: `chmod +x scripts/build.sh`

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| manualChunks function-form may conflict with TanStack Router's autoCodeSplitting chunk generation | Medium | autoCodeSplitting and manualChunks operate at different levels (route vs library); confirmed complementary by Vite/Rollup architecture. If conflict arises, remove manualChunks and rely solely on autoCodeSplitting. |
| rollup-plugin-visualizer version ^5.14.0 may not be available on npm at time of install | Low | Use latest available 5.x release; check npm registry. The `ANALYZE=true` guard means any version issue only affects analysis builds, not production builds. |
| GZipMiddleware double-compression if a reverse proxy is later added | Low | minimum_size=1000 limits overhead. Document in app.py that GZipMiddleware is present. |
| scripts/build.sh uses bash shebang; may not work on Windows without WSL/Git Bash | Low | Project is Windows dev environment but build scripts typically run in CI (Linux). Add note in script header. For local Windows use, run steps manually or via WSL. |
| Conditional visualizer with `process.env.ANALYZE` may fail on Windows (env var syntax `ANALYZE=true cmd`) | Medium | build:analyze script uses Unix syntax. Windows devs should use cross-env or run via WSL. Note in package.json comment or README. |

## Success Criteria
- [ ] `npm run build` in `llm_pipeline/ui/frontend/` completes without errors and produces `dist/index.html`
- [ ] `npm run build:analyze` produces `stats.html` in frontend directory showing chunk breakdown
- [ ] Built bundle total gzip size <500KB (NFR-009); expected ~210KB based on measured baseline
- [ ] Three vendor chunks visible in build output: `vendor`, `router`, `query`
- [ ] `sourcemap: false` confirmed: no `.map` files in `dist/`
- [ ] `scripts/build.sh` runs to completion and produces a valid hatch wheel containing `llm_pipeline/ui/frontend/dist/`
- [ ] FastAPI app responds to `Accept-Encoding: gzip` with compressed response (Content-Encoding: gzip) for API endpoints returning >1000 bytes
- [ ] `python -c "from llm_pipeline.ui.app import create_app; app = create_app(); print([type(m).__name__ for m in app.middleware_stack.middlewares])"` shows GZipMiddleware present

## Phase Recommendation
**Risk Level:** low
**Reasoning:** All changes are additive config/middleware additions. No schema changes, no API changes, no routing changes. StaticFiles already correctly implemented (confirmed by CEO). Measured bundle already passes NFR-009 with 58% headroom. The only new executable code is GZipMiddleware (well-tested Starlette built-in) and the build script (shell script with no production runtime impact). manualChunks is a standard Vite pattern confirmed in docs.
**Suggested Exclusions:** testing, review
