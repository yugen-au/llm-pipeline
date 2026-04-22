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

---

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
- [x] ISSUE #4 (Medium) -- RunPickerDialog Select buttons lack aria-label with run context (screen readers announce "Select button" with no identifying info)

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx`
Added descriptive `aria-label` to each Select button inside RunPickerDialog so screen readers announce the run id, variant (if any), start time, and pass rate. Factored `startedLabel` and `variantLabel` out of JSX so the aria-label and visible text share the same formatted values.

```
# Before
{runs.map((r) => {
  const passRate =
    r.total_cases > 0 ? `${r.passed}/${r.total_cases}` : '--'
  return (
    <div ...>
      <div ...>
        <div className="text-xs text-muted-foreground">
          {r.started_at ? new Date(r.started_at).toLocaleString() : 'N/A'}
          {' -- '}
          pass rate {passRate}
        </div>
      </div>
      <Button variant="outline" size="sm" onClick={() => onSelect(r.id)}>
        Select
      </Button>
    </div>
  )
})}

# After
{runs.map((r) => {
  const passRate =
    r.total_cases > 0 ? `${r.passed}/${r.total_cases}` : '--'
  const startedLabel = r.started_at
    ? new Date(r.started_at).toLocaleString()
    : 'N/A'
  const variantLabel =
    r.variant_id != null ? ` (variant #${r.variant_id})` : ''
  return (
    <div ...>
      <div ...>
        <div className="text-xs text-muted-foreground">
          {startedLabel}
          {' -- '}
          pass rate {passRate}
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        onClick={() => onSelect(r.id)}
        aria-label={`Select run #${r.id}${variantLabel} started ${startedLabel} with pass rate ${passRate}`}
      >
        Select
      </Button>
    </div>
  )
})}
```

Row-level keyboard focus enhancement intentionally out of scope per fix directive (small lists, acceptable UX).

### Verification
- [x] aria-label template includes run id, optional variant id, formatted start time, and pass rate
- [x] Visible text unchanged (startedLabel substituted for identical inline expression)
- [x] No new imports required
