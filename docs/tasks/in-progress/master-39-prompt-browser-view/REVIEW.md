# Architecture Review

## Overall Assessment
**Status:** complete
Solid implementation. All 5 steps follow established codebase patterns closely. Architecture decisions (client-side pipeline cross-reference, URL param selection, React element highlighting) are correctly implemented. No security issues, no hardcoded values, proper error/loading/empty states throughout. A few minor consistency deviations noted.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| No semicolons (Prettier `semi: false`) | pass | All 6 files use no semicolons |
| Single quotes (Prettier `singleQuote: true`) | pass | All string literals use single quotes |
| Named function components | pass | All components use `function Name()` syntax, no arrow function components |
| `export function` for custom components | fail | PromptViewer uses `export { PromptViewer }` at bottom instead of `export function PromptViewer` at declaration -- deviates from project convention (all non-UI components use direct export) |
| TanStack Query patterns (queryKeys factory) | pass | `queryKeys.prompts.detail` follows exact `as const` pattern |
| shadcn/ui component usage | pass | All imports from `@/components/ui/` |
| Error: `text-sm text-destructive` | pass | Both PromptList and PromptViewer use this pattern |
| Empty: `text-sm text-muted-foreground` | pass | Matches existing codebase pattern |
| Loading: `animate-pulse rounded bg-muted` | pass | Both components use this skeleton pattern |
| ALL_SENTINEL pattern | pass | Exact match with FilterBar.tsx pattern |
| Monospace pre styling | pass | `whitespace-pre-wrap break-all rounded-md bg-muted p-3 text-xs` matches StepDetailPanel |
| `@/` path alias | pass | All imports use `@/` prefix |
| printWidth 100 | pass | No lines exceed 100 chars |

## Issues Found
### Critical
None

### High
None

### Medium
#### PromptViewer export style deviates from project convention
**Step:** 4
**Details:** `PromptViewer` is declared as `function PromptViewer(...)` but exported via `export { PromptViewer }` at the bottom of the file (line 138). Every other non-UI custom component in the codebase uses `export function` at the declaration site (FilterBar, PromptFilterBar, PromptList, ContextEvolution, StepTimeline, etc.). The `export { }` pattern is reserved for shadcn/ui primitives that use `React.forwardRef`. This inconsistency may confuse future contributors scanning for exported components.

#### useMemo dependency on pipelineMetaQueries creates potential re-render churn
**Step:** 5
**Details:** In `prompts.tsx` line 83, `promptKeyToPipelines` useMemo depends on `pipelineMetaQueries` (the array returned by `useQueries`). TanStack Query v5's `useQueries` returns a new array reference on every render, which means the useMemo dependency check will always detect a change and re-run the memo. The memo body has an early-return guard (`if (!q.data) return`) and the downstream `filteredPrompts` memo depends on the Map reference, so the practical impact is a Map rebuild each render cycle when any query state changes. For 1-5 pipelines this is negligible, but the dependency should ideally be stabilized (e.g., depend on `pipelineMetaQueries.map(q => q.data)` or use a `combine` option in `useQueries`).

### Low
#### Variable highlighting hardcoded color classes assume dark theme
**Step:** 4
**Details:** The highlight spans use `bg-blue-900/30 text-blue-400` (line 19 of PromptViewer.tsx). These are raw Tailwind colors rather than semantic design tokens (e.g., `bg-primary/20 text-primary`). In the current dark-only or dark-default theme this works fine, but if a light theme is added these colors will appear washed out or low contrast. Low priority since the codebase currently does not have a light theme actively in use for this section.

#### No accessibility labels on PromptFilterBar Select dropdowns
**Step:** 2
**Details:** The existing FilterBar.tsx uses `htmlFor`/`id` on its select trigger (`id="status-filter"`) plus a visible `<label>`. PromptFilterBar omits labels entirely -- the Select components have no `aria-label` or associated `<label>` element. The `placeholder` text on `SelectValue` provides some context but is not a proper accessible name. The search Input also lacks an `aria-label` (though the placeholder partially compensates).

## Review Checklist
[x] Architecture patterns followed -- split-pane layout matches RunDetailPage, data fetching at page level with presentational children, query key factory pattern, zod-validated search params
[x] Code quality and maintainability -- clean separation of concerns, well-structured components, clear naming
[x] Error handling present -- all three states (loading, error, empty) handled in PromptList and PromptViewer, guard on `!data` in PromptViewer
[x] No hardcoded values -- limit=200 matches backend max, ALL_SENTINEL pattern reused, no magic strings
[x] Project conventions followed -- Prettier (no semi, single quotes, trailing commas), named functions, path aliases, comment separators
[x] Security considerations -- React element highlighting avoids dangerouslySetInnerHTML (XSS safe), regex matches backend pattern
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- minimal new code, no unnecessary abstractions, reuses existing hooks and patterns

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `llm_pipeline/ui/frontend/src/api/query-keys.ts` | pass | `detail` factory follows exact pattern of `runs.detail` |
| `llm_pipeline/ui/frontend/src/api/prompts.ts` | pass | `usePromptDetail` mirrors `usePipeline` pattern with `enabled: Boolean(promptKey)` |
| `llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.tsx` | pass | Matches FilterBar.tsx ALL_SENTINEL pattern exactly; minor a11y gap |
| `llm_pipeline/ui/frontend/src/components/prompts/PromptList.tsx` | pass | Clean skeleton/error/empty states, proper button semantics with `type="button"` |
| `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.tsx` | pass | Variable highlighting regex matches backend, Tabs for multi-variant is appropriate; export style inconsistency |
| `llm_pipeline/ui/frontend/src/routes/prompts.tsx` | pass | Correct use of useQueries, zodValidator, useMemo filtering, URL param selection |

## New Issues Introduced
- None detected -- no regressions to existing functionality, all new files are additive

## Recommendation
**Decision:** APPROVE
All implementation steps are architecturally sound and follow codebase conventions. The two medium issues (export style, useMemo dependency stability) are minor consistency/optimization concerns that do not affect correctness or user experience. The low issues (hardcoded theme colors, missing a11y labels) are pre-existing patterns in the codebase. No blocking changes required.

---

# Re-Review (Post-Fix)

## Overall Assessment
**Status:** complete
All 4 issues from initial review resolved correctly. No new issues introduced by the fixes.

## Issue Resolution Verification

### MEDIUM - Step 4: PromptViewer export style -- RESOLVED
Line 69 now reads `export function PromptViewer(...)` at the declaration site. Matches project convention exactly. The trailing `export { }` block is removed. File ends cleanly at line 138 (blank line after closing brace).

### MEDIUM - Step 5: useMemo dependency re-render churn -- RESOLVED
`useQueries` now uses `combine` option (line 85) with a `useCallback`-wrapped `combinePipelineMeta` function (lines 52-77). The `combine` callback receives query results and returns a structurally-shared `Map<string, string[]>` directly. `promptKeyToPipelines` is now the Map itself (not an array of query results), so the downstream `filteredPrompts` useMemo (line 127) depends on a stable reference that only changes when actual pipeline data changes. The `useCallback` dependency on `pipelineNames` is correct since pipeline names determine the index-to-name mapping.

### LOW - Step 4: Variable highlighting hardcoded theme colors -- RESOLVED
Line 19 now uses `bg-primary/20 text-primary` (semantic design tokens) instead of `bg-blue-900/30 text-blue-400`. These tokens adapt to both light and dark themes automatically via CSS custom properties.

### LOW - Step 2: Missing a11y labels on PromptFilterBar -- RESOLVED
- Input (line 48): `aria-label="Search prompts"`
- Type Select trigger (line 55): `aria-label="Filter by prompt type"`
- Pipeline Select trigger (line 68): `aria-label="Filter by pipeline"`
All three interactive elements now have proper accessible names for screen readers.

## Files Re-Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.tsx` | pass | 3 aria-label attributes added correctly |
| `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.tsx` | pass | Export style fixed, semantic color tokens applied |
| `llm_pipeline/ui/frontend/src/routes/prompts.tsx` | pass | combine option stabilizes Map reference; useCallback deps correct |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE
All 4 issues fully resolved. Implementation is clean and consistent with codebase conventions. No further changes needed.
