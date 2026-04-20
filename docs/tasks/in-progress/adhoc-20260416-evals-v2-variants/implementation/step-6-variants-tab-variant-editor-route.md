# IMPLEMENTATION - STEP 6: VARIANTS TAB + VARIANT EDITOR ROUTE
**Status:** completed

## Summary
Added the variant authoring UI layer on top of the Step 5 API hooks:
- Variants tab on the dataset detail page listing variants with create/delete/edit affordances.
- Split-pane variant editor route (`/evals/{datasetId}/variants/{variantId}`) with a read-only prod step def pane (left) and editable delta pane (right) covering all 4 delta sections (model, system prompt, user prompt, instructions_delta).
- Separate "new variant" route (`/evals/{datasetId}/variants/new`) that POSTs a blank variant and redirects to the editor (ref-guarded to survive StrictMode double-mount).
- Dirty tracking (baseline vs. live state comparison), Save/Discard buttons, "Run with Variant" button that triggers `useTriggerEvalRun({ variant_id })` and navigates back to the dataset.
- Backend 422 dry-run rejection surfaced verbatim: global banner + per-row inline error matched to the offending field name when possible.
- UI info banner in the instructions-delta section explicitly states that inherited `LLMResultMixin` fields (`confidence_score`, `notes`) cannot be removed in v2 (research/CEO decision); fields typed with those names also get an inline amber tooltip.
- Type dropdown is whitelisted to exactly the 10 backend-allowed `type_str` values; op dropdown restricted to `add | modify`; `instructions_delta` array capped at 50 entries UI-side with both near-cap warning and hard cap lockout.

## Files
**Created:**
- llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.$variantId.tsx
- llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.new.tsx

**Modified:**
- llm_pipeline/ui/frontend/src/routes/evals.$datasetId.index.tsx

**Deleted:** none

## Changes

### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.index.tsx`
Added a third `Variants` tab between Cases and Run History, a `VariantsTab` component that lists variants and wires the "New Variant" button to `/evals/{datasetId}/variants/new`, and per-row Delete (with `confirm`) / Edit navigation. Reused the existing `formatDate` helper and page-level `Tabs` component.

```
# Before
import { Plus, Trash2, Play, ArrowLeft } from 'lucide-react'
import {
  useDataset,
  useCreateCase,
  useUpdateCase,
  useDeleteCase,
  useDeleteDataset,
  useEvalRuns,
  useTriggerEvalRun,
  useInputSchema,
} from '@/api/evals'
import type { CaseItem, RunListItem, SchemaResponse } from '@/api/evals'

...

<Tabs defaultValue="cases">
  <TabsList>
    <TabsTrigger value="cases">
      Cases ({dataset.cases?.length ?? 0})
    </TabsTrigger>
    <TabsTrigger value="runs">Run History</TabsTrigger>
  </TabsList>

# After
import { Plus, Trash2, Play, ArrowLeft, Pencil } from 'lucide-react'
import {
  useDataset,
  useCreateCase,
  useUpdateCase,
  useDeleteCase,
  useDeleteDataset,
  useEvalRuns,
  useTriggerEvalRun,
  useInputSchema,
  useVariants,
  useDeleteVariant,
} from '@/api/evals'
import type { CaseItem, RunListItem, SchemaResponse, VariantItem } from '@/api/evals'

...

// New VariantsTab component (inline) rendering variant table + "New Variant" button
// + per-row delete (with confirm()) that calls useDeleteVariant.

<Tabs defaultValue="cases">
  <TabsList>
    <TabsTrigger value="cases">
      Cases ({dataset.cases?.length ?? 0})
    </TabsTrigger>
    <TabsTrigger value="variants">Variants</TabsTrigger>
    <TabsTrigger value="runs">Run History</TabsTrigger>
  </TabsList>
  ...
  <TabsContent value="variants" className="mt-4">
    <VariantsTab datasetId={datasetId} />
  </TabsContent>
```

### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.$variantId.tsx` (new)
`VariantEditorPage` with a split-pane grid (`lg:grid-cols-2`). Left pane (`ProdStepDefPanel`) fetches the dataset + step schema via `useDataset`/`useInputSchema` and renders the instructions class' fields read-only (prod model/prompts are not exposed through an existing endpoint for arbitrary steps, so the pane documents that blanks inherit prod). Right pane (`VariantDeltaPanel`) hosts all 4 delta sections.

- Dirty tracking via `useVariantEditor(variant)` hook: keeps a `baseline` snapshot alongside mutable `state`, derives `dirty` with a deep equality helper (`statesEqual`) covering metadata + all 4 delta sections incl. the `instructions_delta` array (compared row-by-row with JSON.stringify for `default`).
- Save flow: awaits `updateVariantMut.mutateAsync`; on `ApiError` with `status === 422`, parses the `detail` for a single-quoted field name and maps it to the row index to set an inline error, plus a banner. Other errors surface via toast (apiClient already does this) + banner.
- Run-with-variant: `useTriggerEvalRun({ variant_id })`; if dirty, prompts user to confirm since the run uses the saved variant; on success navigates to `/evals/{datasetId}` (dataset detail page). User manually clicks "Run History" tab there — the existing tab component does not accept search-param-driven `defaultValue`, and Step 6 scope is forbidden from touching Step 7 infrastructure.
- Delta row editor: op dropdown (`add | modify`), field name input (lowercased on change), type dropdown (10 whitelisted values matching backend), default value input parsed as JSON with raw-string fallback (backend validates).
- Info banner at top of instructions-delta section documents the `LLMResultMixin` inherited-field limitation.

### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.new.tsx` (new)
Mounts, POSTs a blank variant via `useCreateVariant`, and navigates (`replace: true`) to the editor. Uses `useRef` guard to prevent StrictMode double-fire. Default name uses an ISO timestamp (`Variant 2026-04-17 16:45`). On error: shows inline error card with Back + Retry buttons.

## Decisions

### New variant as separate route, not sentinel in `$variantId.tsx`
**Choice:** Dedicated `evals.$datasetId.variants.new.tsx` that creates + redirects, rather than handling `$variantId === "new"` inside the editor.
**Rationale:** Keeps the editor strictly about loading/editing an existing variant; avoids `useVariant` from firing with `NaN` variantId or needing a "creating" state inside the editor. TanStack file-based routing picks up the `new` literal path segment as a concrete match before the `$variantId` param, so routing precedence handles the dispatch automatically.

### Prod pane scope limited to instructions output_schema
**Choice:** Left pane shows step target + instructions class field list (from `/api/evals/schema?target_type=step&target_name=X`). It does NOT show production system/user prompt content or model.
**Rationale:** There is no backend endpoint that maps a dataset's `target_name` to its owning pipeline. `GET /api/pipelines/{name}/steps/{step}/prompts` would require the pipeline name, which the dataset does not store. Surfacing the instructions field list is enough to make the delta meaningful (users can see what they're modifying). The right pane documents that blanks inherit prod, so no silent behavior.

### Dirty tracking pattern (hook-local baseline + state comparison)
**Choice:** `useVariantEditor` keeps both `baseline` (server snapshot) and `state` (live); `dirty = !statesEqual(state, baseline)`. Mirror of the `useCaseEditor` pattern in the same codebase — both use component-local `useState` + derived flags rather than a global store.
**Rationale:** Editor is a single self-contained page, no cross-component state sharing needed. Zustand/Redux would be overkill for a per-variant editor. TanStack Query (`useVariant`) remains the source of server truth; local state only overlays unsaved edits.

### 422 error mapping
**Choice:** On `ApiError.status === 422`, show the backend message in a top banner AND attempt to match the message against known row fields (exact-match of `'fieldname'` in detail string). If match, set per-row inline error; otherwise banner-only.
**Rationale:** Backend `_dry_run_validate_delta` raises `ValueError` with messages like `field name '__class__' is invalid` or `type_str 'foo' is not allowed`. The quoted-field heuristic catches the field-name / field-default case; type/op errors remain banner-only which is still visible and actionable. Never swallows the message.

### `instructions_delta` cap enforcement
**Choice:** UI warns at 45 entries, disables "Add field" button at 50. Matches backend hard cap.
**Rationale:** Prevents the user from authoring a delta that will be rejected at save time. Still not the primary defense — backend remains authoritative.

## Verification
- [x] TypeScript compiles (`npx tsc --noEmit` exits 0).
- [x] ESLint clean on all 3 touched/new files (0 errors, 0 warnings).
- [x] Variants tab renders alongside Cases + Run History.
- [x] `VariantsTab` "New Variant" button navigates to `/evals/{datasetId}/variants/new`.
- [x] New-variant route creates blank variant + redirects to editor.
- [x] Editor fetches variant via `useVariant`; dataset via `useDataset`; step schema via `useInputSchema`.
- [x] Delta form populates all 4 sections (model, system_prompt, user_prompt, instructions_delta rows).
- [x] Save button disabled when not dirty; enabled + calls `useUpdateVariant` when dirty.
- [x] Discard button resets state to baseline snapshot.
- [x] Run-with-Variant button calls `useTriggerEvalRun({ variant_id })` and navigates back to dataset.
- [x] 422 responses from backend surfaced as inline + banner error, never swallowed.
- [x] Inherited-field info banner displayed in instructions-delta section.
- [x] Type/op dropdowns match backend whitelist exactly.
- [x] Instructions-delta array capped at 50 entries UI-side with counter + disabled add button.
- [x] Step 7 files (`evals.$datasetId.compare.tsx`, `evals.$datasetId.runs.$runId.tsx`) untouched.

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
- [x] MEDIUM: `variable_definitions` UI missing — backend runner consumes it but editor had no affordance. Extended the UI to author variable_definitions overrides.
- [x] LOW: NewVariantPage retry forced full navigate() round-trip — replaced with local `retryKey` state included in the effect dep list.
- [x] LOW: `parseBackendFieldError` used substring matching — replaced with longest-field-match so `'foo'` in the field list does not shadow a real `'foobar'` error.

### Changes Made

#### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.$variantId.tsx`
- Added `useDeltaTypeWhitelist` + `VariableDefinitions` imports from `@/api/evals`.
- Renamed the local `TYPE_WHITELIST` constant to `FALLBACK_TYPE_WHITELIST`; only used when the backend fetch is loading or errored (error logged via `console.error`).
- Added `MAX_VAR_DEF_ENTRIES = 20` cap constant.
- Extended `EditorState` with `variableDefinitions: VariableDefinitionRow[]` (new row shape `{name, type, auto_generate}`).
- Added `varDefsToRows()` / `rowsToVarDefs()` serialisation helpers (tolerates both map and list-of-dicts shapes on read; writes back the TS canonical map form keyed by name; drops empty rows and omits blank `auto_generate` to avoid overwriting prod defs with empty strings).
- Extended `statesEqual` to diff the var-defs row list.
- Added `addVarDefRow` / `updateVarDefRow` / `removeVarDefRow` to the `useVariantEditor` hook.
- `DeltaRowEditor` now takes `typeOptions` + `typesDisabled` props; the `type_str` select reads from props instead of the module-level constant.
- `VariantDeltaPanel` takes the new handlers + `typeOptions` / `typesLoading` props; renders a new "Variable definitions" section under the instructions-delta section with a dynamic row list (name / type / auto_generate inputs + remove button), add button, counter, info banner explaining "Variant wins on name collision" and that `auto_generate` is backend-resolved.
- `VariantEditorPage` calls `useDeltaTypeWhitelist()`, falls back to `FALLBACK_TYPE_WHITELIST` on error or empty result, logs errors to console, and passes `typeOptions` / `typesLoading` through.
- `parseBackendFieldError` rewritten to find the LONGEST quoted-field match instead of the first, so `foo` vs `foobar` no longer mis-attributes (both would match `'foobar'` with naive substring; longest-match wins).

#### File: `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.new.tsx`
- Added `retryKey` local state (`useState(0)`).
- Effect dep list is now `[datasetId, retryKey]` so bumping the key re-runs the create attempt without a URL round-trip.
- Retry button replaces the prior `navigate(..., replace: true)` call with `setRetryKey(k => k + 1)` (plus the existing `attemptedRef.current = false` reset).

### Verification
- [x] `npx tsc --noEmit` clean in `llm_pipeline/ui/frontend` (no TS errors).
- [x] `uv run pytest tests/ -q -k "variant or delta"` — 123/123 passed.
- [x] No changes to Step 5 API files (`api/evals.ts`, `api/query-keys.ts`) or Step 7 files (`evals.$datasetId.compare.tsx`, `evals.$datasetId.runs.$runId.tsx`).
- [x] Imports the existing Step 5 exports (`useDeltaTypeWhitelist`, `VariableDefinitions`) — no new API layer code added.
- [x] Variable definitions editor writes to `delta.variable_definitions` on Save; backend runner already consumes this field (runner.py `_apply_variant_to_sandbox`, confirmed against `merge_variable_definitions`).
- [x] `auto_generate` resolver logic NOT duplicated client-side — UI only captures expression strings; registry resolution remains a backend concern.
