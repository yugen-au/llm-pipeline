# IMPLEMENTATION - STEP 5: CREATE PIPELINEDETAIL
**Status:** completed

## Summary
Created PipelineDetail component for the right panel of the Pipeline Structure View. Renders full pipeline metadata including header (name, registry models, execution order, input schema) and strategy sections.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/pipelines/PipelineDetail.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/pipelines/PipelineDetail.tsx`
New file. Component handles four states:
- Empty state (no pipeline selected) -- centered muted text
- Loading state -- skeleton blocks (h-7 w-48, h-4 w-32, h-40)
- Error state -- centered destructive text
- Loaded state -- header with pipeline_name (h2), registry_models as Badge list, execution_order as ordered Badge list, pipeline_input_schema via JsonTree, then StrategySection for each strategy

Uses `usePipeline(pipelineName ?? '')` with early return for null pipelineName. Content wrapped in `<ScrollArea className="h-full">` with inner `<div className="space-y-6 p-4">`.

## Decisions
### Skeleton as inline component
**Choice:** Private `DetailSkeleton` function with animate-pulse divs (matching existing codebase pattern)
**Rationale:** Codebase uses inline SkeletonRows functions (PromptList, StepTimeline) rather than a shared Skeleton UI component. Consistency with existing pattern.

### Error guard includes !data
**Choice:** `if (error || !data)` instead of just `if (error)`
**Rationale:** When usePipeline returns with no error but data is undefined (e.g. enabled: false race), the error state message is safer than rendering undefined properties.

## Verification
[x] TypeScript compilation passes with no errors
[x] Component handles null pipelineName (empty state)
[x] Component handles loading state with skeleton
[x] Component handles error state
[x] Component renders registry_models as Badge list
[x] Component renders execution_order as ordered Badge list
[x] Component renders pipeline_input_schema via JsonTree when not null
[x] Component renders strategies via StrategySection
[x] Content wrapped in ScrollArea with space-y-6 p-4
[x] Imports match existing codebase conventions (@/ aliases)
