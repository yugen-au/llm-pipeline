# IMPLEMENTATION - STEP 11: PIPELINEDETAIL TESTS
**Status:** completed

## Summary
Created PipelineDetail.test.tsx with 6 tests covering null selection, loading, error, data rendering (badges, schema, strategies). Mocked usePipeline hook, StrategySection, and JsonTree to isolate the component.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/pipelines/PipelineDetail.test.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/pipelines/PipelineDetail.test.tsx`
New test file with 6 tests:
- `shows "Select a pipeline" when pipelineName=null` - verifies empty state
- `shows loading skeleton when isLoading=true` - asserts .animate-pulse elements
- `shows error state when error is set` - asserts "Failed to load pipeline" text
- `renders pipeline name, execution_order, and registry_models badges` - full data render with indexed execution order and model badges
- `renders JsonTree for pipeline_input_schema` - mocked JsonTree renders schema keys
- `renders StrategySection for each strategy` - 2 strategies, both names and testids visible

## Decisions
### Mock StrategySection and JsonTree
**Choice:** Mock both child components with simple stubs
**Rationale:** StrategySection uses TanStack Router Link which throws without router context. JsonTree is recursive. Mocking both keeps tests isolated and avoids brittle deep-render issues, per PLAN.md risk mitigation.

### ResizeObserver polyfill
**Choice:** Added globalThis.ResizeObserver stub in beforeAll
**Rationale:** Radix ScrollArea (used in PipelineDetail) depends on ResizeObserver which jsdom lacks. Same pattern used in PromptList.test.tsx.

## Verification
[x] All 6 tests pass (npx vitest run PipelineDetail - 6 passed)
[x] Co-located test file next to source
[x] Hook-level vi.mock() pattern used (no QueryClientProvider)
[x] No new npm packages added
