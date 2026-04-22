# IMPLEMENTATION - STEP 4: RENAME LABELS BASE/COMPARE
**Status:** completed

## Summary
Renamed all user-facing "Baseline"/"Variant" label strings to "Base"/"Compare" and renamed internal variables for consistency throughout the compare page component.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`

**User-facing label renames:**
- "Baseline" -> "Base" in card titles, column headers, markdown export labels
- "Variant" -> "Compare" in card titles, column headers, markdown export labels, stat card sub-labels
- "Baseline scores" -> "Base scores", "Variant scores" -> "Compare scores" in TableHead
- "Baseline output" -> "Base output", "Variant output" -> "Compare output" in detail panels
- "Baseline run #N" -> "Base run #N", "Variant run #N" -> "Compare run #N" in header
- "baseline: X -> variant: Y" -> "base: X -> compare: Y" in markdown case section headers
- `Baseline (#N)` -> `Base (#N)`, `Variant (#N)` -> `Compare (#N)` in aggregateComparisonTable headers
- evaluatorScoresBlock labels: 'Baseline' -> 'Base', 'Variant' -> 'Compare'
- "No delta_snapshot recorded for this variant run" -> "...this compare run"

**Internal variable/function renames:**
- `variantRunQ` -> `compareRunQ`
- `variantRun` -> `compareRun` (local state variable, not search param)
- `variantByName` -> `compareByName` (in both page component and buildPayloadMarkdown)
- `variantPassRate` -> `comparePassRate`
- `variantValue` prop -> `compareValue` (DeltaBadge, DeltaPctBadge, ComparisonStatCard)
- `variantResult` -> `compareResult` (caseDelta params, CaseRow/CaseDetailCard props)
- `baselineResult` -> `baseResult` (CaseRow/CaseDetailCard props)
- `BaselineOutputPanel` -> `BaseOutputPanel`
- `VariantOutputPanel` -> `CompareOutputPanel` (with internal baselineResult/variantResult -> baseResult/compareResult)
- `erroredInVariant` -> `erroredInCompare`
- `varFailing` -> `compareFailing`
- `variantRes`/`varStatus` -> `compareRes`/`compareStatus` in caseMarkdownSection
- `varStats` -> `compareStats` in aggregateComparisonTable
- `BuildPayloadArgs.variantRun` -> `BuildPayloadArgs.compareRun`

**Preserved (not renamed):**
- `variantRunId` in Zod schema (Step 3 handles search params)
- `variantQ` / `useVariant` (refers to the variant entity lookup, not comparison side)
- `ExportPayload.runs.baseline`/`ExportPayload.runs.variant` structural field names (Step 8 handles export restructuring)
- Type imports: `VariantDelta`, `VariantItem` (domain types)
- "Variant:" label showing variant entity name (domain term, not comparison side label)

## Decisions
### Keep "Variant:" entity label
**Choice:** Kept the "Variant:" label that shows the variant entity name when compareRun has a variant_id
**Rationale:** This refers to the domain concept (a variant configuration), not the comparison side label. Renaming it to "Compare:" would lose semantic meaning.

### Defer ExportPayload field renames
**Choice:** Left `runs.baseline`/`runs.variant` field names in ExportPayload interface unchanged
**Rationale:** Step 8 (export rewrite) handles full payload restructuring including replacing `variant` field with `comparison` field.

## Verification
[x] All user-facing "Baseline" labels replaced with "Base"
[x] All user-facing "Variant" labels (for comparison side) replaced with "Compare"
[x] Internal variables renamed consistently
[x] Component prop names updated at definition and all call sites
[x] TypeScript compiles without errors (npx tsc --noEmit)
[x] Zod schema variantRunId left untouched (Step 3 scope)
