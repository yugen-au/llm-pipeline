# Research Summary

## Executive Summary

Both research files are well-sourced and largely consistent. Cross-validated against on-disk codebase state, Context7 TanStack Router docs, and Graphiti memory. Two minor contradictions found and resolved (pipelines route structure, CSS class usage). CEO confirmed minimal search param schemas and flat pipelines route. No blockers -- ready for planning.

## Domain Findings

### TanStack Router File-Based Routing Setup
**Source:** step-1, step-2, Context7 /tanstack/router

- Plugin order `tanstackRouter() -> react() -> tailwindcss()` already correct on disk
- `autoCodeSplitting: true` confirmed as recommended approach by Context7 docs -- automatically splits component/loader/errorComponent into lazy chunks without manual `.lazy.tsx` files
- `target: 'react'` option unnecessary (react is default) but harmless if added
- routeTree.gen.ts auto-regeneration confirmed working -- current file on disk matches expected codegen output for 2 routes (root + index)
- Route file naming conventions validated: `$param.tsx` for dynamic segments, `__root.tsx` for root, `index.tsx` for index routes

### Proposed Route Structure
**Source:** step-1, step-2

Target routes validated against task 30 requirements:
| File | URL | Status |
|---|---|---|
| `__root.tsx` | (layout) | MODIFY existing |
| `index.tsx` | `/` | MODIFY existing |
| `runs/$runId.tsx` | `/runs/$runId` | CREATE |
| `live.tsx` | `/live` | CREATE |
| `prompts.tsx` | `/prompts` | CREATE |
| `pipelines.tsx` | `/pipelines` | CREATE (see contradiction below) |

No `runs/index.tsx` needed -- root `index.tsx` at `/` serves as run list. Confirmed correct.

### Zod Search Params Integration
**Source:** step-1, Context7 /tanstack/router

Pattern validated against Context7 docs:
- `zodValidator(schema)` wraps Zod schema for `validateSearch` -- confirmed
- `fallback(z.type(), default)` from `@tanstack/zod-adapter` -- confirmed as correct API for safe URL param defaults
- `Route.useSearch()` hook for type-safe access -- confirmed
- Dependencies: `zod` + `@tanstack/zod-adapter` as production deps -- confirmed needed (zod only exists as transitive dep currently)

### CSS Design Tokens
**Source:** step-2, verified on disk (src/index.css)

- Full OKLCH token system present with sidebar-specific tokens: `--sidebar`, `--sidebar-foreground`, `--sidebar-primary`, `--sidebar-accent`, `--sidebar-border`, `--sidebar-ring`
- Tailwind v4 `@theme inline` maps CSS vars to utility classes (e.g., `bg-sidebar`, `text-sidebar-foreground`)
- Dark mode via `.dark` class (set in main.tsx)
- Research correctly identifies: use `bg-background`/`bg-sidebar` tokens, NOT raw `bg-gray-900`/`bg-gray-800`

### Existing Code Style
**Source:** step-2, verified on disk (.prettierrc, eslint.config.ts)

- No semicolons, single quotes, trailing commas, 2-space indent, 100 char width
- Named function components (not arrow): `function PageName() {}`
- `createFileRoute('/path')({...})` pattern with `export const Route =`

## Contradictions Found

### 1. Pipelines Route: Flat File vs Directory
**Step 1** proposes `pipelines.tsx` (flat file -> `/pipelines`).
**Step 2** proposes `pipelines/index.tsx` (directory with index -> `/pipelines`).

Both produce the same URL. No nested routes under `/pipelines` are planned in any downstream task (31, 32, 41). Flat file is consistent with `live.tsx` and `prompts.tsx`.

**Resolution:** CEO confirmed flat `pipelines.tsx`. Use for consistency. Switch to directory structure only if nested routes are needed later.

### 2. Task Description CSS vs Actual Design System
**Task 30 description** uses `bg-gray-900 text-gray-100` in the root layout code sample.
**Research (both steps)** correctly identifies the OKLCH token system already in place.

**Resolution:** Research is correct. Implementation must use design tokens (`bg-background`, `bg-sidebar`, etc.), overriding the task description's raw gray classes. No CEO input needed -- design system on disk is authoritative.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Should search param schemas be minimal (key params only, expandable later) or comprehensive (all anticipated params from step-1 section 6)? | Minimal skeletons -- page/status for run list, tab for run detail. Expand as features develop. | Task 30 implements only core params; full schemas deferred to API integration (task 31+) |
| Confirm pipelines route as flat `pipelines.tsx` (not `pipelines/index.tsx`)? | Flat `pipelines.tsx` -- consistent with other top-level routes, simpler. | Use `pipelines.tsx` matching `live.tsx`/`prompts.tsx` pattern |

## Assumptions Validated
- [x] TanStack Router plugin order (before react) -- confirmed on disk and in Context7 docs
- [x] autoCodeSplitting is the recommended approach -- confirmed by Context7 docs
- [x] routeTree.gen.ts auto-regenerates on file changes during dev -- confirmed by existing working codegen
- [x] Zod + @tanstack/zod-adapter needed as production deps -- confirmed not installed, only transitive
- [x] zodValidator + fallback API pattern -- confirmed by Context7 docs (multiple examples)
- [x] Root layout owns sidebar shell, actual Sidebar component deferred to task 41 -- confirmed by task dependency chain (41 depends on 30 + 32)
- [x] Design tokens (bg-background, bg-sidebar) must be used over raw gray classes -- confirmed by index.css OKLCH system
- [x] No semicolons / single quotes / named functions code style -- confirmed by .prettierrc on disk
- [x] router.ts Register module augmentation pattern is correct -- confirmed on disk
- [x] QueryClientProvider wraps RouterProvider in entry point -- confirmed in main.tsx

## Open Items
- Windows file watcher: Vite uses chokidar for file watching; generally reliable on Windows but if routeTree.gen.ts doesn't regenerate during dev, manual restart of dev server may be needed
- TanStack Router DevTools: step 1 mentions optional `@tanstack/router-devtools` -- not a task 30 requirement, can be added opportunistically during implementation
- Task 41 description uses raw gray classes (bg-gray-800) -- downstream task will need updating to use design tokens when it starts

## Recommendations for Planning
1. Use `pipelines.tsx` (flat file) -- CEO confirmed, keeps all top-level routes consistent
2. Minimal search param schemas: page/status for run list, tab for run detail -- CEO confirmed, expand when API hooks (task 31) define actual response shapes
3. Enable `autoCodeSplitting: true` in vite.config.ts -- single line change, confirmed best practice
4. Root layout: placeholder `<aside>` with `bg-sidebar` token, no interactivity -- task 41 replaces with full Sidebar component
5. Each route file: minimal placeholder component following existing code style (named function, design tokens, consistent structure)
6. Verify routeTree.gen.ts regeneration after creating all route files -- run `npm run dev` and check output
7. Do NOT add `tsr.config.json` -- pass options directly in vite.config.ts to minimize config files
