# Task Summary

## Work Completed

Delta-based variant system for evals v2. Variants let users override a subset of a step definition (model, system/user prompt, instruction schema fields, prompt variable definitions) without touching production configuration. Each variant is scoped to a dataset; runs reference it via a nullable FK; the runner applies the delta in a sandboxed engine before evaluator resolution. All delta entry points are ACE-hardened. Full frontend shipped: Variants tab, split-pane editor, Run with Variant flow, and side-by-side run comparison view.

### What shipped

- **EvaluationVariant table** (`eval_variants`): dataset-scoped, stores `delta` JSON (keys: `model`, `system_prompt`, `user_prompt`, `instructions_delta`, `variable_definitions`). Nullable `variant_id` FK and `delta_snapshot` JSON column added to `EvaluationRun` via existing `_migrate_add_columns` pattern -- zero-downtime on existing DBs.
- **`apply_instruction_delta(base_cls, delta) -> type`** (`evals/delta.py`): pure function, no I/O, no globals. Builds a pydantic subclass via `create_model(__base__=LLMResultMixin)`, preserving `create_failure()`. Hard-coded type whitelist, identifier regex, dunder rejection, JSON round-trip default validation, length caps. Docker-relocatable with zero refactor.
- **Runner integration**: `run_dataset`/`run_dataset_by_name` accept optional `variant_id`. Delta applied via `dataclasses.replace` (prod step def never mutated) BEFORE `_resolve_evaluators` (CEO-required ordering so auto-evaluators reflect variant schema). Sandbox receives model/prompt/variable_definitions overrides through `_apply_variant_to_sandbox`. `delta_snapshot` (deep-copied JSON, no class refs) persisted on the run row.
- **Variant CRUD API** (`GET`/`POST`/`PUT`/`DELETE` under `/evals/{dataset_id}/variants`): dry-run ACE validation on every create/update (HTTP 422 on invalid delta). `GET /evals/delta-type-whitelist` single-source-of-truth endpoint. Dataset delete cascades variants. Variant delete nulls `EvaluationRun.variant_id` FK references atomically; `delta_snapshot` preserved for reproducibility.
- **Frontend API layer**: TS interfaces (`VariantItem`, `VariantDelta`, `DeltaTypeStr` literal union, `VariableDefinitions` map type), TanStack Query hooks (`useVariants`, `useVariant`, `useCreateVariant`, `useUpdateVariant`, `useDeleteVariant`, `useDeltaTypeWhitelist`). `RunListItem` and `TriggerRunRequest` extended.
- **Variants tab** on dataset detail page: third tab alongside Cases and Run History; variant list table with delete confirmation.
- **Variant editor route** (`evals.$datasetId.variants.$variantId.tsx`): split-pane (prod read-only left / delta right), model/system prompt/user prompt/instructions delta/variable definitions sections, dirty tracking, Save/Discard/Run with Variant buttons. 422 ACE errors parsed into row-level inline messages via longest-match field attribution.
- **New variant route** (`evals.$datasetId.variants.new.tsx`): StrictMode-safe via `attemptedRef` + `retryKey` state.
- **Compare view** (`evals.$datasetId.compare.tsx`): Zod-validated search params, parallel run fetch, delta snapshot viewer, side-by-side stat cards, per-case union table with improved/regressed/unchanged indicators. Compare button in Run History on multi-select; Compare with baseline link on variant run detail.

---

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `llm_pipeline/evals/delta.py` | `apply_instruction_delta`, `merge_variable_definitions`, `get_type_whitelist` -- pure ACE-hardened delta toolkit |
| `tests/test_eval_variants.py` | Steps 1-3 tests: DB schema (9), delta utility (57), merge helpers (5), sandbox override (6), runner integration (9) -- 86 total |
| `tests/ui/test_evals_routes.py` | Step 4 tests: variant CRUD, cascade delete, trigger with variant_id, FK nullification, whitelist endpoint -- 32 total |
| `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.$variantId.tsx` | Variant editor route (split-pane) |
| `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.new.tsx` | New variant creation route |
| `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx` | Side-by-side run comparison view |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/evals/models.py` | Added `EvaluationVariant` table; extended `EvaluationRun` with `variant_id` + `delta_snapshot`; updated `__all__` |
| `llm_pipeline/evals/__init__.py` | Re-exported `apply_instruction_delta`, `merge_variable_definitions`, `get_type_whitelist` |
| `llm_pipeline/evals/runner.py` | `run_dataset`/`run_dataset_by_name` accept `variant_id`; delta applied before evaluator resolution; `_apply_variant_to_sandbox` + `_merge_variant_defs_into_prompt` helpers; snapshot persistence |
| `llm_pipeline/db/__init__.py` | Imported `EvaluationVariant`; registered table in `init_pipeline_db()`; added `variant_id`/`delta_snapshot` migration rows |
| `llm_pipeline/ui/routes/evals.py` | Variant CRUD endpoints + request/response models; dry-run validation; `GET /evals/delta-type-whitelist`; extended `TriggerRunRequest`, `RunListItem`, `RunDetail`; cascade deletes; FK nullification on variant delete |
| `llm_pipeline/ui/frontend/src/api/evals.ts` | `VariantItem`, `VariantDelta`, `DeltaTypeStr` literal union, `VariableDefinitions` types; variant fetch fns + TQ hooks; `useDeltaTypeWhitelist`; extended `RunListItem` + `TriggerRunRequest` |
| `llm_pipeline/ui/frontend/src/api/query-keys.ts` | `variants`, `variant`, `deltaTypeWhitelist` key factories added to `evals` factory |
| `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.index.tsx` | Third Variants tab; `VariantsTab` component with list, create button, delete |
| `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx` | Compare with baseline link gated on `variant_id != null`; most-recent-baseline selection |

---

## Commits Made

| Hash | Message |
| --- | --- |
| `f00e56a3` | docs(implementation-A): adhoc-20260416-evals-v2-variants (Step 1: model + migration) |
| `8bb85a25` | docs(implementation-A): adhoc-20260416-evals-v2-variants (Step 2: delta utility) |
| `519a92d2` | docs(implementation-B): adhoc-20260416-evals-v2-variants (Step 3: runner integration) |
| `3435d20d` | docs(implementation-B): adhoc-20260416-evals-v2-variants (Step 4: CRUD API routes) |
| `42bd31f2` | docs(implementation-C): adhoc-20260416-evals-v2-variants (Step 5: frontend API layer) |
| `bf925d58` | docs(implementation-D): adhoc-20260416-evals-v2-variants (Step 6: variants tab + editor) |
| `8e14f525` | docs(implementation-D): adhoc-20260416-evals-v2-variants (Step 7: comparison view) |
| `24013252` | fix(evals): reject non-list instructions_delta before empty-check |
| `068c8c8a` | docs(fixing-review-B): adhoc-20260416-evals-v2-variants (DRY: _merge_variant_defs_into_prompt) |
| `b7bd3b0e` | docs(fixing-review-B): adhoc-20260416-evals-v2-variants (get_type_whitelist, FK nullification, whitelist endpoint) |
| `be02f8bd` | docs(fixing-review-C): adhoc-20260416-evals-v2-variants (DeltaTypeStr union, VariableDefinitions type, useDeltaTypeWhitelist) |
| `8e7b1dda` | docs(fixing-review-D): adhoc-20260416-evals-v2-variants (whitelist hook, varDef editor, longest-match error parse, state-key retry) |

---

## Deviations from Plan

- **`variable_definitions` in delta**: PLAN listed delta shape as `{model, system_prompt, user_prompt, instructions_delta}`. Review found runner already consumed `variable_definitions` but it was absent from TS types and plan contract. CEO chose UI extension over removing the runner branch. Adds a fifth delta key to the documented contract.
- **`delete_variant` FK nullification**: PLAN Risks table stated application-level cascade delete in `delete_variant` endpoint but initial implementation omitted it. Fixed in review -- variant delete now nulls `EvaluationRun.variant_id` in the same transaction; `delta_snapshot` preserved.
- **Single-source-of-truth whitelist endpoint**: Not in original PLAN. Added `GET /evals/delta-type-whitelist` during review to resolve backend/frontend whitelist drift (MEDIUM finding).

---

## Issues Encountered

### MEDIUM 1 -- variable_definitions frontend/backend drift
Runner consumed `variable_definitions` from delta but TS `VariantDelta` type and PLAN delta shape did not declare it.
**Resolution:** CEO chose UI extension. Added `VariableDefinitions` map type, extended `VariantDelta`, added editor section. Runner branch retained.

### MEDIUM 2 -- delete_variant orphaned FK references
Deleting a variant left `EvaluationRun.variant_id` pointing at a deleted row (SQLite FK enforcement off by default).
**Resolution:** `delete_variant` now queries and nulls all referencing run FKs atomically before deleting the variant row. `delta_snapshot` preserved.

### MEDIUM 3 -- Empty dict bypassed non-list type check
`apply_instruction_delta` checked `len == 0` before `isinstance(list)`. Empty dict has `len == 0`, returned as no-op without type validation.
**Resolution:** Reordered: isinstance check runs first. Empty dict raises `ValueError`. Two new tests added.

### MEDIUM 4 -- type_str whitelist drift (two sources of truth)
Backend `_TYPE_WHITELIST` dict and frontend `TYPE_WHITELIST` constant were independent, could drift silently.
**Resolution:** Added `get_type_whitelist()` pure accessor; `GET /evals/delta-type-whitelist` endpoint; `useDeltaTypeWhitelist` hook (`staleTime: Infinity`). Editor consumes backend whitelist at runtime with offline fallback.

### MEDIUM 5 -- Validation duplicated between route and runner
`trigger_eval_run` validates variant ownership at 422 synchronously; runner re-validates in background.
**Resolution:** Accepted as intentional defensive depth (TOCTOU window on variant deletion). Comment added.

### LOW items resolved
`_coerce_var_defs`/`_encode_var_defs` duplication (extracted to `_merge_variant_defs_into_prompt`); `type_str: string` not a literal union (tightened to `DeltaTypeStr`); `NewVariantPage` retry via navigate (replaced with `retryKey` state); substring field error matching (replaced with longest-match).

### Review pass 2: 3 LOW (doc-grade), no code changes
`variable_definitions` editor drops unknown spec keys on save (acknowledged trade-off, documented inline); frontend fallback whitelist and `DeltaTypeStr` union remain manual sync points alongside runtime endpoint (codegen deferred); `varDefsToRows`/`rowsToVarDefs` row reorder risk noted for future serializer changes.

---

## Success Criteria

- [x] `EvaluationVariant` table created by `init_pipeline_db()` with correct schema -- verified by `TestFreshDbCreation` (7 tests)
- [x] `eval_runs.variant_id` + `eval_runs.delta_snapshot` added via `_migrate_add_columns` on existing DB -- verified by `TestMigrationOnExistingDb` (2 tests, idempotency included)
- [x] `apply_instruction_delta()` for add, modify, empty delta, inherited-field remove rejection, all adversarial payloads -- verified by `TestApplyInstructionDelta` (57 tests)
- [x] `EvalRunner.run_dataset(dataset_id, variant_id=X)` produces run with `variant_id` and `delta_snapshot` populated -- verified by `TestRunnerVariantIntegration`
- [x] Evaluator resolution uses delta-modified instructions class -- verified by `test_evaluator_resolution_uses_modified_instructions_class`
- [x] Sandbox receives correct model, prompt content, and `variable_definitions` overrides -- verified by `TestApplyVariantToSandbox`
- [x] Variant CRUD correct HTTP status codes and payloads -- verified by `TestCreateVariant`, `TestListVariants`, `TestGetVariant`, `TestUpdateVariant`, `TestDeleteVariant`
- [x] Cascade delete removes variants on dataset deletion -- verified by `TestDeleteDatasetCascade`
- [x] `POST /evals/{dataset_id}/runs` with `variant_id` triggers variant run -- verified by `TestTriggerRunWithVariant`
- [x] Malicious delta payloads rejected at API layer with 422 -- verified by 5 parametrized cases in `TestCreateVariant` + `TestUpdateVariant`
- [x] `delete_variant` nulls FK atomically, preserves `delta_snapshot` -- verified by `test_delete_variant_nulls_run_fk_preserves_snapshot`
- [x] `GET /evals/delta-type-whitelist` returns sorted canonical list -- verified by `TestDeltaTypeWhitelist`
- [x] All existing tests continue to pass -- 1444 pass / 15 fail / 6 skip; all 15 failures pre-existing (confirmed on stash)
- [x] TypeScript compiles clean -- `npx tsc --noEmit` exits 0
- [ ] Variants tab renders on dataset detail page -- requires manual UI verification
- [ ] Variant editor split-pane, Save, delta persistence -- requires manual UI verification
- [ ] Run with Variant triggers run, navigates to Run History -- requires manual UI verification
- [ ] Comparison view side-by-side stats + per-case delta -- requires manual UI verification

---

## Manual Verification Checklist

Before promoting to prod, verify these 7 flows (`uv run llm-pipeline ui --dev`):

1. **Create variant**: dataset detail > Variants tab > New Variant > fill name + instructions delta row > Save. Variant appears in list.
2. **Edit + save**: open existing variant > modify system prompt override > Save. Change persists on reload; dirty indicator clears.
3. **Run with variant**: in variant editor > Run with Variant. New run appears in Run History with `variant_id` shown; run detail shows `delta_snapshot`.
4. **Compare view**: Run History > select baseline + variant run (checkboxes) > Compare. `/evals/{id}/compare` renders stat cards + per-case table.
5. **Dataset cascade delete**: delete dataset with variants. Dataset, runs, cases, and variants all removed; other datasets unaffected.
6. **Variant delete preserves run data**: delete variant with associated completed runs. Runs remain with `variant_id = null`, `delta_snapshot` still visible.
7. **Malicious payload 422**: submit delta with `field="__class__"` via editor or API. HTTP 422 returned; nothing persisted.

---

## Recommendations for Follow-up

1. **Runner three-session pattern**: `run_dataset` uses three separate `Session` blocks with non-atomic boundaries. Process death between write sessions leaves runs stuck as running. Consolidate into single try-with-session or add startup stuck-running sweeper.
2. **Pipeline-level variants**: v2 scope is dataset-scoped only. Variants at the pipeline/strategy level (`create_sandbox_from_factory`) deferred to post-v2.
3. **prompt_key auto-discovery**: when `system_instruction_key`/`user_prompt_key` is `None`, prompt overrides are silently skipped. Auto-discovery would unlock prompt overrides for all pipelines, not just those with named keys.
4. **variable_definitions shape canonicalization**: runner accepts both list-of-dicts and `{name: spec}` dict shapes from existing pipelines. Canonicalize to one shape and migrate existing prompt rows.
5. **Whitelist codegen**: `DeltaTypeStr` literal union in `evals.ts` and `FALLBACK_TYPE_WHITELIST` in the editor are convention-synced with backend `_TYPE_WHITELIST`. A codegen step would eliminate manual sync.
6. **Frontend test coverage**: no vitest unit tests for variant hooks or editor components. Add component tests for `VariantsTab`, editor dirty-tracking, and compare view case union.
7. **Pre-existing test failures**: 15 failures across `test_sandbox.py` (x6), `test_evaluators.py` (x7), `test_cli.py` (x1), `test_runs.py` (x1) are unrelated to this branch. Address in a separate task.