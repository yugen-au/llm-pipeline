# PLANNING

## Summary

Set up TanStack Router file-based routing in `llm_pipeline/ui/frontend/`. Work includes: installing `zod` and `@tanstack/zod-adapter` as production deps, enabling `autoCodeSplitting` in vite.config.ts, updating `__root.tsx` with a dark-themed sidebar layout shell using design tokens, creating four new route files (`live.tsx`, `prompts.tsx`, `pipelines.tsx`, `runs/$runId.tsx`), updating `index.tsx` with minimal Zod search params (page/status), adding tab search param to `runs/$runId.tsx`, and verifying routeTree.gen.ts auto-regeneration. No changes to `main.tsx` or `router.ts` are needed.

## Plugin & Agents

**Plugin:** frontend-mobile-development, javascript-typescript
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Dependencies**: Install `zod` and `@tanstack/zod-adapter` as production deps
2. **Vite Config**: Enable `autoCodeSplitting: true` in tanstackRouter plugin options
3. **Root Layout**: Update `__root.tsx` with sidebar shell using design tokens
4. **Route Files**: Create `live.tsx`, `prompts.tsx`, `pipelines.tsx`, `runs/$runId.tsx`; update `index.tsx` with search params
5. **Verify**: Confirm routeTree.gen.ts regenerates correctly with all routes

## Architecture Decisions

### Flat pipelines.tsx vs directory structure
**Choice:** `pipelines.tsx` flat file at `src/routes/pipelines.tsx`
**Rationale:** CEO confirmed. No nested routes under `/pipelines` in tasks 31, 32, or 41. Consistent with `live.tsx` and `prompts.tsx`.
**Alternatives:** `pipelines/index.tsx` directory structure (same URL, overkill for current scope)

### autoCodeSplitting: true
**Choice:** Enable `autoCodeSplitting: true` in `tanstackRouter({ autoCodeSplitting: true })` in vite.config.ts
**Rationale:** Context7 docs confirm this is recommended; automatically lazy-chunks route components/loaders without manual `.lazy.tsx` files. Single line change.
**Alternatives:** Manual `.lazy.tsx` files (verbose, not needed), omitting entirely (loses performance optimization)

### Root layout sidebar shell (placeholder)
**Choice:** `__root.tsx` renders a flex layout with `<aside>` using `bg-sidebar` token and `<main>` using `bg-background` token; no interactive logic
**Rationale:** Task 41 (Sidebar component) depends on task 30; placeholder prevents task 41 from needing to restructure layout. Design tokens from OKLCH system in `index.css` must be used, not raw gray classes (validated in VALIDATED_RESEARCH.md).
**Alternatives:** Full sidebar in task 30 (out of scope, task 41 owns it); raw gray classes (contradicts design system on disk)

### Minimal Zod search params
**Choice:** `index.tsx` gets `{ page: z.number().int().min(1).optional(), status: z.string().optional() }`; `runs/$runId.tsx` gets `{ tab: z.string().optional() }`
**Rationale:** CEO confirmed minimal skeletons. Full schemas deferred to task 31+ when API response shapes are defined. `fallback()` from `@tanstack/zod-adapter` provides safe defaults.
**Alternatives:** Comprehensive schemas upfront (premature, would conflict with task 31 API hook shapes)

### No tsr.config.json
**Choice:** Pass all tanstackRouter options directly in vite.config.ts
**Rationale:** Minimizes config files per VALIDATED_RESEARCH.md recommendation. Current vite.config.ts already uses this pattern with no tsr.config.json on disk.
**Alternatives:** Separate tsr.config.json (unnecessary indirection)

## Implementation Steps

### Step 1: Install production dependencies
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** A

1. In `llm_pipeline/ui/frontend/`, run `npm install zod @tanstack/zod-adapter`
2. Verify both appear in `package.json` under `dependencies` (not `devDependencies`)

### Step 2: Enable autoCodeSplitting in vite.config.ts
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** A

1. Edit `llm_pipeline/ui/frontend/vite.config.ts`
2. Change `tanstackRouter()` to `tanstackRouter({ autoCodeSplitting: true })` on line 11

### Step 3: Update __root.tsx with sidebar layout shell
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** B

1. Edit `llm_pipeline/ui/frontend/src/routes/__root.tsx`
2. Replace the current pass-through component with a flex layout:
   - Outer div: `flex h-screen bg-background text-foreground overflow-hidden`
   - `<aside>`: `w-60 shrink-0 bg-sidebar border-r border-sidebar-border` with placeholder text (task 41 replaces this)
   - `<main>`: `flex-1 overflow-auto` containing `<Outlet />`
3. Keep imports: `createRootRoute`, `Outlet` from `@tanstack/react-router`
4. Use named function component `function RootLayout() {}`
5. No semicolons, single quotes, 2-space indent per `.prettierrc`

### Step 4: Update index.tsx with Zod search params
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** B

1. Edit `llm_pipeline/ui/frontend/src/routes/index.tsx`
2. Add imports: `z` from `'zod'`, `zodValidator` from `'@tanstack/zod-adapter'`
3. Define search schema: `const runListSearchSchema = z.object({ page: fallback(z.number().int().min(1), 1).optional(), status: fallback(z.string(), '').optional() })`
4. Add `validateSearch: zodValidator(runListSearchSchema)` to `createFileRoute('/')({...})`
5. Keep existing `IndexPage` component body; add `Route.useSearch()` call as placeholder (or leave for task 31 to use)
6. Named function, no semicolons, single quotes

### Step 5: Create runs/$runId.tsx
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** B

1. Create directory `llm_pipeline/ui/frontend/src/routes/runs/`
2. Create `llm_pipeline/ui/frontend/src/routes/runs/$runId.tsx`
3. Use `createFileRoute('/runs/$runId')({...})` pattern
4. Add Zod search params: `tab: fallback(z.string(), 'steps').optional()`
5. Named function `function RunDetailPage() {}` with placeholder content using design tokens (`bg-card`, `text-card-foreground`)
6. Access `runId` via `Route.useParams()` in component body for type-safety demonstration
7. No semicolons, single quotes

### Step 6: Create live.tsx, prompts.tsx, pipelines.tsx
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/routes/live.tsx`
   - `createFileRoute('/live')({...})`
   - Named function `function LivePage() {}` with placeholder `<div>` using design tokens
2. Create `llm_pipeline/ui/frontend/src/routes/prompts.tsx`
   - `createFileRoute('/prompts')({...})`
   - Named function `function PromptsPage() {}` with placeholder content
3. Create `llm_pipeline/ui/frontend/src/routes/pipelines.tsx`
   - `createFileRoute('/pipelines')({...})`
   - Named function `function PipelinesPage() {}` with placeholder content
4. All files: no semicolons, single quotes, minimal imports

### Step 7: Verify routeTree.gen.ts regeneration
**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Run `npm run dev` (or `npm run build`) in `llm_pipeline/ui/frontend/` to trigger TanStack Router Vite plugin codegen
2. Verify `src/routeTree.gen.ts` now includes all 6 routes: `/`, `/live`, `/prompts`, `/pipelines`, `/runs/$runId`, plus root
3. Confirm TypeScript compilation succeeds (`npm run type-check`)
4. Stop dev server after verification

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| routeTree.gen.ts not regenerating on Windows (chokidar watcher) | Medium | Run `npm run build` as fallback to force codegen; restart dev server if needed |
| `fallback` import from `@tanstack/zod-adapter` API mismatch | Medium | Verify against Context7 docs (/tanstack/router) before writing; use `zodValidator` wrapping `z.object()` with `.catch()` as fallback if `fallback()` unavailable in installed version |
| Step groups B conflict (multiple files edited concurrently) | Low | Steps 3-6 are all Group B but touch different files; no overlap except index.tsx (step 4 only) |
| Task 41 raw gray classes conflict with design tokens | Low | Task 41 description notes this deviation; note in implementation to flag when task 41 starts |
| `zod`/`@tanstack/zod-adapter` version incompatibility | Low | Both are peer-compatible with TanStack Router 1.161.x per docs; install latest |

## Success Criteria

- [ ] `zod` and `@tanstack/zod-adapter` listed in `package.json` dependencies (not devDependencies)
- [ ] `vite.config.ts` has `tanstackRouter({ autoCodeSplitting: true })`
- [ ] `src/routes/__root.tsx` renders flex layout with sidebar `<aside>` and `<main><Outlet /></main>` using design tokens
- [ ] `src/routes/index.tsx` has `validateSearch` with page/status Zod schema
- [ ] `src/routes/runs/$runId.tsx` exists with tab search param and `Route.useParams()`
- [ ] `src/routes/live.tsx`, `prompts.tsx`, `pipelines.tsx` all exist with placeholder components
- [ ] `src/routeTree.gen.ts` contains all 6 routes after running build/dev
- [ ] `npm run type-check` passes with no errors
- [ ] All new/modified files use design tokens (bg-sidebar, bg-background, etc.), not raw gray classes
- [ ] All files follow code style: no semicolons, single quotes, named functions

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All decisions validated and confirmed by CEO. No external API integration. Pure file creation and config changes. Existing routeTree.gen.ts auto-generation already proven to work on this machine (task 29). The only non-trivial risk is the Windows file watcher, mitigated by the build fallback.
**Suggested Exclusions:** testing, review
