# IMPLEMENTATION - STEP 6: UPDATE TESTS
**Status:** completed

## Summary
Updated ContextEvolution.test.tsx: accumulated step 2 context snapshot, removed raw-JSON assertion test, added two new JsonDiff-aware tests verifying green addition rendering and new-key detection between steps.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx`

Accumulated step 2 context_snapshot, removed old test, added two new tests.

```
# Before
mockSnapshots step 2: { result: 42, tags: ['a', 'b'] }   // non-accumulated

test 'renders JSON snapshots as formatted text':
  getByText(/"input": "raw data"/)   // raw JSON string, no longer rendered

# After
mockSnapshots step 2: { input: 'raw data', extracted: true, result: 42, tags: ['a', 'b'] }  // accumulated

test 'renders addition for first step keys':
  getAllByText('+').length >= 2      // step 1 before={} → all keys are CREATE
  span containing 'input' present
  span containing 'extracted' present

test 'renders changes between steps':
  getAllByText('+').length >= 4      // step 1: 2 + step 2: 2 new keys
  span containing 'result' present
  span containing 'tags' present
```

## Decisions
### Text matcher approach for key names
**Choice:** Custom function matcher `(_, el) => el?.tagName === 'SPAN' && el.textContent?.includes('key')` rather than exact string match
**Rationale:** JsonDiff renders key and value as separate text nodes within the same `<span>`. The span's textContent combines them (e.g. `input: "raw data"`). Exact string match on `input` alone would hit multiple elements across steps. The function matcher targets the correct `<span>` elements without being brittle to value formatting changes.

### Addition marker count
**Choice:** Assert `>= 2` for step 1 and `>= 4` total for step 2 rather than exact counts
**Rationale:** Exact counts couple tests to sort order and implementation details. Lower-bound assertions verify the presence of green additions while remaining resilient to future key additions or ordering changes.

## Verification
- [x] mockSnapshots step 2 uses accumulated context (includes step 1 keys)
- [x] test 'renders JSON snapshots as formatted text' removed
- [x] test 'renders addition for first step keys' added and passes
- [x] test 'renders changes between steps' added and passes
- [x] retained: 'renders step names as headers', 'shows loading skeleton with animate-pulse elements', 'shows error text when isError', 'shows empty state message'
- [x] loading skeleton test passes (6 animate-pulse elements)
- [x] all 6 tests pass: `npx vitest run src/components/runs/ContextEvolution.test.tsx`
