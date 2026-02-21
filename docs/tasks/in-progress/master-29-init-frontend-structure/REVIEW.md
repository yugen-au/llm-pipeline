# Architecture Review

## Overall Assessment
**Status:** complete
Solid frontend scaffold. Architecture decisions (3-file tsconfig, Tailwind v4 CSS-first, dynamic proxy port, hatchling artifacts) are correct and well-documented. Code is clean, minimal, and properly scoped for a project init task. Two low-severity issues found; no blockers.

## Project Guidelines Compliance
**CLAUDE.md:** D:\Documents\claude-projects\llm-pipeline\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | pyproject.toml requires-python >=3.11 unchanged |
| Pydantic v2 / SQLModel / Hatchling | pass | build system unchanged, artifacts directive added correctly |
| Pipeline + Strategy + Step pattern | pass | no backend changes, frontend is additive |
| No hardcoded values | pass | proxy port via VITE_API_PORT env var, dev port via VITE_PORT |
| Error handling present | pass | cli.py handles missing deps, missing dist/, missing npx |
| Test deps in optional-dependencies.dev | pass | unchanged |

## Issues Found
### Critical
None

### High
None

### Medium
None

### Low
#### Broken favicon reference in index.html
**Step:** 1
**Details:** `index.html` line 5 references `href="/vite.svg"` but `public/vite.svg` was deleted in step 1. Results in a 404 for the favicon in dev mode. Harmless functionally but produces a console error. Should either remove the `<link>` tag or add a project favicon. The page title `<title>frontend</title>` is also a scaffold default -- should be `llm-pipeline` for consistency.

#### Hatchling exclude list does not cover index.html, README.md, .gitignore
**Step:** 10
**Details:** The pyproject.toml `exclude` list omits `llm_pipeline/ui/frontend/index.html`, `llm_pipeline/ui/frontend/README.md`, and `llm_pipeline/ui/frontend/.gitignore`. These dev-only files will be included in the built wheel. Functionally harmless since `cli.py` serves from `dist/` only, but adds ~3KB of unnecessary payload. The PLAN.md exclude list also did not include these, so this is a plan-level omission rather than an implementation deviation.

## Review Checklist
[x] Architecture patterns followed -- clean separation: frontend nested in Python package, hatchling artifacts for dist inclusion, proxy for API/WS, TanStack Router file-based routing
[x] Code quality and maintainability -- minimal files, each with single responsibility; ESLint + Prettier configured; TypeScript strict mode
[x] Error handling present -- cli.py handles missing UI deps, missing dist/, missing npx
[x] No hardcoded values -- proxy port, dev port, API port all configurable via env vars
[x] Project conventions followed -- commit style, branch naming, build system all match project CLAUDE.md
[x] Security considerations -- no secrets committed; .env.local gitignored; minimatch override patches ReDoS vuln
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- placeholder routes are minimal; no premature abstractions; layout deferred to task 30, theme tokens deferred to task 42

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/frontend/vite.config.ts | pass | correct plugin order, dynamic proxy, path alias |
| llm_pipeline/ui/frontend/tsconfig.json | pass | solution file with project references + path alias |
| llm_pipeline/ui/frontend/tsconfig.app.json | pass | ES2020 target, strict, baseUrl+paths for alias |
| llm_pipeline/ui/frontend/tsconfig.node.json | pass | includes vite.config.ts + eslint.config.ts, no DOM lib |
| llm_pipeline/ui/frontend/src/main.tsx | pass | React 19 createRoot, providers, dark class before render |
| llm_pipeline/ui/frontend/src/router.ts | pass | createRouter + Register module augmentation |
| llm_pipeline/ui/frontend/src/queryClient.ts | pass | sensible defaults (30s stale, 2 retries) |
| llm_pipeline/ui/frontend/src/routes/__root.tsx | pass | minimal Outlet, layout deferred to task 30 |
| llm_pipeline/ui/frontend/src/routes/index.tsx | pass | placeholder with Tailwind classes |
| llm_pipeline/ui/frontend/src/index.css | pass | Tailwind v4 CSS-first + shadcn OKLCH vars + dark theme |
| llm_pipeline/ui/frontend/eslint.config.ts | pass | flat config, prettier last, routeTree.gen.ts ignored |
| llm_pipeline/ui/frontend/components.json | pass | new-york style, neutral, rsc:false, cssVariables:true |
| llm_pipeline/ui/frontend/package.json | pass | correct deps, all 5 scripts, minimatch override |
| llm_pipeline/ui/frontend/index.html | fail | broken vite.svg favicon ref, scaffold title |
| llm_pipeline/ui/frontend/src/lib/utils.ts | pass | shadcn cn() utility |
| llm_pipeline/ui/frontend/.prettierrc | pass | matches plan spec |
| llm_pipeline/ui/frontend/.prettierignore | pass | routeTree.gen.ts + dist/ excluded |
| llm_pipeline/ui/frontend/.gitignore | pass | dist/, node_modules/, .vite/, tsbuildinfo, env files |
| llm_pipeline/ui/frontend/src/routeTree.gen.ts | pass | auto-generated, eslint/prettier ignored |
| pyproject.toml | pass | artifacts directive correct, exclude list covers major files |

## New Issues Introduced
- Broken favicon reference in index.html (vite.svg deleted but link tag remains)
- index.html, README.md, .gitignore not excluded from wheel build (minor bloat)

## Recommendation
**Decision:** APPROVE
Both issues are low severity. The broken favicon causes only a console 404 in dev mode and the extra files in the wheel add negligible size. These can be fixed in a follow-up commit or as part of task 30 (routes/layout) which will likely touch index.html anyway. All architecture decisions are sound, implementation matches the plan, and the scaffold is ready for downstream tasks.
