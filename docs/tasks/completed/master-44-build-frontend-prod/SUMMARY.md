# Task Summary

## Work Completed

Configured Vite 7 production build with chunk splitting and optional bundle analysis, added GZipMiddleware to the FastAPI app factory, and created a build orchestration script. The task spanned four implementation steps across three execution groups, one review fix cycle (env var scoping bug in build:analyze), and a full test run confirming 803/804 tests passing (one pre-existing unrelated failure). Final bundle is 209.41KB gzip -- 57.8% under the 500KB NFR-009 target.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `scripts/build.sh` | Orchestrates frontend npm build then hatch Python package build; fails fast if dist/index.html absent after npm build |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/ui/frontend/vite.config.ts` | Converted to function-form defineConfig; added build.emptyOutDir, build.sourcemap:false, rollupOptions.output.manualChunks (vendor/router/query), conditional rollup-plugin-visualizer via ANALYZE env var |
| `llm_pipeline/ui/frontend/vitest.config.ts` | Replaced mergeConfig(viteConfig,...) pattern with standalone defineConfig; duplicated resolve.alias (function-form vite export incompatible with mergeConfig first arg) |
| `llm_pipeline/ui/frontend/package.json` | Added build:analyze script (`tsc -b && ANALYZE=true vite build`); added rollup-plugin-visualizer@^5.14.0 to devDependencies |
| `llm_pipeline/ui/frontend/package-lock.json` | Auto-updated by npm install; added rollup-plugin-visualizer@5.14.0 and 5 transitive deps (724 total packages) |
| `llm_pipeline/ui/app.py` | Added `from starlette.middleware.gzip import GZipMiddleware` import; added `app.add_middleware(GZipMiddleware, minimum_size=1000)` in create_app() after CORS block |

## Commits Made

| Hash | Message |
| --- | --- |
| `647141c` | `docs(implementation-A): master-44-build-frontend-prod` (vite.config.ts + vitest.config.ts) |
| `e5efa06` | `docs(implementation-A): master-44-build-frontend-prod` (package.json initial build:analyze) |
| `c6b8178` | `docs(implementation-B): master-44-build-frontend-prod` (app.py GZipMiddleware import) |
| `c55baa1` | `docs(implementation-B): master-44-build-frontend-prod` (app.py middleware call) |
| `e57ea40` | `docs(implementation-C): master-44-build-frontend-prod` (scripts/build.sh) |
| `9b1304f` | `chore(state): master-44-build-frontend-prod -> testing` |
| `ce095e1` | `chore(state): master-44-build-frontend-prod -> review` |
| `8379095` | `docs(fixing-review-A): master-44-build-frontend-prod` (env var scoping fix in build:analyze) |
| `f1e859e` | `chore(state): master-44-build-frontend-prod -> review` (re-review approval) |

## Deviations from Plan

- **rollupOptions instead of rolldownOptions**: PLAN.md specified `build.rolldownOptions` per Vite 7 Context7 docs. Testing showed `rolldownOptions.output.manualChunks` was silently ignored in Vite 7.3.1 -- no chunk splitting occurred. Switched to `build.rollupOptions` (backward-compatible alias Vite 7 still processes for output.manualChunks). Confirmed working with actual build output.
- **Function-form manualChunks instead of object-form**: PLAN.md specified object-form `{ vendor: ['react', 'react-dom'] }`. Object-form produced empty vendor chunk with Vite 7 / Rolldown bundler (module concatenation inlines universally-imported modules into entry chunk). Function-form path matching on `node_modules/` paths reliably split all three chunks.
- **vitest.config.ts standalone config**: PLAN.md did not explicitly address vitest.config.ts. The function-form vite.config.ts export broke the existing `mergeConfig(viteConfig, ...)` pattern in vitest.config.ts (mergeConfig first arg expects UserConfig object, not function). Resolved by converting vitest.config.ts to a standalone defineConfig with resolve.alias duplicated.

## Issues Encountered

### build:analyze env var scoping bug
The initial `build:analyze` script was `"ANALYZE=true tsc -b && vite build"`. The inline prefix-style assignment `ANALYZE=true` only scoped to the first command (`tsc -b`), not to `vite build` after `&&`. The visualizer plugin in vite.config.ts reads `process.env.ANALYZE` during `vite build`, so the plugin would never activate via this script.

**Resolution:** Changed to `"tsc -b && ANALYZE=true vite build"` in commit `8379095`. The env var now correctly scopes to `vite build` only. Type checking (`tsc -b`) never needed it.

### manualChunks object-form silently ignored in Vite 7
Object-form manualChunks (`{ vendor: ['react', 'react-dom'] }`) produced no chunk splitting at build time -- the vendor chunk was empty or absent in output. Vite 7's Rolldown bundler inlines universally-imported modules via module concatenation when object-form is used.

**Resolution:** Switched to function-form `manualChunks(id)` matching on `id.includes('node_modules/react/')` paths. All three chunks (vendor/router/query) split correctly.

### rolldownOptions silently ignored in Vite 7.3.1
Context7 docs for Vite 7 reference `build.rolldownOptions` as canonical. In practice, `rolldownOptions.output.manualChunks` was silently ignored -- no chunk splitting occurred despite correct syntax.

**Resolution:** Used `build.rollupOptions` (the backward-compatible alias Vite 7.3.1 still processes for output chunk configuration). Chunk splitting worked correctly.

## Success Criteria

- [x] `npm run build` completes without errors and produces `dist/index.html` -- confirmed, 7.34s build time, 2112 modules transformed
- [ ] `npm run build:analyze` produces `stats.html` -- script and plugin are correctly implemented; human validation on Unix/CI required (Unix env var syntax; Windows without WSL cannot run inline prefix assignments)
- [x] Built bundle total gzip size <500KB (NFR-009) -- 209.41KB total (57.8% under target)
- [x] Three vendor chunks visible in build output -- vendor 60.53KB gz, router 27.29KB gz, query 11.41KB gz
- [x] sourcemap:false confirmed -- zero .map files found in dist/
- [ ] scripts/build.sh end-to-end with hatch build -- script structure and executable bit verified; full end-to-end (npm ci + hatch build) requires Unix/CI environment
- [ ] FastAPI gzip live response verification -- GZipMiddleware is registered (confirmed via repr); live curl verification requires running server
- [x] GZipMiddleware present in app middleware -- confirmed `Middleware(GZipMiddleware, minimum_size=1000)` in user_middleware via Python import check

## Recommendations for Follow-up

1. Add `stats.html` to `llm_pipeline/ui/frontend/.gitignore` to prevent accidental commit of the 2-5MB visualizer artifact when a developer runs `build:analyze`.
2. Consider adding `cross-env` as a devDependency and updating `build:analyze` to `cross-env ANALYZE=true tsc -b && cross-env ANALYZE=true vite build` so Windows developers can run the script natively without WSL.
3. Fix pre-existing test failure `tests/test_ui.py::TestRoutersIncluded::test_events_router_prefix` -- the test expects prefix `/events` but the events router is mounted at `/runs/{run_id}/events`; this failure predates task 44 and will continue failing in CI.
4. Run `build:analyze` on a Unix/CI environment to confirm `stats.html` is produced and validate the chunk breakdown visually via the rollup-plugin-visualizer output.
5. Verify GZip compression live by starting the server and running `curl -s -H "Accept-Encoding: gzip" -I http://localhost:8642/api/runs` -- response should include `Content-Encoding: gzip` for API responses over 1000 bytes.
6. Track the vitest.config.ts alias duplication -- if more shared Vite config emerges, consider a dedicated `vite.base.config.ts` exporting a plain object that both vite.config.ts and vitest.config.ts import, avoiding duplication without the mergeConfig incompatibility.
