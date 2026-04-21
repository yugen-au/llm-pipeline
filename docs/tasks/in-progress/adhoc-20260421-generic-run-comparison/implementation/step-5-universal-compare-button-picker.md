# IMPLEMENTATION - STEP 5: UNIVERSAL COMPARE BUTTON + PICKER
**Status:** completed

## Summary
Replaced the variant-only compare button on the run detail page with a universal "Compare" button that opens a run picker dialog. Any completed run in the same dataset can now be compared against the current run.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx`

1. Added Dialog component imports (Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription)
2. Removed `findMostRecentBaseline` helper function -- no longer needed
3. Removed `isVariantRun`, `baseline`, `canCompare`, `compareDisabled` state vars
4. Added `pickerOpen` state and `completedRuns` derived list (filtered by status=completed, excluding current run, sorted by started_at desc)
5. Replaced `handleCompare()` with `handlePickRun(selectedRunId)` -- navigates with `baseRunId=selectedRunId, compareRunId=runId`
6. Replaced variant-gated compare button block with universal compare button: always visible, disabled only when no other completed runs exist (with tooltip), opens picker dialog on click
7. Added `RunPickerDialog` component inline -- Dialog with scrollable list of completed runs showing run ID, started_at, pass rate, variant tag; "Select" button per row
8. Rendered `RunPickerDialog` at bottom of page JSX

## Decisions
### Navigation param ordering
**Choice:** Selected run is `baseRunId` (reference), current run is `compareRunId` (target)
**Rationale:** Matches plan spec -- the run you're viewing is the "compare target" and you pick what to compare it against as the "base reference"

### Dialog vs dropdown
**Choice:** Full Dialog with scrollable list
**Rationale:** Per plan architecture decision -- dialog is more discoverable and handles many runs better than an inline dropdown

## Verification
[x] No variant-gating remains on compare button
[x] findMostRecentBaseline fully removed
[x] pickerOpen state controls dialog open/close
[x] completedRuns filters status=completed, excludes current run, sorted desc
[x] RunPickerDialog shows run ID, started_at, pass rate, variant tag
[x] Navigation uses compareRunId (not variantRunId)
[x] Dialog imports from existing shadcn component
[x] useState already imported
