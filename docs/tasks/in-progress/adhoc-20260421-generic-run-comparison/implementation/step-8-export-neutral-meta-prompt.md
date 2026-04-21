# IMPLEMENTATION - STEP 8: EXPORT NEUTRAL META-PROMPT
**Status:** completed

## Summary
Rewrote META_PROMPT and export payload to be comparison-neutral, removing all variant-specific language and framing from export functions.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`

1. Replaced META_PROMPT constant -- removed variant iteration language, replaced with neutral "Eval Run Comparison Context" framing
2. ExportPayload interface -- replaced `variant` field with `comparison: { base_run_id, compare_run_id }`, renamed `runs.baseline`/`runs.variant` to `runs.base`/`runs.compare`
3. BuildPayloadArgs interface -- removed `variant: VariantItem | undefined` and `variantId: number | null`
4. buildPayloadJSON -- removed variant lookup, added `comparison` field with run IDs, updated runs keys
5. buildPayloadMarkdown -- replaced `## Current variant` section with `## Comparison summary` showing base vs compare run IDs, updated all `runs.baseline`/`runs.variant` refs
6. buildArgs() -- removed `variant`/`variantId` from returned object

Items already done by prior steps (verified, no changes needed):
- exportFilename already uses compareRunId
- aggregateComparisonTable already uses "Base (#N)" / "Compare (#N)"
- caseMarkdownSection already uses "base" / "compare" labels

## Decisions
### Keep useVariant for header display
**Choice:** Retained `useVariant` hook and `VariantItem` import for header variant name display
**Rationale:** The header conditionally shows variant name when compareRun has variant_id -- this is display-only context, not export payload

## Verification
[x] TypeScript compiles without errors (tsc --noEmit)
[x] META_PROMPT contains no variant-specific language
[x] ExportPayload has comparison field instead of variant field
[x] buildPayloadJSON builds comparison-neutral payload
[x] buildPayloadMarkdown uses "Comparison summary" instead of "Current variant"
[x] BuildPayloadArgs and buildArgs() have no variant/variantId references
