# IMPLEMENTATION - STEP 9: PIPELINESELECTOR TESTS
**Status:** completed

## Summary
Created PipelineSelector.test.tsx with 6 tests covering loading, error, empty, data rendering, selection callback, and disabled states. Uses hook-level vi.mock() pattern for usePipelines.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/live/PipelineSelector.test.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/live/PipelineSelector.test.tsx`
New test file with 6 tests:
- `shows loading skeleton when isLoading=true` - asserts `.animate-pulse` elements present
- `shows error state when isError=true` - asserts "Failed to load pipelines." text
- `shows "No pipelines registered" when pipelines=[]` - asserts empty state text
- `renders Select with pipeline options when data present` - opens combobox, asserts 2 option roles
- `calls onSelect with pipeline name on selection` - clicks option, asserts mock called with name
- `disables Select when disabled=true` - asserts combobox is disabled

Mock pattern: `const mockUsePipelines = vi.fn()` + `vi.mock('@/api/pipelines', () => ({ usePipelines: () => mockUsePipelines() }))` with `beforeEach` setting default return value `{ data: { pipelines: [...] }, isLoading: false, isError: false }`.

## Decisions
### Mock shape matches component access pattern
**Choice:** `{ data: { pipelines: PipelineListItem[] }, isLoading, isError }`
**Rationale:** Component accesses `data?.pipelines`, matching the TanStack Query return shape where `data` is the API response `{ pipelines: [...] }`.

## Verification
[x] All 6 tests pass (npx vitest run PipelineSelector)
[x] No QueryClientProvider wrapping used
[x] Test file co-located next to source
[x] Follows established hook-level vi.mock() pattern from StepDetailPanel.test.tsx
[x] No new npm packages added
