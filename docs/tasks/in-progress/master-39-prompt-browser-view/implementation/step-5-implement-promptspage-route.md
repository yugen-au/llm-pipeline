# IMPLEMENTATION - STEP 5: IMPLEMENT PROMPTSPAGE ROUTE
**Status:** completed

## Summary
Replaced the `prompts.tsx` stub with full PromptsPage implementation wiring PromptFilterBar, PromptList, and PromptViewer into a split-pane layout with Zod-validated URL search params, client-side filtering, pipeline cross-reference via useQueries, and prompt_key deduplication.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/prompts.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/prompts.tsx`
Full replacement of stub with PromptsPage implementation.

```
# Before
import { createFileRoute } from '@tanstack/react-router'

export const Route = createFileRoute('/prompts')({
  component: PromptsPage,
})

function PromptsPage() {
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-card-foreground">Prompts</h1>
      <p className="mt-2 text-muted-foreground">Prompt management</p>
    </div>
  )
}

# After
- Zod search schema with `fallback(z.string(), '').default('')` + `zodValidator` (matches $runId.tsx pattern)
- `Route.useSearch()` for `key` param, `useNavigate({ from: '/prompts' })` for selection
- `usePrompts({ limit: 200 })` fetches all prompts
- `usePipelines()` fetches pipeline list
- `useQueries` with `queryKeys.pipelines.detail(name)` per pipeline, `staleTime: Infinity`, builds `Map<prompt_key, string[]>`
- Local `useState` for selectedType, selectedPipeline, searchText
- `useMemo` for filteredPrompts: filters by type, pipeline (via map lookup), searchText (case-insensitive on prompt_name + prompt_key), deduplicates by prompt_key
- Split-pane layout: left panel (w-80, border, overflow-hidden) with PromptFilterBar + PromptList; right panel (flex-1, border, overflow-auto) with PromptViewer
- `promptTypes` derived from `[...new Set(prompts.data?.items.map(p => p.prompt_type))]`
- `pipelineNames` derived from `pipelines.data?.pipelines.map(p => p.name)`
```

## Decisions
### ALL_SENTINEL not needed in route file
**Choice:** Removed `ALL_SENTINEL` constant from prompts.tsx -- sentinel logic lives in PromptFilterBar which converts sentinel to empty string via callbacks
**Rationale:** ESLint flagged unused variable. The page uses empty string `''` for "all" filter state; PromptFilterBar handles sentinel <-> empty string conversion internally.

### useQueries over individual usePipeline calls
**Choice:** Used `useQueries` from `@tanstack/react-query` with mapped pipeline names instead of calling `usePipeline(name)` per pipeline
**Rationale:** `useQueries` dispatches all pipeline detail requests in parallel (no waterfall). Reuses same query keys as `usePipeline` hook so cache is shared. Direct `apiClient` call avoids needing to restructure the existing `usePipeline` hook.

## Verification
[x] TypeScript `tsc --noEmit` passes with zero errors
[x] ESLint passes with zero errors
[x] No semicolons, single quotes, named function components (ESLint compliance)
[x] Route tree generation unchanged (prompts route still present in routeTree.gen.ts)
[x] Zod search schema follows $runId.tsx pattern exactly
[x] useQueries with staleTime: Infinity follows useStepInstructions precedent
[x] Layout matches RunDetailPage split-pane pattern (flex min-h-0 flex-1 gap-4, w-80 shrink-0)
[x] Filter state uses empty string for "all" (PromptFilterBar converts sentinel internally)
[x] Deduplication by prompt_key in useMemo before passing to PromptList
[x] URL param `?key=` drives selection and is bookmarkable

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] (MEDIUM) useMemo dependency on pipelineMetaQueries creates re-render churn -- useQueries returns new array ref every render, causing promptKeyToPipelines useMemo to re-run needlessly

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/routes/prompts.tsx`
Replaced separate `useQueries` + `useMemo` with `useQueries({ combine })` pattern. The `combine` callback is wrapped in `useCallback` (stable ref keyed on `pipelineNames`) so it only re-runs when pipeline data actually changes. TanStack Query v5 structurally shares the `combine` return value, eliminating the unstable array reference problem.

```
# Before
const pipelineMetaQueries = useQueries({
  queries: pipelineNames.map((name) => ({ ... })),
})

const promptKeyToPipelines = useMemo(() => {
  const map = new Map<string, string[]>()
  pipelineMetaQueries.forEach((q, idx) => { ... })
  return map
}, [pipelineMetaQueries, pipelineNames])   // <-- unstable dep

# After
const combinePipelineMeta = useCallback(
  (results: { data: PipelineMetadata | undefined }[]) => {
    const map = new Map<string, string[]>()
    results.forEach((q, idx) => { ... })
    return map
  },
  [pipelineNames],
)

const promptKeyToPipelines = useQueries({
  queries: pipelineNames.map((name) => ({ ... })),
  combine: combinePipelineMeta,             // <-- structurally shared
})
```

### Verification
[x] TypeScript `tsc --noEmit` passes with zero errors
[x] ESLint passes with zero errors
[x] combine callback uses useCallback with [pipelineNames] dep for stable ref
[x] Map building logic unchanged -- only the memoization strategy changed
