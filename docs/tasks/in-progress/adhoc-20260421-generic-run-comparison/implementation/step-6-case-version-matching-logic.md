# IMPLEMENTATION - STEP 6: CASE VERSION MATCHING LOGIC
**Status:** completed

## Summary
Added client-side case version matching logic that computes matched/drifted/unmatched buckets per case, visual badges on drifted/unmatched rows, and a conditional aggregate scope toggle that filters stats to matched-only cases.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`

1. Added `VersionBucket` type and `computeCaseBucket()` function that determines matched/drifted/unmatched per case by comparing `case_versions` maps from both runs using `case_id` keys
2. Added `VersionBucketBadge` component showing amber "drifted" or muted "unmatched" badges (matched = no badge)
3. Extended the `useMemo` building `baseByName`/`compareByName`/`allCaseNames` to also compute `bucketByName`, `matchedCount`, `driftedCount`, `unmatchedCount`
4. Added `matchedOnly` state and `filteredCaseNames` memo for matched-only filtering
5. Added `useMemo` that recomputes pass rate and per-stat counts from filtered cases when `matchedOnly` is true
6. Added conditional aggregate scope toggle (segmented button: "All cases" / "Matched only") that only renders when `driftedCount + unmatchedCount > 0`
7. Updated stat cards to use filtered values (`statBasePassed`, etc.)
8. Added `bucket` prop to `CaseRow` component, rendered as inline badge next to case name

## Decisions
### Legacy run handling
**Choice:** Both runs with `case_versions === null` => matched; one null => matched
**Rationale:** Per plan spec and CEO decision -- legacy runs without version tracking assume shared name = same case

### No Switch component -- used segmented Button pair
**Choice:** Used two Button components with secondary/ghost variants as toggle
**Rationale:** No Switch UI component available in the project's shadcn setup; segmented buttons achieve the same UX

## Verification
[x] TypeScript compiles without errors (`npx tsc --noEmit` passes)
[x] computeCaseBucket handles all edge cases: missing result, both null, one null, version match, version mismatch
[x] Badge only shows for drifted/unmatched (matched = clean, no noise)
[x] Scope toggle conditionally rendered only when needed
[x] Stats cards use filtered values when matchedOnly active
[x] Step 7 delta summary area not modified

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
- [x] Issue #1 (Medium) — setState called during render in seed-expanded logic
- [x] Issue #7 (Low) — Unused `_caseName` param in `computeCaseBucket`

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`

**Fix #1:** Moved render-phase setState into `useEffect` (added `useEffect` to react import).
```
# Before
const seedKey = `${baseRun?.id ?? 0}-${compareRun?.id ?? 0}`
if (baseRun && compareRun && seedKey !== seededFor) {
  setExpanded(new Set(initialExpanded))
  setSeededFor(seedKey)
}

# After
const seedKey = `${baseRun?.id ?? 0}-${compareRun?.id ?? 0}`
useEffect(() => {
  if (baseRun && compareRun && seedKey !== seededFor) {
    setExpanded(new Set(initialExpanded))
    setSeededFor(seedKey)
  }
}, [seedKey, seededFor, initialExpanded, baseRun, compareRun])
```

**Fix #7:** Removed unused `_caseName` param from `computeCaseBucket` signature and updated call site.
```
# Before (signature)
function computeCaseBucket(
  _caseName: string,
  baseResult: CaseResultItem | undefined,
  ...
)

# Before (call site)
const bucket = computeCaseBucket(
  name,
  baseMap.get(name),
  cmpMap.get(name),
  baseRun,
  compareRun,
)

# After (signature)
function computeCaseBucket(
  baseResult: CaseResultItem | undefined,
  ...
)

# After (call site)
const bucket = computeCaseBucket(
  baseMap.get(name),
  cmpMap.get(name),
  baseRun,
  compareRun,
)
```

### Verification
- [x] `tsc --noEmit` passes with no errors
- [x] Seeding still happens exactly once per (baseRun, compareRun) pair via seedKey gate
- [x] Only call site of `computeCaseBucket` updated; signature and call match
- [x] Step 7 delta summary area untouched
