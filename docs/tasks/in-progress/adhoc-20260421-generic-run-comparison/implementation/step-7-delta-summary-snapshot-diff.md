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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] ISSUE #2 (Medium) — JsonViewer diff-mode prop typed as non-null but fed null values; call site force-casts via `as unknown as Record<string, unknown>`, silencing legitimate null handling at the JsonViewer boundary.

### Changes Made
#### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx`

Applied Option A: narrow types at construction time by filtering out null fields from baseConfig and compareConfig, then dropped the cast at the JsonViewer call site. Updated hasSnapshotData guard to use `Object.keys(...).length` on the filtered configs so partial nulls (one side has data, the other doesn't) render sensibly — the missing side shows as `{}` and the diff highlights the added/removed fields.

```
# Before
const baseConfig = useMemo(
  () => ({
    prompt_versions: baseRun?.prompt_versions ?? null,
    model_snapshot: baseRun?.model_snapshot ?? null,
  }),
  [baseRun],
)
const compareConfig = useMemo(
  () => ({
    prompt_versions: compareRun?.prompt_versions ?? null,
    model_snapshot: compareRun?.model_snapshot ?? null,
  }),
  [compareRun],
)
// ...
const hasSnapshotData =
  baseConfig.prompt_versions != null ||
  baseConfig.model_snapshot != null ||
  compareConfig.prompt_versions != null ||
  compareConfig.model_snapshot != null
// ...
<JsonViewer
  before={baseConfig as unknown as Record<string, unknown>}
  after={compareConfig as unknown as Record<string, unknown>}
  maxDepth={3}
/>

# After
const baseConfig = useMemo<Record<string, unknown>>(() => {
  const cfg: Record<string, unknown> = {}
  if (baseRun?.prompt_versions != null) cfg.prompt_versions = baseRun.prompt_versions
  if (baseRun?.model_snapshot != null) cfg.model_snapshot = baseRun.model_snapshot
  return cfg
}, [baseRun])
const compareConfig = useMemo<Record<string, unknown>>(() => {
  const cfg: Record<string, unknown> = {}
  if (compareRun?.prompt_versions != null) cfg.prompt_versions = compareRun.prompt_versions
  if (compareRun?.model_snapshot != null) cfg.model_snapshot = compareRun.model_snapshot
  return cfg
}, [compareRun])
// ...
const hasSnapshotData =
  Object.keys(baseConfig).length > 0 || Object.keys(compareConfig).length > 0
// ...
<JsonViewer
  before={baseConfig}
  after={compareConfig}
  maxDepth={3}
/>
```

### Verification
[x] TypeScript compiles without errors (`npx tsc --noEmit` passes)
[x] No `as unknown as` cast remains at the JsonViewer call site
[x] `hasSnapshotData` still correctly returns false when both runs have all-null snapshot fields (filtered configs empty on both sides)
[x] Partial nulls render sensibly — one-sided data yields `{}` vs populated object diff
[x] No changes to Step 6 scope (case matching, useMemo seeding, computeCaseBucket untouched)
