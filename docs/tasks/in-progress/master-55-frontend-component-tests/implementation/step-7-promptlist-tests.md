# IMPLEMENTATION - STEP 7: PROMPTLIST TESTS
**Status:** completed

## Summary
Created PromptList.test.tsx with 6 tests covering loading, error, empty, render, selection highlight, and click callback states.

## Files
**Created:** llm_pipeline/ui/frontend/src/components/prompts/PromptList.test.tsx
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/prompts/PromptList.test.tsx`
New test file with 6 tests:
- `shows loading skeleton when isLoading=true` - asserts `.animate-pulse` elements present
- `shows error message when error is an Error object` - passes `new Error('load failed')`, asserts `.text-destructive` with correct text
- `shows empty state when prompts=[]` - asserts `.text-muted-foreground` with "No prompts match filters"
- `renders a button per prompt` - passes 2 Prompt objects, asserts 2 buttons with correct names
- `highlights selected prompt` - asserts `bg-accent` class on selected button, absent on unselected
- `calls onSelect with prompt key on click` - clicks button via userEvent, asserts onSelect called with correct key

## Decisions
### ResizeObserver polyfill
**Choice:** Added `beforeAll` block stubbing `globalThis.ResizeObserver` in test file
**Rationale:** Radix ScrollArea uses ResizeObserver internally which jsdom doesn't provide. The click test triggers layout effects that hit this. Global setup.ts doesn't include this polyfill, so added locally to avoid modifying shared setup.

## Verification
[x] All 6 tests pass (`npx vitest run PromptList`)
[x] No new npm packages added
[x] No QueryClientProvider wrapping
[x] Test file co-located next to source

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] ResizeObserver not restored in afterAll - store original and restore matching PipelineList.test.tsx pattern

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/components/prompts/PromptList.test.tsx`
Added save/restore of original ResizeObserver reference to match PipelineList.test.tsx pattern.
```
# Before
// Radix ScrollArea uses ResizeObserver internally (not in jsdom)
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})

# After
// Radix ScrollArea uses ResizeObserver internally; polyfill for jsdom
const originalRO = globalThis.ResizeObserver
beforeAll(() => {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver
})
afterAll(() => {
  globalThis.ResizeObserver = originalRO
})
```

### Verification
[x] All 6 tests pass (`npx vitest run PromptList`)
[x] Pattern matches PipelineList.test.tsx
