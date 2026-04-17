# IMPLEMENTATION - STEP 5: FRONTEND API LAYER - VARIANTS + RUN TYPES
**Status:** completed

## Summary
Added frontend API contract layer for variants: TS interfaces mirroring backend Pydantic models, fetch functions, and TanStack Query hooks (queries + mutations). Extended `RunListItem` with `variant_id` and `delta_snapshot`. Extended `TriggerRunRequest` and `useTriggerEvalRun` to accept optional `variant_id`. Added `variants` + `variant` key factories to `queryKeys.evals`. No UI components; contract-only for Group D consumption.

## Files
**Created:** none
**Modified:**
- llm_pipeline/ui/frontend/src/api/evals.ts
- llm_pipeline/ui/frontend/src/api/query-keys.ts

**Deleted:** none

## Changes

### File: `llm_pipeline/ui/frontend/src/api/evals.ts`
Added variant interfaces (`InstructionDeltaOp`, `InstructionDeltaItem`, `VariantDelta`, `VariantItem`, `VariantCreateRequest`, `VariantUpdateRequest`, `VariantListResponse`). Extended `RunListItem` with `variant_id: number | null` and `delta_snapshot: Record<string, unknown> | null` (inherited by `RunDetail`). Extended `TriggerRunRequest` with optional `variant_id`. Added `fetchVariants`, `fetchVariant`, `createVariant`, `updateVariant`, `deleteVariant`. Added TanStack Query hooks `useVariants`, `useVariant`, `useCreateVariant`, `useUpdateVariant`, `useDeleteVariant`. Mutations invalidate `queryKeys.evals.variants(datasetId)` on create/delete; update invalidates both list and detail.

```
# Before
export interface RunListItem {
  id: number
  dataset_id: number
  status: string
  total_cases: number
  passed: number
  failed: number
  errored: number
  started_at: string
  completed_at: string | null
}
export interface TriggerRunRequest {
  model?: string | null
}

# After
export interface RunListItem {
  id: number
  dataset_id: number
  status: string
  total_cases: number
  passed: number
  failed: number
  errored: number
  started_at: string
  completed_at: string | null
  variant_id: number | null
  delta_snapshot: Record<string, unknown> | null
}
export interface TriggerRunRequest {
  model?: string | null
  variant_id?: number | null
}

// variant interfaces + fetch fns + hooks appended
```

### File: `llm_pipeline/ui/frontend/src/api/query-keys.ts`
Added `variants` and `variant` factories under `queryKeys.evals`, matching existing `runs`/`run` factory style.

```
# Before
evals: {
  all: ['evals'] as const,
  list: ...,
  detail: ...,
  runs: ...,
  run: ...,
  schema: ...,
}

# After
evals: {
  all: ['evals'] as const,
  list: ...,
  detail: ...,
  runs: ...,
  run: ...,
  schema: ...,
  variants: (datasetId: number) => ['evals', datasetId, 'variants'] as const,
  variant: (datasetId: number, variantId: number) =>
    ['evals', datasetId, 'variants', variantId] as const,
}
```

## Decisions

### VariantUpdateRequest shape
**Choice:** `export type VariantUpdateRequest = Partial<VariantCreateRequest>`
**Rationale:** Backend `VariantUpdateRequest` has all three fields optional for partial PUT updates. Using `Partial<VariantCreateRequest>` keeps the TS surface minimal and prevents drift — any future field added to create auto-propagates to update.

### `InstructionDeltaItem.default` typing
**Choice:** `default?: unknown`
**Rationale:** Backend accepts JSON-scalar, list of scalars, or flat dict of scalars (validated via `json.dumps` round-trip). TS `unknown` is the safest client-side type without duplicating the Python whitelist logic.

### Error handling for 422 delta validation
**Choice:** Rely on existing `apiClient` behavior — it throws `ApiError(status, detail)` on non-OK and preserves the backend `detail` string. No custom onError in mutation hooks.
**Rationale:** Group D needs the raw `ApiError` to display ACE-hygiene validation errors inline in the variant editor. Adding an `onError` toast here would double-report (since `apiClient` already toasts non-OK responses when `silent` is not set). The thrown error propagates to `mutation.error` for UI consumption. Group D can pass `silent: true` at the fetch level if they want to control display.

### Mutation invalidation scope
**Choice:** Create/delete invalidate only `variants(datasetId)` list. Update invalidates both list and `variant(datasetId, id)` detail.
**Rationale:** Matches `useCreateCase`/`useUpdateCase`/`useDeleteCase` patterns already in the file. Narrow invalidation avoids wasteful refetches.

## Verification
- [x] Read current state of both files before editing (no clobbering of prior session work)
- [x] `npx tsc --noEmit` passes with no errors
- [x] All fetch functions use existing `apiClient<T>` wrapper (same pattern as dataset/case fetches)
- [x] `VariantItem` shape mirrors backend `VariantItem` in `llm_pipeline/ui/routes/evals.py` (id, dataset_id, name, description, delta, created_at, updated_at)
- [x] `VariantDelta` mirrors backend delta dict shape (model, system_prompt, user_prompt, instructions_delta with op/field/type_str/default)
- [x] `TriggerRunRequest.variant_id` matches backend `TriggerRunRequest.variant_id: Optional[int]`
- [x] Query keys use same style as existing factory (`['evals', datasetId, 'variants'] as const`)
- [x] Mutation hooks invalidate the contract-specified keys (list on create/delete; list + detail on update)
- [x] No UI components, no route files touched
- [x] No backend Python modified
