# PLANNING

## Summary

Implement the Prompt Browser view: a split-pane page at `/prompts` showing a scrollable, filterable prompt list on the left and a prompt detail viewer on the right. Filtering supports prompt type and pipeline name (via client-side cross-reference with pipeline introspection data). Selected prompt persists in URL search params. Variable placeholders highlighted via React elements. No backend changes required.

## Plugin & Agents

**Plugin:** frontend-mobile-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **API Layer**: Add `queryKeys.prompts.detail` factory and `usePromptDetail` hook to existing API files
2. **Components**: Build `PromptFilterBar`, `PromptList`, `PromptViewer` components
3. **Route**: Replace `prompts.tsx` stub with full split-pane `PromptsPage` wiring all components

## Architecture Decisions

### Client-Side Pipeline Filter via Cross-Reference

**Choice:** Fetch all pipeline metadata in parallel with prompts. Build a `Map<prompt_key, string[]>` (prompt_key to pipeline names). Filter prompts client-side by checking if `prompt.prompt_key` is in the selected pipeline's key set.

**Rationale:** The `Prompt` DB model has no `pipeline_name` field. CEO confirmed pipeline filter = actual pipeline names (e.g. `RateCardExtractionPipeline`). `PipelineMetadata.strategies[].steps[].system_key` and `user_key` expose prompt keys per pipeline -- confirmed in `src/api/types.ts` (`PipelineStepMetadata`). `usePipelines()` and `usePipeline(name)` exist in `src/api/pipelines.ts`. Dataset is small (20-200 prompts, 1-5 pipelines), so parallel fetching + client join is acceptable. `staleTime: Infinity` on pipeline metadata follows `useStepInstructions` precedent.

**Alternatives:** Use `category` or `step_name` as pipeline proxy (rejected -- CEO explicitly wants pipeline name), server-side join (rejected -- no backend endpoint, no backend changes desired).

### URL Search Params for Selected Prompt

**Choice:** Zod-validated search params `?key=<prompt_key>` (bookmarkable). Follow `$runId.tsx` pattern using `zodValidator` from `@tanstack/zod-adapter` and `fallback()`.

**Rationale:** CEO confirmed URL-param-based selection. Existing `$runId.tsx` demonstrates exact pattern: `z.object({ key: fallback(z.string(), '').default('') })` with `validateSearch: zodValidator(schema)`. `useNavigate` + `navigate({ search: { key } })` for selection.

**Alternatives:** Zustand ephemeral state (rejected -- not bookmarkable per CEO requirement).

### Full-Scroll with Client-Side Filtering

**Choice:** Single `GET /api/prompts?limit=200` fetch. All filter logic (prompt_type, pipeline) applied client-side in `useMemo`. Native scroll via CSS `overflow-y-auto`.

**Rationale:** CEO confirmed full scroll, no pagination. Backend max is 200 (verified in `PromptListParams`). Client-side `useMemo` filtering eliminates server round-trips on filter change, matches file-browser UX goal. `ScrollArea` from shadcn/ui provides consistent scroll styling.

**Alternatives:** Server-side filtering per change (rejected -- adds latency, contradicts CEO's preference), infinite scroll (rejected explicitly by CEO).

### Variable Highlighting via React Elements

**Choice:** Split content string on regex `\{([a-zA-Z_][a-zA-Z0-9_]*)\}` (backend-compatible), render matches as `<span>` with highlight classes, wrap in `<pre className="whitespace-pre-wrap font-mono text-xs">`.

**Rationale:** Task description specifies React elements, not `dangerouslySetInnerHTML`. Backend `extract_variables_from_content` uses `\{([a-zA-Z_][a-zA-Z0-9_]*)\}` (no dots) per `llm_pipeline/prompts/loader.py`. Using the same regex avoids highlighting non-variable dot-notation patterns. Monospace `<pre>` follows existing pattern in `StepDetailPanel`.

**Alternatives:** `dangerouslySetInnerHTML` with HTML injection (rejected -- XSS risk, task explicitly forbids it), dot-inclusive regex `\{[\w.]+\}` (rejected -- inconsistent with backend).

### Component Structure

**Choice:** Three new component files: `src/components/prompts/PromptFilterBar.tsx`, `src/components/prompts/PromptList.tsx`, `src/components/prompts/PromptViewer.tsx`. Route page `src/routes/prompts.tsx` owns data fetching and passes props down.

**Rationale:** Follows RunDetailPage composition pattern (page owns queries, passes data to presentational components). Collocating under `src/components/prompts/` mirrors `src/components/runs/` directory pattern (confirmed: `StepTimeline`, `ContextEvolution`, `StepDetailPanel` all live there).

**Alternatives:** Inline everything in `prompts.tsx` (rejected -- too large, untestable), context/store for selected key (rejected -- URL params handle this already).

## Implementation Steps

### Step 1: Extend API Layer

**Agent:** frontend-mobile-development:default
**Skills:** none
**Context7 Docs:** /tanstack/query
**Group:** A

1. In `llm_pipeline/ui/frontend/src/api/query-keys.ts`, add `detail: (key: string) => ['prompts', key] as const` to the `prompts` object (after the existing `list` factory). Import is already correct (`PromptListParams` used by `list`).
2. In `llm_pipeline/ui/frontend/src/api/prompts.ts`, add `import type { PromptDetail } from './types'` and add `usePromptDetail(promptKey: string)` hook: `useQuery({ queryKey: queryKeys.prompts.detail(promptKey), queryFn: () => apiClient<PromptDetail>('/prompts/' + promptKey), enabled: Boolean(promptKey) })`. Use default staleTime (30s) -- prompt content is static reference data.

### Step 2: Build PromptFilterBar Component

**Agent:** frontend-mobile-development:default
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/prompts/PromptFilterBar.tsx`.
2. Props: `promptTypes: string[]`, `pipelineNames: string[]`, `selectedType: string`, `selectedPipeline: string`, `onTypeChange: (v: string) => void`, `onPipelineChange: (v: string) => void`, `searchText: string`, `onSearchChange: (v: string) => void`.
3. Render: `Input` for text search (shadcn Input, placeholder "Search prompts..."), two shadcn `Select` dropdowns (prompt type, pipeline name) using `ALL_SENTINEL = '__all'` pattern from `FilterBar.tsx`. Pipeline select options derived from `pipelineNames` prop.
4. Use `cn()` from `@/lib/utils`, import shadcn `Select`, `SelectTrigger`, `SelectContent`, `SelectItem`, `SelectValue`, `Input` from `@/components/ui/`. No semicolons, single quotes, named function component (ESLint rules).

### Step 3: Build PromptList Component

**Agent:** frontend-mobile-development:default
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/prompts/PromptList.tsx`.
2. Props: `prompts: Prompt[]`, `selectedKey: string`, `onSelect: (key: string) => void`, `isLoading: boolean`, `error: Error | null`.
3. Loading state: render 6x skeleton rows `<div className="h-12 animate-pulse rounded bg-muted" />` inside `ScrollArea`.
4. Error state: `<p className="text-sm text-destructive">Failed to load prompts</p>`.
5. Empty state: `<p className="text-sm text-muted-foreground">No prompts match filters</p>`.
6. List: shadcn `ScrollArea` wrapping a list of items. Each item is a `<button>` (or div with role="button") showing `prompt.prompt_name` and `prompt.prompt_type` badge. Selected item highlighted with `bg-accent` or `bg-muted`. Clicking calls `onSelect(prompt.prompt_key)`. Group by `prompt_key` (show unique keys; since system/user variants are fetched in detail view, list shows one row per unique `prompt_key`).
7. Import `Prompt` type from `@/api/types`, `Badge` from `@/components/ui/badge`, `ScrollArea` from `@/components/ui/scroll-area`.

### Step 4: Build PromptViewer Component

**Agent:** frontend-mobile-development:default
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.tsx`.
2. Props: `promptKey: string | null` (null = nothing selected).
3. Internally calls `usePromptDetail(promptKey ?? '')` (enabled only when key truthy).
4. Empty state (no key): centered `<p className="text-muted-foreground">Select a prompt to view details</p>`.
5. Loading state: skeleton placeholder matching header + content areas.
6. Error state: `<p className="text-sm text-destructive">Failed to load prompt</p>`.
7. Loaded: show `PromptDetail.prompt_key` as heading, then for each variant in `PromptDetail.variants`:
   - Section header with `prompt.prompt_type` label (Badge) and `prompt.version`.
   - Optional `prompt.description` as `<p className="text-sm text-muted-foreground">`.
   - If `prompt.required_variables` non-empty, render a list of variable badges.
   - Content rendered in `<pre className="whitespace-pre-wrap font-mono text-xs rounded-md bg-muted p-3">` with inline variable highlighting via `highlightVariables(content)` helper.
8. `highlightVariables(content: string): React.ReactNode[]`: split on regex `/(\{[a-zA-Z_][a-zA-Z0-9_]*\})/g`, return array where matches are `<span className="rounded bg-blue-900/30 px-0.5 text-blue-400">{part}</span>` and non-matches are plain strings. Use `key={i}` on each element.
9. Wrap in `Tabs` (shadcn) if variants > 1, else show single variant directly. Tab values = `prompt_type`.
10. Import `usePromptDetail` from `@/api/prompts`, types from `@/api/types`, shadcn components from `@/components/ui/`.

### Step 5: Implement PromptsPage Route

**Agent:** frontend-mobile-development:default
**Skills:** none
**Context7 Docs:** /tanstack/router, /tanstack/query
**Group:** C

1. Replace `llm_pipeline/ui/frontend/src/routes/prompts.tsx` with full implementation.
2. Add zod search schema: `z.object({ key: fallback(z.string(), '').default('') })`. Export `Route = createFileRoute('/prompts')({ validateSearch: zodValidator(schema), component: PromptsPage })`.
3. Data fetching inside `PromptsPage`:
   - `usePrompts({ limit: 200 })` -- fetch all prompts (no server-side filters; apply filters client-side).
   - `usePipelines()` -- fetch pipeline list.
   - For each pipeline name from pipelines data, call `usePipeline(name)` to get metadata. Use `useQueries` pattern or sequential `usePipeline` calls. Since pipeline count is small (1-5), call `usePipeline` per name conditionally. Build `Map<prompt_key, string[]>` once all pipeline metadata is loaded.
4. Filter state: local `useState` for `selectedType`, `selectedPipeline`, `searchText`. All start at `ALL_SENTINEL` or `''`.
5. `useMemo` for filtered prompts list: filter `prompts.data?.items` by `selectedType`, `selectedPipeline` (lookup in pipeline->prompt_key map), `searchText` (match against `prompt_name` and `prompt_key`, case-insensitive). Deduplicate by `prompt_key` for list display (one row per unique key, since variants are shown in detail viewer).
6. URL param for selected key: `const { key } = Route.useSearch()`, `const navigate = useNavigate({ from: '/prompts' })`. Call `navigate({ search: { key: promptKey } })` on list item click.
7. Layout: `<div className="flex h-full flex-col gap-4 p-6">` with `<h1>Prompts</h1>` heading and `<div className="flex min-h-0 flex-1 gap-4">`. Left panel `<div className="flex w-80 shrink-0 flex-col overflow-hidden rounded-xl border">` containing `PromptFilterBar` + `PromptList`. Right panel `<div className="flex-1 overflow-auto rounded-xl border">` containing `PromptViewer`.
8. Pass all necessary props to child components. Pass `selectedKey={key}` and `onSelect` callback to `PromptList`. Pass `promptKey={key || null}` to `PromptViewer`.
9. Derive `promptTypes` for filter from `[...new Set(prompts.data?.items.map(p => p.prompt_type) ?? [])]`. Derive `pipelineNames` from `pipelines.data?.pipelines.map(p => p.name) ?? []`.
10. Handle `useQueries` for pipeline metadata: import `useQueries` from `@tanstack/react-query`, use `queryKeys.pipelines.detail(name)` per pipeline, `apiClient<PipelineMetadata>('/pipelines/' + name)`, `staleTime: Infinity`. Build the prompt_key map in `useMemo` from results.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `usePipeline` called per pipeline name causes waterfall | Low | Parallel fetch via `useQueries` (all pipeline detail queries dispatched simultaneously, not sequential). staleTime: Infinity prevents re-fetching. |
| `GET /api/pipelines` or `/api/pipelines/{name}` not yet implemented (task 24 note) | Medium | Check if pipelines endpoints are live. Pipeline filter degrades gracefully: if `usePipelines()` returns error/empty, pipeline filter dropdown shows empty and all prompts are displayed (no crash). |
| `GET /api/prompts?limit=200` returns more than 200 items as dataset grows | Low | 200 is backend max per `PromptListParams`. If dataset exceeds 200, note in code and set limit=200 for now. Add TODO comment for pagination if ever needed. |
| `prompt_key` uniqueness in list: system+user variants share same key | Low | Deduplicate list by `prompt_key` using `Map` in `useMemo` before rendering PromptList. Detail viewer shows all variants grouped by type. |
| Variable regex mismatch with future dot-notation variables | Low | Use backend-compatible regex `\{([a-zA-Z_][a-zA-Z0-9_]*)\}`. Document this choice with a comment referencing `prompts/loader.py`. |
| `useQueries` import: may not be in existing imports | Low | `useQueries` is part of `@tanstack/react-query` v5, already installed. |

## Success Criteria

- [ ] `/prompts` route renders split-pane layout with left sidebar (prompt list) and right panel (prompt detail)
- [ ] Prompt list shows all prompts loaded from `GET /api/prompts?limit=200` (deduped by prompt_key)
- [ ] Text search filters list by prompt_name and prompt_key (case-insensitive, client-side)
- [ ] Prompt type filter (Select) filters list by `prompt.prompt_type`
- [ ] Pipeline filter (Select) filters list to prompts whose `prompt_key` belongs to selected pipeline's steps
- [ ] Selecting a prompt navigates to `?key=<prompt_key>` and highlights the item in the list
- [ ] Reloading page at `?key=<prompt_key>` restores selected prompt in detail viewer
- [ ] Detail viewer shows all variants (system/user) for selected `prompt_key`
- [ ] Variable placeholders `{var_name}` highlighted with distinct color in monospace content
- [ ] Variable highlighting uses React elements (not dangerouslySetInnerHTML)
- [ ] Monospace font applied to prompt template content (`font-mono`)
- [ ] Loading skeletons shown while data fetches
- [ ] Error states shown on fetch failure (text-destructive)
- [ ] Empty states shown when no prompts match filters
- [ ] No semicolons, single quotes, named function components (ESLint compliance)

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Pure frontend feature. No backend changes. All API endpoints exist and are verified. All shadcn/ui components are installed. All TypeScript types are defined. The only new artifacts are ~20 lines in existing API files plus 3 new component files and 1 route replacement. Pipeline filter has graceful degradation if pipelines endpoint is unavailable.
**Suggested Exclusions:** testing, review
