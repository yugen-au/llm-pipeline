# IMPLEMENTATION - STEP 2: CREATE PIPELINELIST
**Status:** completed

## Summary
Created PipelineList sub-component following the exact pattern from PromptList.tsx. Renders pipeline list with loading skeleton, error, empty, and populated states. Each row shows pipeline name with conditional badges for step count, error, and strategy count.

## Files
**Created:** `llm_pipeline/ui/frontend/src/components/pipelines/PipelineList.tsx`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/pipelines/PipelineList.tsx`
New file. Component with props `{ pipelines, selectedName, onSelect, isLoading, error }`. Renders:
- 6x skeleton rows (animate-pulse h-12) when loading
- Error message (text-destructive) when error
- Empty state (text-muted-foreground) when no pipelines
- ScrollArea-wrapped button list with conditional badges:
  - Error badge (variant="destructive") if pipeline.error is non-null
  - Step count badge (variant="outline") if step_count is non-null and no error
  - Strategy count badge (variant="secondary") if strategy_count is non-null

## Decisions
### Badge display logic for error vs step count
**Choice:** Show error badge instead of step count when pipeline.error is present; show step count otherwise
**Rationale:** Error state is more important than counts; showing both would be noisy. Strategy count still shows alongside error since it may still be valid metadata.

### Badge variant for step count
**Choice:** variant="outline" for step count badge
**Rationale:** Plan specified step count badge but not its variant. Using "outline" differentiates from strategy count ("secondary") and error ("destructive"), matching the visual hierarchy.

## Verification
[x] TypeScript compilation passes (npx tsc --noEmit)
[x] Component follows PromptList.tsx pattern exactly (same skeleton, error, empty, ScrollArea structure)
[x] All PipelineListItem fields handled (name, step_count, strategy_count, error; registry_model_count reserved for detail view)
[x] Nullable fields guarded with != null checks
