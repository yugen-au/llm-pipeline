# IMPLEMENTATION - STEP 3: ZOD SCHEMA COMPARERUNID + ALIAS
**Status:** completed

## Summary
Updated compare page Zod search schema to accept `compareRunId` as primary param with `variantRunId` as backward-compatible alias. Updated all search-param consumption sites and navigation calls.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx, llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx
**Deleted:** none

## Changes
### File: `evals.$datasetId.compare.tsx`
Zod schema now accepts both `compareRunId` and `variantRunId`, using `.transform()` to resolve into single `compareRunId` field. Destructured search params updated. Validation check and error message updated. Export filename updated.

```
# Before
const compareSearchSchema = z.object({
  baseRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
  variantRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
})

# After
const compareSearchSchema = z
  .object({
    baseRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
    compareRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
    variantRunId: fallback(z.coerce.number().int().positive(), 0).default(0),
  })
  .transform(({ baseRunId, compareRunId, variantRunId }) => ({
    baseRunId,
    compareRunId: compareRunId || variantRunId || 0,
  }))
```

### File: `evals.$datasetId.runs.$runId.tsx`
`handleCompare` navigation now passes `compareRunId` instead of `variantRunId`.

```
# Before
search: { baseRunId: baseline.id, variantRunId: runId },

# After
search: { baseRunId: baseline.id, compareRunId: runId },
```

## Decisions
### Internal variable renames deferred to Step 4
**Choice:** Did not rename `variantRunQ`, `variantRun`, `aggregateComparisonTable` param, etc.
**Rationale:** Step 4 handles all variable/label renames containing "variant". This step only changes the search param identity and its direct consumption.

## Verification
[x] Zod schema accepts both `compareRunId` and `variantRunId` params
[x] `.transform()` resolves `compareRunId ?? variantRunId ?? 0`
[x] Final validated shape has `baseRunId` and `compareRunId` (no `variantRunId`)
[x] All search-param destructuring uses `compareRunId`
[x] Navigation in runs detail uses `compareRunId`
[x] `tsc --noEmit` passes with no errors
