# IMPLEMENTATION - STEP 7: DELTA SUMMARY SNAPSHOT DIFF
**Status:** completed

## Summary
Replaced the variant-gated delta summary card with a snapshot-based configuration diff that works for any two runs. The card now diffs `prompt_versions` and `model_snapshot` from both runs directly, removing the dependency on `delta_snapshot`, prod-config fetches, and the `buildBefore`/`buildAfter` helper pipeline.

## Files
**Created:** none
**Modified:** `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`

1. **Removed dead code:** `EffectiveConfig` interface, `applyVarDefsDelta`, `buildBefore`, `buildAfter` functions -- all only used by old delta card logic
2. **Removed `VariantDelta` type import** -- no longer needed after removing `buildAfter`
3. **Updated comment** on `prodPromptsQ`/`prodModelQ` hooks -- they now serve export only, not the delta card
4. **Replaced delta summary state block:** Removed `deltaSnapshot`, `prodPromptsSettled`, `prodModelSettled`, `summaryLoading`, `bothProdErrored`, `summaryReady`, `summaryBefore`, `summaryAfter`. Added `baseConfig` and `compareConfig` (memoized objects from `baseRun.prompt_versions`/`model_snapshot` and `compareRun.prompt_versions`/`model_snapshot`) plus `hasSnapshotData` boolean.
5. **Replaced delta summary card JSX:** Card title changed from "Delta summary" to "Configuration diff". Renders `JsonViewer` with `before={baseConfig}` / `after={compareConfig}` when `hasSnapshotData` is true; otherwise shows "No snapshot data recorded for either run" fallback. No loading state needed since data comes from already-loaded run objects.
6. **Kept `useVariant` hook** -- still used in page header (variant name display) and export `buildArgs`
7. **Kept `useDatasetProdPrompts`/`useDatasetProdModel` hooks** -- still used by export payload builder

## Decisions
### Keep prod-config hooks despite delta card removal
**Choice:** Retained `useDatasetProdPrompts` and `useDatasetProdModel`
**Rationale:** Still consumed by `buildArgs()` for the export payload builder (Step 8 scope)

### Keep useVariant hook
**Choice:** Retained `useVariant` with conditional lookup (`compareRun.variant_id ?? 0`)
**Rationale:** Still referenced in header (line showing variant name when `variant_id` is non-null) and in export `buildArgs`

### Renamed card title
**Choice:** Changed "Delta summary" to "Configuration diff"
**Rationale:** More accurate for generic snapshot comparison; "delta" implied variant-specific semantics

## Verification
[x] TypeScript compiles without errors (`npx tsc --noEmit` passes)
[x] Delta summary card renders for any two runs (not gated on `delta_snapshot`)
[x] Fallback shows "No snapshot data recorded" when both configs are all-null
[x] No modifications to case row rendering or aggregate stats (Step 6 scope preserved)
[x] `useVariant`, `useDatasetProdPrompts`, `useDatasetProdModel` retained for non-delta-card usages
