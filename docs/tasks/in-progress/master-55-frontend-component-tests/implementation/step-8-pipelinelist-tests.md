# IMPLEMENTATION - STEP 8: PIPELINELIST TESTS
**Status:** completed

## Summary
Created 8 RTL tests for PipelineList covering loading, error, empty, rendering, badge mutual exclusivity, click handler, and selection highlight states.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/pipelines/PipelineList.test.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/pipelines/PipelineList.test.tsx`
New test file with 8 tests:
- `shows loading skeleton when isLoading=true` - asserts `.animate-pulse` elements present
- `shows error message when error is an Error object` - asserts "Failed to load pipelines" with `.text-destructive`
- `shows empty state when pipelines=[]` - asserts "No pipelines found" with `.text-muted-foreground`
- `renders a button per pipeline` - 2 PipelineListItem objects, asserts 2 buttons
- `shows step count badge when pipeline has no error` - asserts outline variant badge with step count, no destructive badges
- `shows destructive error badge instead of step count when pipeline.error != null` - asserts destructive variant badge, no step count badge (mutual exclusivity)
- `calls onSelect on click` - userEvent click, asserts mock called with pipeline name
- `highlights selected pipeline` - asserts `bg-accent` class on selected, absent on other

## Decisions
### ResizeObserver polyfill
**Choice:** Added file-level `beforeAll`/`afterAll` polyfill for `ResizeObserver`
**Rationale:** Radix ScrollArea uses ResizeObserver internally which is missing in jsdom. The polyfill is needed when `userEvent.setup()` triggers layout effects. Scoped to this test file rather than global setup to avoid side effects.

### Badge variant assertion via data-variant
**Choice:** Used `data-variant` attribute on `[data-slot="badge"]` elements to assert destructive vs outline
**Rationale:** The Badge component renders `data-variant={variant}` providing a reliable, semantic way to distinguish badge variants without relying on CSS class strings.

## Verification
[x] All 8 tests pass (`npx vitest run PipelineList` exits 0)
[x] Co-located test file next to source
[x] No QueryClientProvider wrapping
[x] No new npm packages
[x] Badge mutual exclusivity verified (destructive vs outline)
