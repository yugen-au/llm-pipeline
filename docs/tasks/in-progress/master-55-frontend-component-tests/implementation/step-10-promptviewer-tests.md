# IMPLEMENTATION - STEP 10: PROMPTVIEWER TESTS
**Status:** completed

## Summary
Created RTL tests for the hook-dependent PromptViewer component, mocking usePromptDetail at module level. All 6 tests pass covering null selection, loading, error, single variant (no tabs), multiple variants (tabs), and variable placeholder highlighting.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.test.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/prompts/PromptViewer.test.tsx`
New test file with 6 tests:
- `shows "Select a prompt" when promptKey=null` -- renders empty state text
- `shows loading skeleton when isLoading=true` -- asserts `.animate-pulse` divs
- `shows error state when error is set` -- asserts "Failed to load prompt" text
- `renders prompt content for single variant (no tabs)` -- asserts content visible, no tablist role
- `renders Tabs for multiple variants` -- asserts tablist with 2 tab triggers matching prompt_type values
- `highlights {variable} placeholders in content` -- asserts 2 `span.text-primary` elements with correct variable text

Mock pattern: `vi.mock('@/api/prompts')` with `mockUsePromptDetail` fn, consistent with established StepDetailPanel/RunsTable patterns. Helper `makeVariant()` factory produces valid PromptVariant objects with overrides.

## Decisions
### Mock return shape uses `error` not `isError`
**Choice:** Mock returns `{ data, isLoading, error }` matching useQuery's actual return shape
**Rationale:** PromptViewer destructures `error` (not `isError`) from usePromptDetail, so mock must match

### Variable highlight assertion via CSS class selector
**Choice:** Query `span.text-primary` elements to verify highlighting
**Rationale:** The highlightVariables function wraps matched placeholders in `<span className="... text-primary">`. Querying by class is the most direct assertion for styled wrapper spans without adding test IDs.

## Verification
[x] All 6 tests pass (`npx vitest run PromptViewer` -- 6 passed, 0 failed)
[x] No QueryClientProvider wrapping used
[x] Test file co-located next to source
[x] Hook mocked at module level with vi.mock()
[x] No new npm packages added
