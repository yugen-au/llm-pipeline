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

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
- [x] MEDIUM: `variable_definitions` drift — backend runner consumes `variant_delta["variable_definitions"]` but TS `VariantDelta` does not declare it. CEO direction: extend UI types. Added optional `variable_definitions?: VariableDefinitions | null` to `VariantDelta` plus supporting `VariableDefinitionEntry` / `VariableDefinitions` types.
- [x] MEDIUM: whitelist drift — frontend variant editor hard-codes `TYPE_WHITELIST`. Added single-source-of-truth fetcher `fetchDeltaTypeWhitelist()` + `useDeltaTypeWhitelist()` TanStack hook (`staleTime: Infinity`, `gcTime: Infinity`) pointing at `GET /api/evals/delta-type-whitelist`. Step 6 will swap the hard-coded constant for this hook.
- [x] LOW: `type_str` lax typing — replaced `type_str: string` with literal union `DeltaTypeStr` mirroring backend `_TYPE_WHITELIST` (10 values: str, int, float, bool, list, dict, Optional[str|int|float|bool]).

### Changes Made

#### File: `llm_pipeline/ui/frontend/src/api/evals.ts`
Added `DeltaTypeStr` literal union, `VariableDefinitionEntry` / `VariableDefinitions` types, `TypeWhitelistResponse`, tightened `InstructionDeltaItem.type_str`, extended `VariantDelta` with optional `variable_definitions`, added `fetchDeltaTypeWhitelist()` + `useDeltaTypeWhitelist()` hook.

```ts
// Before
export interface InstructionDeltaItem {
  op: InstructionDeltaOp
  field: string
  type_str: string
  default?: unknown
}

export interface VariantDelta {
  model: string | null
  system_prompt: string | null
  user_prompt: string | null
  instructions_delta: InstructionDeltaItem[] | null
}

// After
export type DeltaTypeStr =
  | 'str' | 'int' | 'float' | 'bool' | 'list' | 'dict'
  | 'Optional[str]' | 'Optional[int]' | 'Optional[float]' | 'Optional[bool]'

export interface InstructionDeltaItem {
  op: InstructionDeltaOp
  field: string
  type_str: DeltaTypeStr
  default?: unknown
}

export interface VariableDefinitionEntry {
  type: string
  description?: string
  auto_generate?: string
  [key: string]: unknown
}
export type VariableDefinitions = Record<string, VariableDefinitionEntry>

export interface VariantDelta {
  model: string | null
  system_prompt: string | null
  user_prompt: string | null
  instructions_delta: InstructionDeltaItem[] | null
  variable_definitions?: VariableDefinitions | null
}

export interface TypeWhitelistResponse { types: DeltaTypeStr[] }

export function fetchDeltaTypeWhitelist(): Promise<TypeWhitelistResponse> {
  return apiClient<TypeWhitelistResponse>('/evals/delta-type-whitelist')
}

export function useDeltaTypeWhitelist() {
  return useQuery({
    queryKey: queryKeys.evals.deltaTypeWhitelist(),
    queryFn: fetchDeltaTypeWhitelist,
    staleTime: Infinity,
    gcTime: Infinity,
  })
}
```

`VariableDefinitionEntry` mirrors existing `PromptVariant.variable_definitions` shape in `api/types.ts` (`Record<string, { type; description; auto_generate? }>`), with an `[key: string]: unknown` index signature so unknown backend-side fields round-trip without silent drops.

#### File: `llm_pipeline/ui/frontend/src/api/query-keys.ts`
Added `deltaTypeWhitelist` to the `evals` key factory, following the existing `as const` tuple style.

```ts
// Before (excerpt)
    variants: (datasetId: number) => ['evals', datasetId, 'variants'] as const,
    variant: (datasetId: number, variantId: number) =>
      ['evals', datasetId, 'variants', variantId] as const,
  },

// After (excerpt)
    variants: (datasetId: number) => ['evals', datasetId, 'variants'] as const,
    variant: (datasetId: number, variantId: number) =>
      ['evals', datasetId, 'variants', variantId] as const,
    deltaTypeWhitelist: () => ['evals', 'delta-type-whitelist'] as const,
  },
```

### Downstream impact (for Group D / Step 6)
The stricter `DeltaTypeStr` union surfaces one pre-existing compile-time laxness in the Step 6 editor that Step 5 intentionally does NOT fix (out of scope per contract):

- `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.$variantId.tsx:387`
  `onValueChange={(v) => onChange({ type_str: v })}` — `v` is `string` from shadcn `Select`, target is `DeltaTypeStr`. Step 6 should change to `onChange({ type_str: v as DeltaTypeStr })` (mirroring the adjacent `op: v as InstructionDeltaOp` cast on line 353). The cast is safe because the `SelectItem` values are drawn from the (soon to be backend-sourced) whitelist.

Step 6 will also:
- Replace local `TYPE_WHITELIST` constant (lines 42-53) with `const { data } = useDeltaTypeWhitelist(); const TYPE_WHITELIST = data?.types ?? []`.
- Add a new editor section for `variable_definitions` (add/edit/remove rows) that populates the new `VariantDelta.variable_definitions` field.

Other in-repo callers of `InstructionDeltaItem.type_str` that were audited:
- `:120` `x.type_str !== y.type_str` — comparison, unaffected.
- `:158` `{ op: 'add', field: '', type_str: 'str', default: null }` — literal `'str'` is a valid `DeltaTypeStr`, unaffected.

### Verification
- [x] Read `api/evals.ts`, `api/query-keys.ts`, `api/types.ts`, `api/prompts.ts`, `components/prompts/PromptViewer.tsx`, and the Step 6 editor route before editing — confirmed existing `VariableDefinition`-like shape and reused it.
- [x] `DeltaTypeStr` literal union contains exactly the 10 values in backend `_TYPE_WHITELIST` — verified against `llm_pipeline/evals/delta.py`.
- [x] `useDeltaTypeWhitelist` uses `staleTime: Infinity` + `gcTime: Infinity` (types are immutable at runtime).
- [x] Query key `['evals', 'delta-type-whitelist'] as const` — matches contract string, `as const` tuple style consistent with factory.
- [x] `fetchDeltaTypeWhitelist()` calls `apiClient<TypeWhitelistResponse>('/evals/delta-type-whitelist')` — `apiClient` prefixes `/api`, so the resolved URL is `/api/evals/delta-type-whitelist` (matches backend router).
- [x] `VariantDelta.variable_definitions` is optional + nullable so existing construct sites (editor, new-variant route) keep compiling without change.
- [x] `npx tsc -b` reports exactly one error and it is in Step 6's file (line 387) — confirms the literal-union is doing its job and the break is localised to Group D's scope. No new errors in any other file. No errors in `api/evals.ts`, `api/query-keys.ts`, or any Step 7 compare-view file.
- [x] No UI components, no route files touched in this step — Step 6 / Group D owns the editor cast + whitelist consumption.
- [x] No backend Python modified.
