# Task Summary

## Work Completed

Implemented the Prompt Browser view for the LLM pipeline dashboard. Added a split-pane page at `/prompts` with a scrollable, filterable prompt list on the left and a prompt detail viewer on the right. Filtering supports text search, prompt type, and pipeline name (via client-side cross-reference with pipeline metadata). Selected prompt persists in URL search params (`?key=<prompt_key>`). Variable placeholders in prompt content are highlighted using React elements (not `dangerouslySetInnerHTML`). All 4 issues found during review (export style, `useMemo` stability, hardcoded theme colors, missing a11y labels) were fixed and re-verified.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.tsx` | Filter bar with text search Input and two Select dropdowns (prompt type, pipeline) |
| `llm_pipeline/ui/frontend/src/components/prompts/PromptList.tsx` | Scrollable list of prompts (deduped by `prompt_key`) with loading skeleton, error, and empty states |
| `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.tsx` | Prompt detail panel showing all variants per key, monospace content with variable highlighting, Tabs for multi-variant |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/ui/frontend/src/api/query-keys.ts` | Added `detail: (key: string) => ['prompts', key] as const` factory to `prompts` object |
| `llm_pipeline/ui/frontend/src/api/prompts.ts` | Added `usePromptDetail(promptKey: string)` hook calling `GET /prompts/:key`, enabled only when key is truthy |
| `llm_pipeline/ui/frontend/src/routes/prompts.tsx` | Replaced stub with full `PromptsPage`: zod-validated search params, `usePrompts`/`usePipelines`/`useQueries` data fetching, client-side filtering via `useMemo`, split-pane layout |

## Commits Made

| Hash | Message |
| --- | --- |
| `97f650a` | `docs(implementation-A): master-39-prompt-browser-view` |
| `255c42a` | `docs(implementation-B): master-39-prompt-browser-view` |
| `4321db3` | `docs(implementation-B): master-39-prompt-browser-view` |
| `565cf89` | `docs(implementation-C): master-39-prompt-browser-view` |
| `1c603ac` | `docs(fixing-review-B): master-39-prompt-browser-view` |
| `1c693d0` | `docs(fixing-review-C): master-39-prompt-browser-view` |

Note: `PromptFilterBar.tsx` was created during the fixing-review phase (when a11y labels and review fixes were applied); its implementation commit is `1c603ac`.

## Deviations from Plan

- `PromptFilterBar.tsx` was not committed in its own implementation step -- it was created and committed during the fixing-review phase alongside the a11y label fixes. This was a sequencing deviation with no functional impact.
- `useQueries` `combine` option was added during fixing-review (not part of original plan) to stabilize the `promptKeyToPipelines` `useMemo` dependency. This improves render efficiency and aligns with TanStack Query v5 best practices.
- Variable highlight color changed from hardcoded `bg-blue-900/30 text-blue-400` (as specified in PLAN.md step 4) to semantic tokens `bg-primary/20 text-primary` to support light/dark theme compatibility.

## Issues Encountered

### MEDIUM: PromptViewer used `export { PromptViewer }` instead of `export function`
**Resolution:** Changed declaration to `export function PromptViewer(...)` at the definition site, removing the trailing export block. Matches project convention used by all other non-UI custom components.

### MEDIUM: `pipelineMetaQueries` array in `useMemo` deps caused re-render churn
**Resolution:** Added `combine` option to `useQueries` call with a `useCallback`-wrapped `combinePipelineMeta` function. The combine callback returns a structurally-shared `Map<string, string[]>` directly, so `promptKeyToPipelines` is a stable Map reference rather than a new array on every render.

### LOW: Variable highlight classes hardcoded to dark theme colors
**Resolution:** Replaced `bg-blue-900/30 text-blue-400` with `bg-primary/20 text-primary` semantic design tokens that adapt automatically to both light and dark themes via CSS custom properties.

### LOW: Missing accessibility labels on PromptFilterBar interactive elements
**Resolution:** Added `aria-label="Search prompts"` to the Input, `aria-label="Filter by prompt type"` to the type Select trigger, and `aria-label="Filter by pipeline"` to the pipeline Select trigger.

## Success Criteria

- [ ] `/prompts` route renders split-pane layout with left sidebar (prompt list) and right panel (prompt detail) -- requires runtime verification with live backend
- [ ] Prompt list shows all prompts loaded from `GET /api/prompts?limit=200` (deduped by `prompt_key`) -- requires runtime verification
- [ ] Text search filters list by `prompt_name` and `prompt_key` (case-insensitive, client-side) -- requires runtime verification
- [ ] Prompt type filter (Select) filters list by `prompt.prompt_type` -- requires runtime verification
- [ ] Pipeline filter (Select) filters list to prompts whose `prompt_key` belongs to selected pipeline's steps -- requires runtime verification
- [ ] Selecting a prompt navigates to `?key=<prompt_key>` and highlights the item in the list -- requires runtime verification
- [ ] Reloading page at `?key=<prompt_key>` restores selected prompt in detail viewer -- requires runtime verification
- [ ] Detail viewer shows all variants (system/user) for selected `prompt_key` -- requires runtime verification
- [x] Variable placeholders `{var_name}` highlighted with distinct color in monospace content -- confirmed via code review: `highlightVariables()` splits on `/(\{[a-zA-Z_][a-zA-Z0-9_]*\})/g` and wraps matches in `<span className="rounded bg-primary/20 px-0.5 text-primary">`
- [x] Variable highlighting uses React elements (not `dangerouslySetInnerHTML`) -- confirmed: returns `React.ReactNode[]`, no `dangerouslySetInnerHTML`
- [x] Monospace font applied to prompt template content (`font-mono`) -- confirmed: `<pre className="whitespace-pre-wrap break-all rounded-md bg-muted p-3 font-mono text-xs">`
- [x] Loading skeletons shown while data fetches -- confirmed: `SkeletonRows` in `PromptList`, skeleton divs in `PromptViewer`
- [x] Error states shown on fetch failure (`text-destructive`) -- confirmed in `PromptList` and `PromptViewer`
- [x] Empty states shown when no prompts match filters -- confirmed: `'No prompts match filters'` in `PromptList`
- [x] No semicolons, single quotes, named function components (ESLint compliance) -- confirmed: `npx eslint` passes with zero issues on all 6 new/modified files
- [x] TypeScript type-check clean -- confirmed: `npm run type-check` exits zero errors
- [x] Vite production build succeeds -- confirmed: 2105 modules transformed successfully
- [x] All 91 existing vitest tests pass -- confirmed: 9 test files, 91 tests, zero failures

## Recommendations for Follow-up

1. Add vitest unit tests for `highlightVariables()` (pure function, easy to test with various variable patterns and edge cases) following the `FilterBar.test.tsx` pattern, once backend task 22 is merged and `/api/prompts` endpoint is live.
2. Add vitest component tests for `PromptList` and `PromptFilterBar` covering loading/error/empty states and filter interactions.
3. Address pre-existing `react-hooks/set-state-in-effect` error in `src/routes/live.tsx` (line 198) in a separate task -- this blocks `npm run lint` from passing with `--max-warnings=0`.
4. Run full manual validation checklist (route render, prompt selection/URL persistence, variable highlighting, pipeline filter cross-reference) once backend endpoints `/api/prompts` and `/api/pipelines/{name}` are available.
5. If the prompt dataset grows beyond 200 items in future, add server-side filtering or pagination -- a `TODO` comment exists in `prompts.tsx` at the `limit: 200` call site.
