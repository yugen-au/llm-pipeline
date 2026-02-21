# PLANNING

## Summary

Scaffold a React 19 + TypeScript + Vite 7 frontend at `llm_pipeline/ui/frontend/` and wire it into the Python package. Work covers project scaffolding, TanStack Router + Query setup, TailwindCSS v4 CSS-first config, shadcn/ui init (new-york/neutral), Zustand, Vite proxy to localhost:8642, ESLint 9 flat config + Prettier, and hatchling `artifacts` directive in pyproject.toml. Task 30 (routes) and 42 (theme tokens) are downstream and explicitly out of scope.

## Plugin & Agents

**Plugin:** frontend-mobile-development, python-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. Project Scaffold: Run `npm create vite@latest` to create the Vite + React-TS project skeleton, then replace/extend generated files with all required config (tsconfig 3-file pattern, vite.config.ts, .gitignore, .prettierrc, .prettierignore, eslint.config.ts, index.css).
2. Package Wiring: Add `[tool.hatch.build.targets.wheel]` with `artifacts` + `exclude` to pyproject.toml so `dist/` is included in the wheel.
3. shadcn Init: Run `npx shadcn@latest init` interactively (new-york, neutral, CSS variables, rsc:false) to generate `components.json` and update `src/index.css`.

## Architecture Decisions

### TypeScript Config Pattern
**Choice:** 3-file tsconfig pattern (`tsconfig.json` + `tsconfig.app.json` + `tsconfig.node.json`)
**Rationale:** Matches Vite 7 scaffold output exactly. `tsconfig.json` acts as solution file with project references; `tsconfig.app.json` targets DOM/JSX app code; `tsconfig.node.json` targets config files (vite.config.ts, eslint.config.ts). Validated in VALIDATED_RESEARCH.md step-1.
**Alternatives:** 2-file pattern (step-3 research) -- rejected, does not match scaffold output and complicates project references.

### Tailwind v4 CSS-First Config
**Choice:** `@import "tailwindcss"` + `@custom-variant dark` in `src/index.css`, no `tailwind.config.ts`
**Rationale:** Tailwind v4 eliminates the JS config file entirely. Config lives in CSS via `@theme inline`. Class-based dark mode uses `@custom-variant dark (&:where(.dark, .dark *))`. OKLCH color format. `tw-animate-css` replaces deprecated `tailwindcss-animate`. Validated in VALIDATED_RESEARCH.md step-1.
**Alternatives:** Tailwind v3 approach (`tailwind.config.ts`, `@tailwind` directives) -- rejected, incompatible with v4.

### Vite Proxy: Dynamic Port via Env Vars
**Choice:** Proxy config reads `process.env.VITE_API_PORT` at Vite startup (step-3 approach)
**Rationale:** `cli.py` line 155 passes `VITE_API_PORT` as env var to the Vite subprocess at runtime. Hardcoding 8642 would break if user passes `--port`. API routes at `/api`, WebSocket at `/ws` (no `/api` prefix per app.py line 80).
**Alternatives:** Hardcoded port (step-1 research) -- rejected, broken for non-default ports.

### Hatchling Artifacts (NOT shared-data)
**Choice:** `[tool.hatch.build.targets.wheel]` with `artifacts = ["llm_pipeline/ui/frontend/dist/**"]`
**Rationale:** `artifacts` overrides gitignore so `dist/` (normally gitignored) is included in the wheel. `shared-data` installs to `{prefix}/share/` which is wrong -- `cli.py` resolves dist via `Path(__file__).parent / "frontend" / "dist"` requiring it inside the package. Validated in VALIDATED_RESEARCH.md step-2.
**Alternatives:** `shared-data` directive -- rejected, installs to wrong path.

### shadcn Init: Interactive CLI (Not Automated)
**Choice:** `npx shadcn@latest init` run manually as part of the implementation step
**Rationale:** shadcn/ui is not an npm package dependency; it scaffolds components via CLI. The init is interactive but its output (`components.json`, updated `src/index.css`, auto-installed npm deps) must be committed. Must run AFTER Tailwind/Vite/path-alias setup because it modifies `src/index.css`. Validated in VALIDATED_RESEARCH.md step-1.
**Alternatives:** Pre-configuring `components.json` manually -- possible but error-prone given shadcn's version-specific output format.

### TanStack Router Plugin Export Name
**Choice:** Verify export name from `node_modules/@tanstack/router-plugin/dist/vite.d.ts` at implementation time; use `tanstackRouter` (lowercase) for >= v1.150.x
**Rationale:** Export name changed from `TanStackRouterVite` (v1.114.3) to `tanstackRouter` (>= v1.150.x). Research confirmed v1.161.3 is installed, so `tanstackRouter` expected. Must confirm from d.ts file. Validated in VALIDATED_RESEARCH.md appendix B.
**Alternatives:** Assume `TanStackRouterVite` -- rejected, would cause runtime import error on v1.161.x.

## Implementation Steps

### Step 1: Scaffold Vite Project
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitejs/vite
**Group:** A

1. From `llm_pipeline/ui/`, run `npm create vite@latest frontend -- --template react-ts` to scaffold the Vite 7 + React 19 + TypeScript project at `llm_pipeline/ui/frontend/`.
2. From `llm_pipeline/ui/frontend/`, run `npm install` to install scaffold dependencies.
3. Delete scaffold placeholder files not needed: `src/App.css`, `src/App.tsx`, `src/assets/react.svg`, `public/vite.svg`.
4. Create `llm_pipeline/ui/frontend/.gitignore` with entries: `dist/`, `node_modules/`, `.vite/`, `*.tsbuildinfo`, `.env.local`, `.env.*.local`.

### Step 2: Install npm Dependencies
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/router, /shadcn-ui/ui
**Group:** B

1. From `llm_pipeline/ui/frontend/`, install runtime deps: `npm install @tanstack/react-router @tanstack/react-query zustand`.
2. Install Tailwind v4 deps: `npm install tailwindcss @tailwindcss/vite`.
3. Install dev deps: `npm install -D @tanstack/router-plugin @tanstack/react-query-devtools typescript-eslint @eslint/js eslint-plugin-react-hooks eslint-plugin-react-refresh eslint-config-prettier prettier`.
4. Do NOT install shadcn npm packages directly -- they are installed by `npx shadcn@latest init` in Step 5.

### Step 3: Configure TypeScript (3-File Pattern)
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitejs/vite
**Group:** C

1. Replace `llm_pipeline/ui/frontend/tsconfig.json` with solution file containing `references` to `tsconfig.app.json` and `tsconfig.node.json`, plus `compilerOptions.paths: {"@/*": ["./src/*"]}` for path alias.
2. Replace `llm_pipeline/ui/frontend/tsconfig.app.json` with app config: `target: "ES2020"`, `lib: ["ES2020","DOM","DOM.Iterable"]`, `jsx: "react-jsx"`, `moduleResolution: "bundler"`, `verbatimModuleSyntax: true`, `noEmit: true`, `strict: true`, `paths: {"@/*": ["./src/*"]}`.
3. Replace `llm_pipeline/ui/frontend/tsconfig.node.json` with node config targeting vite.config.ts and eslint.config.ts: `moduleResolution: "bundler"`, no DOM lib, `noEmit: true`.

### Step 4: Configure Vite (vite.config.ts)
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /vitejs/vite, /tanstack/router
**Group:** C

1. Check `node_modules/@tanstack/router-plugin/dist/vite.d.ts` to confirm export name (`tanstackRouter` or `TanStackRouterVite`).
2. Replace `llm_pipeline/ui/frontend/vite.config.ts` with config that includes: `tanstackRouter()` plugin FIRST (before `react()`), `react()` plugin, `tailwindcss()` plugin from `@tailwindcss/vite`.
3. Add `resolve.alias: {"@": path.resolve(__dirname, "./src")}` to vite config.
4. Add `build.outDir: "dist"` to vite config (explicit, matches `cli.py` expectation).
5. Add `server.proxy` config reading `process.env.VITE_API_PORT` (default `"8642"`): `/api` -> `http://localhost:${apiPort}` with `changeOrigin: true`, `/ws` -> `ws://localhost:${apiPort}` with `ws: true`.
6. Add `server.port` reading `process.env.VITE_PORT` (default `"5173"`).

### Step 5: Configure TailwindCSS v4 + index.css
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tailwindlabs/tailwindcss.com
**Group:** C

1. Replace `llm_pipeline/ui/frontend/src/index.css` with v4 CSS-first config: `@import "tailwindcss"`, `@custom-variant dark (&:where(.dark, .dark *))` for class-based dark mode, `@theme inline` block (empty for now -- shadcn will extend it in Step 6).
2. Do NOT create `tailwind.config.ts` -- v4 has no JS config file.
3. Ensure `@import "tw-animate-css"` is NOT added yet -- shadcn init adds it automatically in Step 6.

### Step 6: Run shadcn/ui Init
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** D

1. From `llm_pipeline/ui/frontend/`, run `npx shadcn@latest init` interactively. Select: style=new-york, base color=neutral, CSS variables=yes, rsc=no (Vite, not Next.js).
2. Verify `components.json` is created with `style: "new-york"`, `tailwind.baseColor: "neutral"`, `tailwind.cssVariables: true`, `rsc: false`.
3. Verify `src/index.css` now contains OKLCH CSS variables in `:root` and `.dark` selectors, plus `@import "tw-animate-css"`.
4. Verify auto-installed npm packages: `tw-animate-css`, `class-variance-authority`, `clsx`, `tailwind-merge`, `lucide-react`.
5. Commit `components.json` and updated `src/index.css` (shadcn components are not committed here -- only the config).

### Step 7: Configure ESLint 9 + Prettier
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. Create `llm_pipeline/ui/frontend/eslint.config.ts` with ESLint 9 flat config: import `@eslint/js`, `typescript-eslint`, `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh`, `eslint-config-prettier`. Apply `eslint-config-prettier` last. Add ignores for `dist/` and `src/routeTree.gen.ts`.
2. Create `llm_pipeline/ui/frontend/.prettierrc` with: `semi: false`, `singleQuote: true`, `trailingComma: "all"`, `tabWidth: 2`, `printWidth: 100`.
3. Create `llm_pipeline/ui/frontend/.prettierignore` with: `src/routeTree.gen.ts`, `dist/`.

### Step 8: Create src/ Entry Files
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** E

1. Create `llm_pipeline/ui/frontend/src/main.tsx` as React 19 entry point: `createRoot(document.getElementById("root")!)`, wrapped with `QueryClientProvider` (TanStack Query) and `RouterProvider` (TanStack Router). Apply `dark` class to `document.documentElement` for default dark mode.
2. Create `llm_pipeline/ui/frontend/src/router.ts` initializing TanStack Router: `createRouter({ routeTree })` importing the auto-generated `routeTree.gen.ts`. Export as `router` with TypeScript module augmentation for `Register`.
3. Create `llm_pipeline/ui/frontend/src/queryClient.ts` exporting a shared `QueryClient` instance with sensible defaults (staleTime, retry).
4. Create minimal `llm_pipeline/ui/frontend/src/routes/__root.tsx` with `createRootRoute` exporting a bare `<Outlet />` (full layout is task 30's scope).
5. Create `llm_pipeline/ui/frontend/src/routes/index.tsx` with `createFileRoute("/")` and a placeholder component (unblocks router codegen).
6. Run `npm run dev` briefly to trigger TanStack Router codegen of `src/routeTree.gen.ts`, then stop. Commit `routeTree.gen.ts`.

### Step 9: Update package.json Scripts
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. Update `llm_pipeline/ui/frontend/package.json` scripts to ensure: `"dev": "vite"`, `"build": "tsc -b && vite build"`, `"preview": "vite preview"`, `"lint": "eslint ."`, `"type-check": "tsc -b --noEmit"`.

### Step 10: Update pyproject.toml (Hatchling Artifacts)
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /pypa/hatch
**Group:** F

1. Add to `pyproject.toml` the `[tool.hatch.build.targets.wheel]` section with `packages = ["llm_pipeline"]` and `artifacts = ["llm_pipeline/ui/frontend/dist/**"]`.
2. Add `exclude` list to the same section covering: `llm_pipeline/ui/frontend/node_modules/**`, `llm_pipeline/ui/frontend/src/**`, `llm_pipeline/ui/frontend/.vite/**`, `llm_pipeline/ui/frontend/tsconfig*`, `llm_pipeline/ui/frontend/vite.config*`, `llm_pipeline/ui/frontend/components.json`, `llm_pipeline/ui/frontend/eslint*`, `llm_pipeline/ui/frontend/.eslint*`, `llm_pipeline/ui/frontend/.prettierrc`, `llm_pipeline/ui/frontend/.prettierignore`, `llm_pipeline/ui/frontend/package*.json`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `npx shadcn@latest init` is interactive; cannot be fully automated | Medium | Document exact prompts and answers. Agent runs interactively. Commit all generated output. |
| TanStack Router export name mismatch (`tanstackRouter` vs `TanStackRouterVite`) | Medium | Check `node_modules/@tanstack/router-plugin/dist/vite.d.ts` before writing vite.config.ts (Step 4, substep 1). |
| Vite 7 requires Node 20+; CI may run Node 18 | Low | Note in implementation. Node 18 EOL'd Apr 2025; low probability in active CI environments. |
| shadcn init modifies `src/index.css` -- order matters | Medium | Steps are sequenced: Tailwind config in Step 5, shadcn init in Step 6 (group D after C). |
| `routeTree.gen.ts` not generated until first `vite dev` run | Low | Step 8 substep 6 explicitly runs dev briefly to trigger codegen and commits the file. |
| pyproject.toml `[tool.hatch.build.targets.wheel]` section may conflict with any future additions | Low | Section did not exist before task 28 (confirmed). No conflicts expected. |
| Task 42 downstream references Tailwind v3 patterns -- may confuse implementer | Low | Out of scope for task 29. Documented in VALIDATED_RESEARCH.md open items. Task 42 details will need updating separately. |

## Success Criteria

- [ ] `llm_pipeline/ui/frontend/` directory exists with valid `package.json` referencing Vite 7, React 19, TypeScript 5.7.x.
- [ ] `npm run build` in `llm_pipeline/ui/frontend/` succeeds and produces `dist/` directory.
- [ ] `npm run type-check` exits 0 (no TypeScript errors).
- [ ] `npm run lint` exits 0 (no ESLint errors).
- [ ] `vite.config.ts` proxies `/api` and `/ws` to `localhost:${VITE_API_PORT}` (default 8642).
- [ ] `components.json` exists with `style: "new-york"`, `tailwind.baseColor: "neutral"`, `rsc: false`.
- [ ] `src/index.css` contains `@import "tailwindcss"` and OKLCH CSS variables from shadcn init.
- [ ] `src/routeTree.gen.ts` committed and valid.
- [ ] `pyproject.toml` contains `[tool.hatch.build.targets.wheel]` with `artifacts` directive covering `dist/**`.
- [ ] `python -m build` (wheel) completes without error and does not bundle `node_modules/` or `src/`.
- [ ] `llm-pipeline ui` (prod mode, no dist) prints WARNING about missing frontend without crashing.
- [ ] `llm-pipeline ui --dev` starts Vite subprocess from `frontend/` without error.

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** shadcn init is interactive (cannot be fully automated), TanStack Router export name must be verified at runtime, and the correct ordering of steps (Tailwind before shadcn) is critical. These create moderate implementation risk but all mitigations are documented. No architectural unknowns remain.
**Suggested Exclusions:** review
