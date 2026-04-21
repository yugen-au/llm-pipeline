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
