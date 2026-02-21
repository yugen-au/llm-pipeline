# Research Summary

## Executive Summary

Three research steps validated for task 29 (init frontend scaffold at `llm_pipeline/ui/frontend/`). Research is comprehensive and self-correcting -- step-1 appendix already flags and resolves most cross-step contradictions. Four contradictions found (all resolved), six hidden assumptions identified (all low/medium risk), and two gaps requiring implementation attention. CEO confirmed: Vite 7 (latest), shadcn new-york + neutral, ESLint/Prettier in scope.

## Domain Findings

### Frontend Stack Versions
**Source:** step-1-frontend-stack-research.md

Current stable versions confirmed via npm/web research (Feb 2026):
- React 19.2.4, ReactDOM 19.2.4
- Vite 7.3.1 (CEO confirmed: use latest, not ^6.0.0 from task description)
- TypeScript 5.7.x
- TailwindCSS 4.2.0 with `@tailwindcss/vite` plugin (no postcss/autoprefixer)
- @tanstack/react-router 1.161.1, @tanstack/router-plugin 1.161.3
- @tanstack/react-query 5.x, Zustand 5.0.11
- shadcn/ui via `npx shadcn@latest init` (NOT npm dependency)

Vite 7 requires Node 20+ (Node 18 EOL'd Apr 2025).

### Tailwind v4 CSS-First Config
**Source:** step-1-frontend-stack-research.md

Tailwind v4 eliminates `tailwind.config.ts`. All config in CSS:
- `@import "tailwindcss"` replaces `@tailwind base/components/utilities`
- `@theme inline` replaces `theme.extend` in config file
- `@custom-variant dark (&:where(.dark, .dark *))` enables class-based dark mode
- OKLCH color format replaces HSL
- `tw-animate-css` replaces deprecated `tailwindcss-animate`

Impact on task 42: its details reference `tailwind.config.ts` and v3 directives. Task 42 will need updated approach. NOT task 29 scope.

### shadcn/ui Integration
**Source:** step-1-frontend-stack-research.md

CEO confirmed: style "new-york", base color "neutral", CSS variables enabled.
- `npx shadcn@latest init` is interactive; creates `components.json` with `rsc: false` (Vite, not Next.js)
- Init generates CSS with OKLCH variables in `:root` and `.dark` selectors, maps via `@theme inline`
- Auto-installs: `tw-animate-css`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`
- Init MUST run AFTER Tailwind/Vite/path-alias setup (modifies `src/index.css`)
- Custom status color tokens added AFTER shadcn init to avoid overwrite

### Python/Hatchling Integration
**Source:** step-2-python-integration-research.md

Correct build mechanism is `artifacts` (NOT `shared-data`):
```toml
[tool.hatch.build.targets.wheel]
packages = ["llm_pipeline"]
artifacts = ["llm_pipeline/ui/frontend/dist/**"]
exclude = [
    "llm_pipeline/ui/frontend/node_modules/**",
    "llm_pipeline/ui/frontend/src/**",
    "llm_pipeline/ui/frontend/.vite/**",
    "llm_pipeline/ui/frontend/tsconfig*",
    "llm_pipeline/ui/frontend/vite.config*",
    "llm_pipeline/ui/frontend/components.json",
    "llm_pipeline/ui/frontend/eslint*",
    "llm_pipeline/ui/frontend/.eslint*",
    "llm_pipeline/ui/frontend/.prettierrc",
    "llm_pipeline/ui/frontend/.prettierignore",
    "llm_pipeline/ui/frontend/package*.json",
]
```

Key: `artifacts` overrides gitignore exclusion of `dist/`. `shared-data` installs to wrong location (`{prefix}/share/`). cli.py uses `__file__`-relative path requiring dist/ inside package.

No `[tool.hatch.build]` sections exist yet in pyproject.toml. Must be added.

### CLI Integration Points (Verified Against Code)
**Source:** step-2-python-integration-research.md, codebase verification

Verified in `llm_pipeline/ui/cli.py`:
- Line 64: `dist_dir = Path(__file__).resolve().parent / "frontend" / "dist"`
- Line 66: `StaticFiles(directory=str(dist_dir), html=True)` mounted at `/`
- Line 69: WARNING fallback when dist/ missing (API-only mode)
- Line 155: `env = {**os.environ, "VITE_PORT": str(vite_port), "VITE_API_PORT": str(api_port)}`

Verified in `llm_pipeline/ui/app.py`:
- Lines 75-79: All API routers mounted with `prefix="/api"`
- Line 80: `ws_router` mounted WITHOUT prefix (WebSocket at `/ws/runs/{run_id}`)

### Vite Configuration
**Source:** step-3-tsvite-config-research.md, step-1-frontend-stack-research.md (consolidated)

Authoritative vite.config.ts must include:
1. `tanstackRouter()` plugin BEFORE `react()` (generates routeTree.gen.ts)
2. `tailwindcss()` plugin from `@tailwindcss/vite` (MISSING in step-3, present in step-1)
3. Dynamic proxy using `process.env.VITE_API_PORT` (step-3 approach, NOT step-1 hardcoded values)
4. Path alias `@` -> `./src` via `resolve.alias`
5. `build.outDir: "dist"` matching cli.py expectation

### TypeScript Configuration
**Source:** step-1-frontend-stack-research.md, step-3-tsvite-config-research.md

Use 3-file pattern from Vite scaffold (step-1), NOT 2-file pattern (step-3):
- `tsconfig.json` -- solution file with references to app + node configs, path aliases
- `tsconfig.app.json` -- application code (jsx, strict, DOM lib, path aliases)
- `tsconfig.node.json` -- config files (vite.config.ts, eslint.config.ts)

Key settings: `jsx: "react-jsx"`, `moduleResolution: "bundler"`, `verbatimModuleSyntax: true`, `noEmit: true`.

### ESLint + Prettier
**Source:** step-3-tsvite-config-research.md (CEO confirmed: in scope for task 29)

ESLint 9 flat config (`eslint.config.ts`):
- `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`
- `eslint-config-prettier` as last extends (disables conflicting rules)
- Ignores: `dist/`, `src/routeTree.gen.ts`

Prettier (`.prettierrc`): semi=false, singleQuote=true, trailingComma=all, tabWidth=2, printWidth=100.

### TanStack Router Import Name
**Source:** step-1-frontend-stack-research.md (appendix B)

Export name changed across versions:
- v1.114.3 (Context7): `TanStackRouterVite`
- >= v1.150.x: `tanstackRouter` (lowercase)
- Resolution: check `node_modules/@tanstack/router-plugin/dist/vite.d.ts` at implementation time

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Vite version: use latest (7.x) or pin ^6.0.0 per task description? | Use Vite 7 (latest). Note deviation. | `npm create vite@latest` scaffolds Vite 7. No need to downgrade. Backward-compatible. |
| shadcn/ui style and base color preference? | new-york + neutral | Drives `components.json` config and generated CSS variable palette |
| ESLint + Prettier in scope for task 29? | Yes, include ESLint 9 flat config + Prettier | Adds 8 dev dependencies. eslint.config.ts and .prettierrc created during scaffold |

## Assumptions Validated

- [x] cli.py resolves dist via `Path(__file__).parent / "frontend" / "dist"` -- confirmed line 64
- [x] API routes mounted with `/api` prefix -- confirmed app.py lines 75-79
- [x] WebSocket router mounted WITHOUT `/api` prefix -- confirmed app.py line 80, websocket.py line 106
- [x] cli.py passes VITE_PORT and VITE_API_PORT env vars -- confirmed line 155
- [x] .gitignore already covers `dist/` and `node_modules/` recursively -- confirmed
- [x] No `[tool.hatch.build]` sections exist yet -- confirmed (grep found no matches)
- [x] Entry point `llm-pipeline = "llm_pipeline.ui.cli:main"` already configured -- confirmed (task 28 done)
- [x] Graceful degradation when dist/ missing -- confirmed line 69 WARNING message
- [x] `artifacts` config is immune to `exclude` patterns -- confirmed via Context7 hatch docs
- [x] Tailwind v4 does not need postcss/autoprefixer -- confirmed; `@tailwindcss/vite` replaces them
- [x] shadcn/ui `rsc: false` for Vite projects -- confirmed via Context7 shadcn docs
- [x] TanStack Router plugin must come before react() in Vite plugins -- confirmed via Context7 docs

## Open Items

- Task 42 details reference Tailwind v3 patterns (`tailwind.config.ts`, `@tailwind` directives). Will need updated approach for v4. Not blocking task 29.
- TanStack Router export name (`tanstackRouter` vs `TanStackRouterVite`) must be verified at implementation time by checking `node_modules/@tanstack/router-plugin/dist/vite.d.ts`. Fallback documented.
- Node 20+ requirement not validated at runtime by cli.py. Low risk given Node 18 EOL'd Apr 2025.
- `npx shadcn@latest init` is interactive. Implementation must run manually (not automated). For CI reproducibility, `components.json` and generated files should be committed.
- `.prettierignore` needed for `src/routeTree.gen.ts` -- not mentioned in step-3 but noted in step-1 directory structure. Must be created.
- Step-2 exclude list should also include `.prettierrc`, `.prettierignore` for wheel cleanliness.

## Recommendations for Planning

1. Follow step-1 appendix section 4 "Corrected Implementation Order" as the canonical sequence. shadcn init MUST come after Tailwind/Vite/path-alias setup.
2. Use step-3 dynamic proxy config (env vars), NOT step-1 hardcoded values. cli.py passes VITE_API_PORT at runtime.
3. Use step-1 three-file tsconfig pattern (matches Vite scaffold output), NOT step-3 two-file pattern.
4. Add `tailwindcss()` plugin to vite.config.ts (step-1 has it, step-3 omits it).
5. Add `[tool.hatch.build.targets.wheel]` with `artifacts` + `exclude` to pyproject.toml per step-2. Include `package*.json`, `.prettierrc`, `.prettierignore` in exclude list.
6. Create `.prettierignore` with `src/routeTree.gen.ts` to prevent formatting auto-generated file.
7. Commit `routeTree.gen.ts` to git (simplifies CI, matches TanStack recommendation).
8. Add frontend-specific `.gitignore` at `llm_pipeline/ui/frontend/.gitignore` for patterns not covered by root (`.vite/`, `*.tsbuildinfo`, `.env.local`).
9. Verify TanStack Router plugin export name from `node_modules` d.ts file before finalizing vite.config.ts.
10. Note Vite 7 deviation from task 29 description in implementation docs.
