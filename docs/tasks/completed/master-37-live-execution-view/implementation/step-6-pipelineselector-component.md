# IMPLEMENTATION - STEP 6: PIPELINESELECTOR COMPONENT
**Status:** completed

## Summary
Created PipelineSelector component using shadcn/ui Select with usePipelines hook. Handles loading (skeleton), error, and empty states. Follows existing FilterBar pattern for Select usage.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/live/PipelineSelector.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/live/PipelineSelector.tsx`
New component with:
- Props: `selectedPipeline: string | null`, `onSelect: (name: string) => void`, `disabled?: boolean`
- `usePipelines()` hook for data fetching
- `SelectorSkeleton` -- inline loading state with animate-pulse pattern matching existing codebase convention (no separate Skeleton UI component)
- Error state: destructive text "Failed to load pipelines."
- Empty state: muted text "No pipelines registered"
- Normal state: labeled Select dropdown with pipeline names from `data.pipelines`
- `selectedPipeline` mapped from `null` to `undefined` for Radix Select compatibility (Radix requires `undefined` for no selection, not `null`)

## Decisions
### Skeleton pattern
**Choice:** Inline skeleton with animate-pulse divs
**Rationale:** Matches existing pattern in StepTimeline and RunsTable -- project does not have a shared Skeleton UI component

### Null-to-undefined mapping for Select value
**Choice:** `value={selectedPipeline ?? undefined}`
**Rationale:** Radix Select treats `null` differently from `undefined` -- passing `undefined` correctly shows the placeholder text

## Verification
[x] TypeScript compiles with no errors (`npx tsc --noEmit`)
[x] Component follows existing Select usage pattern (FilterBar.tsx)
[x] Loading/error/empty states all handled
[x] Props match contract spec exactly
