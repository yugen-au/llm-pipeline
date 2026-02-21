# Architecture Review

## Overall Assessment
**Status:** complete
Implementation correctly sets up TanStack Router file-based routing with all required routes, Zod search params, design tokens, and code style. Route tree auto-generation verified. Two medium issues found around search param schema inconsistency and a CSS layout quirk; neither blocks approval.

## Project Guidelines Compliance
**CLAUDE.md:** `D:\Documents\claude-projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| No semicolons | pass | All 7 route/config files verified; zero semicolons |
| Single quotes | pass | All string literals use single quotes |
| Named functions (not arrows) | pass | RootLayout, IndexPage, RunDetailPage, LivePage, PromptsPage, PipelinesPage |
| Design tokens (no raw gray classes) | pass | bg-background, text-foreground, bg-sidebar, border-sidebar-border, bg-card, text-card-foreground, text-muted-foreground used throughout |
| No hardcoded values | pass | apiPort/devPort from env vars; no magic strings beyond placeholder text |
| Error handling present | pass | N/A for placeholder routes; Zod fallback() handles invalid search params gracefully |
| 2-space indent per .prettierrc | pass | All files use 2-space indentation |

## Issues Found
### Critical
None

### High
None

### Medium
#### Inconsistent search param schema pattern between index.tsx and $runId.tsx
**Step:** 4
**Details:** `index.tsx` uses `fallback().optional()` while `$runId.tsx` uses `fallback().default()`. Context7 docs consistently recommend `fallback().default()` as the production pattern. With `.optional()`, parsing `{}` returns `{page: undefined, status: undefined}`, forcing consumers to handle undefined. With `.default()`, parsing `{}` returns `{page: 1, status: ''}`. The `$runId.tsx` approach is correct per docs; `index.tsx` should match. Recommend changing `index.tsx` schema to: `page: fallback(z.number().int().min(1), 1).default(1)` and `status: fallback(z.string(), '').default('')` (dropping `.optional()`). This prevents undefined-handling bugs when task 31 wires up the API hooks.

#### min-h-screen on index.tsx is ineffective inside root layout
**Step:** 4
**Details:** `index.tsx` uses `min-h-screen` (100vh) but it renders inside `__root.tsx`'s `<main className="flex-1 overflow-auto">` which is constrained by the parent `h-screen`. The `min-h-screen` creates a 100vh-tall scrollable region inside the main area rather than vertically centering within the visible area. Should use `min-h-full` or `h-full` instead to fill the available main content area, not the viewport. Visual impact is minor since this is placeholder content replaced by task 31.

### Low
#### Zod 4 installed against @tanstack/zod-adapter peer dep of zod ^3.23.8
**Step:** 1
**Details:** `@tanstack/zod-adapter@1.161.3` declares `peerDependencies: {"zod": "^3.23.8"}` but `zod@4.3.6` is installed. Runtime testing confirms the core APIs used (`z.object`, `z.string`, `z.number`, `fallback`) work correctly. Implementation step-1 doc acknowledges this and notes zod 4 ships a `zod/v3` compat layer. Low risk currently but could cause subtle breakage if future code uses APIs that diverged between zod 3 and 4. Monitor when upgrading @tanstack/zod-adapter.

#### Placeholder text in root sidebar is not internationalization-ready
**Step:** 3
**Details:** `"Sidebar (task 41)"` is hardcoded English placeholder text. Acceptable for a placeholder that task 41 replaces entirely. No action needed now but noting for completeness.

## Review Checklist
[x] Architecture patterns followed -- file-based routing, clean separation of routes, layout shell with Outlet pattern
[x] Code quality and maintainability -- consistent structure across all route files, named functions, minimal imports
[x] Error handling present -- Zod fallback() provides safe defaults for invalid/missing search params
[x] No hardcoded values -- env vars for ports, design tokens for colors, Zod schemas for validation
[x] Project conventions followed -- no semicolons, single quotes, 2-space indent, design tokens
[x] Security considerations -- no sensitive data exposure, search params validated via Zod schema
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- minimal placeholder content, no premature abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `llm_pipeline/ui/frontend/vite.config.ts` | pass | autoCodeSplitting: true correctly added to tanstackRouter plugin |
| `llm_pipeline/ui/frontend/src/routes/__root.tsx` | pass | Flex layout with sidebar aside and main Outlet; all design tokens |
| `llm_pipeline/ui/frontend/src/routes/index.tsx` | pass* | Search params work but use .optional() instead of .default() per docs; min-h-screen ineffective in layout |
| `llm_pipeline/ui/frontend/src/routes/runs/$runId.tsx` | pass | Correct fallback().default() pattern, useParams/useSearch, design tokens |
| `llm_pipeline/ui/frontend/src/routes/live.tsx` | pass | Clean placeholder with design tokens |
| `llm_pipeline/ui/frontend/src/routes/prompts.tsx` | pass | Clean placeholder with design tokens |
| `llm_pipeline/ui/frontend/src/routes/pipelines.tsx` | pass | Clean placeholder with design tokens |
| `llm_pipeline/ui/frontend/src/routeTree.gen.ts` | pass | All 6 routes present: /, /live, /pipelines, /prompts, /runs/$runId, __root__ |
| `llm_pipeline/ui/frontend/package.json` | pass | zod and @tanstack/zod-adapter in dependencies (not devDependencies) |

## New Issues Introduced
- Zod 4 peer dependency mismatch with @tanstack/zod-adapter (functional but technically unsatisfied)
- index.tsx search param schema uses .optional() instead of .default(), inconsistent with $runId.tsx and Context7 docs

## Recommendation
**Decision:** CONDITIONAL
Approve with two recommended fixes before merge: (1) Change index.tsx search schema from `fallback().optional()` to `fallback().default()` to match $runId.tsx and Context7 recommended pattern. (2) Change index.tsx `min-h-screen` to `min-h-full` or `h-full`. Both are quick one-line changes. The zod 4 peer dep issue is accepted as-is since it works at runtime and the adapter will likely update its peer dep range soon.
