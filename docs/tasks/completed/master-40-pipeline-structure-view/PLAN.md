# PLANNING

## Summary

Replace the stub `src/routes/pipelines.tsx` with a full Pipeline Structure View using the left-right panel layout pattern from prompts.tsx. Left panel lists pipelines; right panel shows strategies, steps, schemas, and prompt keys. Requires fixing 2 TS interfaces (PipelineListItem and PipelineStepMetadata) and removing @provisional tags from modified types before building the UI.

## Plugin & Agents

**Plugin:** frontend-mobile-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Type Fixes**: Fix TS interface mismatches in `src/api/types.ts` (PipelineListItem nullability + missing fields, PipelineStepMetadata nullability) and remove @provisional tags from modified types
2. **Sub-components**: Create `src/components/pipelines/` directory with PipelineList, PipelineDetail, StrategySection, StepRow, JsonTree sub-components
3. **Route**: Replace stub `src/routes/pipelines.tsx` with full implementation wiring hooks, URL search params (?pipeline=name), and sub-components together

## Architecture Decisions

### Left-Right Panel Layout
**Choice:** Follow prompts.tsx pattern exactly -- flex h-full, left panel w-80 shrink-0 with ScrollArea, right panel flex-1 overflow-auto, both rounded-xl border
**Rationale:** Prompts page already implements this pattern with URL search params and TanStack Router zodValidator. Consistency reduces cognitive overhead and reuses tested patterns.
**Alternatives:** Full-page table with expandable rows (rejected: doesn't match existing UI conventions)

### URL State via Search Params
**Choice:** `?pipeline=name` search param via TanStack Router zodValidator (same as prompts.tsx `?key=`)
**Rationale:** Shareable links, browser back/forward, matches existing prompts page pattern. No Zustand store needed (ephemeral selection state).
**Alternatives:** Zustand store for selected pipeline (rejected: overkill for simple selection, contradicts "no new stores" constraint)

### Collapsible JSON Tree Component
**Choice:** Recursive `JsonTree` component in `src/components/pipelines/JsonTree.tsx` using useState for collapsed nodes, rendering object/array/primitive branches. No new dependency.
**Rationale:** CEO confirmed collapsible JSON tree. Available shadcn/ui components do not include a tree/collapsible but the button component can render chevron toggles. Pure React state, no library needed.
**Alternatives:** Pre-formatted `<pre>` block (rejected: not collapsible), react-json-tree library (rejected: no new dependencies constraint)

### Prompt Key Click-Through
**Choice:** Render system_key/user_key as `<Link to='/prompts' search={{ key: promptKey }}>` using TanStack Router Link component
**Rationale:** CEO confirmed click-through. Reuses existing /prompts route URL param pattern (?key=). No new navigation logic needed.
**Alternatives:** Copy-to-clipboard only (rejected: CEO explicitly approved navigation)

### Step Detail Expansion
**Choice:** Clicking a step row in the right panel expands inline (accordion pattern using local state) to show step details: class_name, system_key, user_key, instructions_schema, context_schema, extractions, transformation. No Sheet/modal.
**Rationale:** Inline expansion avoids overlapping panels. Schemas are shown via JsonTree. Simpler than a secondary right panel or Sheet drawer.
**Alternatives:** Sheet drawer (rejected: already used by StepDetailPanel in runs, would be visually jarring), nested right panel (rejected: adds layout complexity)

### @provisional Tag Removal
**Choice:** Remove @provisional JSDoc tags from PipelineListItem and PipelineStepMetadata only (the 2 types being modified). Leave ExtractionMetadata, TransformationMetadata, PipelineStrategyMetadata, PipelineMetadata untouched.
**Rationale:** Research confirmed PipelineStrategyMetadata already has error field and doesn't need changes. @provisional tags on modified types become stale after fixes are applied.
**Alternatives:** Remove all @provisional pipeline tags at once (rejected: out of scope for task 40; other types not validated against live backend in this task)

## Implementation Steps

### Step 1: Fix TypeScript Interface Mismatches
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /tanstack/router
**Group:** A

1. In `llm_pipeline/ui/frontend/src/api/types.ts` lines 320-332, change `system_key: string` to `system_key: string | null` and `user_key: string` to `user_key: string | null` in `PipelineStepMetadata`
2. In `llm_pipeline/ui/frontend/src/api/types.ts` lines 366-371, update `PipelineListItem`: change `strategy_count: number` to `strategy_count: number | null`, change `step_count: number` to `step_count: number | null`, add `registry_model_count: number | null`, add `error: string | null`
3. Remove `@provisional` JSDoc tag lines from `PipelineStepMetadata` (line ~317-319) and `PipelineListItem` (line ~362-365) only -- leave other pipeline type JSDoc blocks untouched
4. Verify `prompts.tsx` line 60 `[step.system_key, step.user_key]` compiles with nullability (already handles `if (!promptKey) continue` on line 61 -- no change needed there)

### Step 2: Create PipelineList Sub-component
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/pipelines/PipelineList.tsx`
2. Props: `{ pipelines: PipelineListItem[], selectedName: string, onSelect: (name: string) => void, isLoading: boolean, error: Error | null }`
3. Render skeleton rows (6x animate-pulse h-12) when isLoading
4. Render error message `text-destructive` when error
5. Render empty state `text-muted-foreground` when pipelines.length === 0
6. Wrap list in `<ScrollArea className="flex-1">` from `@/components/ui/scroll-area`
7. Each pipeline row: button with `cn('flex w-full items-center gap-3 rounded-md px-3 py-2 text-left transition-colors cursor-pointer hover:bg-muted/30', isSelected && 'bg-accent')`
8. Row content: pipeline name (flex-1 truncate text-sm font-medium), badge showing step count or error badge (variant="destructive" if error field present), badge showing strategy count (variant="secondary") -- hide counts if null

### Step 3: Create JsonTree Sub-component
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/pipelines/JsonTree.tsx`
2. Props: `{ data: Record<string, unknown> | unknown[] | null, depth?: number }`
3. Implement recursive `JsonTreeNode` (private) that renders: object keys as collapsible rows with chevron toggle (useState per node), arrays as indexed collapsible rows, primitives as inline value spans
4. Use `ChevronRight`/`ChevronDown` from `lucide-react` (already used in codebase -- verify import path) for collapse toggles
5. Default collapsed at depth >= 2, expanded at depth 0-1
6. Null/undefined: render `<span className="text-muted-foreground italic">null</span>`
7. String values: `text-green-600 dark:text-green-400`, numbers: `text-blue-600 dark:text-blue-400`, booleans: `text-orange-600`
8. Export `JsonTree` (public), keep `JsonTreeNode` private

### Step 4: Create StrategySection and StepRow Sub-components
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui, /tanstack/router
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/pipelines/StrategySection.tsx`
2. `StrategySection` props: `{ strategy: PipelineStrategyMetadata, pipelineName: string }`
3. Render strategy header: display_name (text-base font-semibold) + class_name (text-xs text-muted-foreground font-mono) + error badge if strategy.error
4. If strategy.error, show `<p className="text-sm text-destructive">{strategy.error}</p>` instead of steps
5. Render ordered list of `StepRow` for each step in strategy.steps

6. `StepRow` (same file or separate -- keep in StrategySection.tsx for locality): props `{ step: PipelineStepMetadata, pipelineName: string }`
7. StepRow has local `useState<boolean>(false)` for expanded/collapsed
8. Collapsed row: step_name (text-sm font-medium), class_name (text-xs text-muted-foreground), clickable chevron to expand
9. Expanded row shows step detail section below: system_key and user_key as clickable `<Link to='/prompts' search={{ key }}` links (only rendered if not null), instructions_schema and context_schema via `<JsonTree>`, extractions list (class_name + model_class per extraction), transformation summary if present
10. Prompt key links: `<a>` using TanStack Router `Link` component: `import { Link } from '@tanstack/react-router'` -- renders as `<Link to='/prompts' search={{ key: step.system_key }} className="font-mono text-xs text-primary underline">`

### Step 5: Create PipelineDetail Sub-component
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /shadcn-ui/ui
**Group:** B

1. Create `llm_pipeline/ui/frontend/src/components/pipelines/PipelineDetail.tsx`
2. Props: `{ pipelineName: string | null }`
3. Empty state (pipelineName null): centered `<p className="text-muted-foreground">Select a pipeline to view details</p>`
4. Uses `usePipeline(pipelineName ?? '')` hook from `@/api/pipelines`
5. Loading state: skeleton blocks (h-7 w-48, h-4 w-32, h-40)
6. Error state: centered `<p className="text-sm text-destructive">Failed to load pipeline</p>`
7. Loaded: render header section (pipeline_name h2, registry_models as badge list, execution_order as ordered badge list, pipeline_input_schema via JsonTree if not null)
8. Below header: render each strategy via `<StrategySection>` in a `<div className="space-y-6">`
9. Wrap entire content in `<ScrollArea className="h-full">` with inner `<div className="space-y-6 p-4">`

### Step 6: Replace Stub pipelines.tsx Route
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /tanstack/router, /shadcn-ui/ui
**Group:** C

1. Replace content of `llm_pipeline/ui/frontend/src/routes/pipelines.tsx` entirely
2. Add zodValidator search schema: `const pipelinesSearchSchema = z.object({ pipeline: fallback(z.string(), '').default('') })`
3. Update `Route = createFileRoute('/pipelines')({ validateSearch: zodValidator(pipelinesSearchSchema), component: PipelinesPage })`
4. `PipelinesPage` function: get `{ pipeline }` from `Route.useSearch()`, `useNavigate({ from: '/pipelines' })`
5. Call `usePipelines()` hook -- access `data?.pipelines ?? []`
6. `handleSelect(name: string)`: `navigate({ search: { pipeline: name } })`
7. Layout: `<div className="flex h-full flex-col gap-4 p-6">` with h1 "Pipelines" + `<div className="flex min-h-0 flex-1 gap-4">`
8. Left panel: `<div className="flex w-80 shrink-0 flex-col overflow-hidden rounded-xl border">` containing `<PipelineList pipelines={...} selectedName={pipeline} onSelect={handleSelect} isLoading={pipelines.isLoading} error={pipelines.error} />`
9. Right panel: `<div className="flex-1 overflow-auto rounded-xl border">` containing `<PipelineDetail pipelineName={pipeline || null} />`
10. Imports: `createFileRoute, useNavigate` from `@tanstack/react-router`, `fallback, zodValidator` from `@tanstack/zod-adapter`, `z` from `zod`, `usePipelines` from `@/api/pipelines`, `PipelineList` from `@/components/pipelines/PipelineList`, `PipelineDetail` from `@/components/pipelines/PipelineDetail`

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `lucide-react` ChevronRight/ChevronDown icons not available | Medium | Verify icon names in existing codebase usages before implementing JsonTree; fallback to inline SVG or text +/- toggle if missing |
| prompts.tsx type error after PipelineStepMetadata nullability fix | Medium | The `if (!promptKey) continue` guard on line 61 of prompts.tsx already handles null -- verify no TS error after fix before proceeding to Step 2 |
| `@tanstack/zod-adapter` not installed | Medium | Verify it is already used in prompts.tsx (confirmed) -- same import works in pipelines.tsx |
| PipelineDetail re-fetches on every render if pipelineName changes rapidly | Low | `enabled: Boolean(name)` guard in usePipeline prevents empty requests; React Query deduplicates in-flight requests |
| StepRow Link import path conflict | Low | Import `Link` from `@tanstack/react-router` directly; no alias needed since the router package is already a direct dep |

## Success Criteria

- [ ] `src/api/types.ts` PipelineListItem has `registry_model_count: number | null`, `error: string | null`, `strategy_count: number | null`, `step_count: number | null`
- [ ] `src/api/types.ts` PipelineStepMetadata has `system_key: string | null`, `user_key: string | null`
- [ ] @provisional JSDoc tags removed from PipelineListItem and PipelineStepMetadata
- [ ] `src/components/pipelines/PipelineList.tsx` renders list with loading/error/empty states
- [ ] `src/components/pipelines/JsonTree.tsx` renders collapsible tree for JSON objects/arrays with depth-based default collapse
- [ ] `src/components/pipelines/StrategySection.tsx` renders strategy header + StepRow list, handles strategy.error
- [ ] `src/components/pipelines/PipelineDetail.tsx` renders full pipeline detail with strategies, registry models, execution order, input schema
- [ ] `src/routes/pipelines.tsx` uses zodValidator search schema with `?pipeline=` param
- [ ] Selecting a pipeline in left panel updates URL and loads detail in right panel
- [ ] Prompt key links (system_key/user_key) navigate to `/prompts?key=<key>` when clicked
- [ ] TypeScript compilation passes with no new errors
- [ ] No new npm dependencies, Zustand stores, or backend endpoints added

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All backend endpoints exist and are verified. All frontend hooks exist and are verified. Type fixes are mechanical (nullability + field additions). UI pattern is direct copy of prompts.tsx. No new dependencies or architectural unknowns. The only non-trivial piece is the recursive JsonTree component, which is self-contained.
**Suggested Exclusions:** testing, review
