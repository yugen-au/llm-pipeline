# Task Summary

## Work Completed

Implemented the Pipeline Structure View frontend (task 40). Replaced the stub `pipelines.tsx` route with a full left-right panel layout following the prompts.tsx pattern. First fixed TypeScript interface mismatches in `types.ts` to match actual backend responses (nullability, missing fields, stale @provisional tags). Then built five new sub-components: PipelineList (left panel), JsonTree (recursive collapsible schema viewer), StrategySection + StepRow (strategy headers and expandable step rows with prompt click-through), and PipelineDetail (right panel). Wired them together in the route with URL state via `?pipeline=name`. No backend changes, no new dependencies.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/frontend/src/components/pipelines/PipelineList.tsx` | Left panel list with loading skeleton, error, empty, and populated states; badges for step count, strategy count, and pipeline errors |
| `llm_pipeline/ui/frontend/src/components/pipelines/JsonTree.tsx` | Recursive collapsible JSON tree for rendering pipeline schemas; depth-based default collapse; color-coded primitive values |
| `llm_pipeline/ui/frontend/src/components/pipelines/StrategySection.tsx` | Strategy header + StepRow accordion; StepRow expands to show prompt key links, schema trees, extractions, transformation; TransformationSummary helper |
| `llm_pipeline/ui/frontend/src/components/pipelines/PipelineDetail.tsx` | Right panel with empty/loading/error/loaded states; renders pipeline name, registry models, execution order, input schema, and strategies |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/ui/frontend/src/api/types.ts` | PipelineStepMetadata: `system_key`/`user_key` made `string \| null`, removed @provisional JSDoc. PipelineListItem: `strategy_count`/`step_count` made `number \| null`, added `registry_model_count: number \| null` and `error: string \| null`, removed @provisional JSDoc |
| `llm_pipeline/ui/frontend/src/routes/pipelines.tsx` | Replaced stub with full implementation: zodValidator search schema (`?pipeline=`), `usePipelines` hook, `handleSelect` navigation, left-right panel layout wiring PipelineList and PipelineDetail |

## Commits Made

| Hash | Message |
| --- | --- |
| `f8dd862` | `docs(implementation-A): master-40-pipeline-structure-view` |
| `d3bf029` | `docs(implementation-B): master-40-pipeline-structure-view` |
| `d6fc886` | `docs(implementation-C): master-40-pipeline-structure-view` |

## Deviations from Plan

- Step 4 implementation notes mention `step-4-create-strategysection-steprow.md` was not separately committed -- steps 2-5 (all Group B components) were bundled into the single `implementation-B` commit (`d3bf029`) alongside their step notes. Plan grouped them as Group B so this is consistent, not a deviation.
- Badge variant for step count was `variant="outline"` (plan did not specify; plan said "badge showing step count"). Chose "outline" to visually differentiate from strategy count ("secondary") and error ("destructive").
- StepRow `Link` uses `from="/pipelines"` prop for cross-route type-safe navigation (plan showed pattern but did not specify the `from` prop; added for correctness per TanStack Router docs).
- `PipelineDetail` error guard uses `if (error || !data)` instead of just `if (error)` -- guards against undefined data when `enabled: false` race condition occurs.

## Issues Encountered

None -- all backend endpoints existed (tasks 24/31), all frontend hooks existed, no missing dependencies.

## Success Criteria

- [x] `src/api/types.ts` PipelineListItem has `registry_model_count: number | null`, `error: string | null`, `strategy_count: number | null`, `step_count: number | null`
- [x] `src/api/types.ts` PipelineStepMetadata has `system_key: string | null`, `user_key: string | null`
- [x] @provisional JSDoc tags removed from PipelineListItem and PipelineStepMetadata
- [x] `src/components/pipelines/PipelineList.tsx` renders list with loading/error/empty states
- [x] `src/components/pipelines/JsonTree.tsx` renders collapsible tree with depth-based default collapse
- [x] `src/components/pipelines/StrategySection.tsx` renders strategy header + StepRow list, handles strategy.error
- [x] `src/components/pipelines/PipelineDetail.tsx` renders full pipeline detail with strategies, registry models, execution order, input schema
- [x] `src/routes/pipelines.tsx` uses zodValidator search schema with `?pipeline=` param
- [x] Selecting a pipeline in left panel updates URL and loads detail in right panel
- [x] Prompt key links (system_key/user_key) navigate to `/prompts?key=<key>` when clicked
- [x] TypeScript compilation passes with no new errors
- [x] No new npm dependencies, Zustand stores, or backend endpoints added

## Recommendations for Follow-up

1. Remove remaining `@provisional` JSDoc tags from `ExtractionMetadata`, `TransformationMetadata`, `PipelineStrategyMetadata`, and `PipelineMetadata` once those types are validated against the live backend (out of scope for task 40 per plan).
2. `registry_model_count` from `PipelineListItem` is currently unused in PipelineList (reserved per step-2 notes); consider adding it as a badge in the list row or as a count in the PipelineDetail header alongside the registry_models badge list.
3. JsonTree could be promoted to a shared component (e.g. `src/components/ui/JsonTree.tsx`) if other views (run detail, step debug panels) need schema display -- currently scoped to `components/pipelines/`.
4. PipelineDetail fetches on every `pipelineName` change with no stale-while-revalidate tuning; if pipelines are large or the backend is slow, consider adding `staleTime` to the `usePipeline` query config.
