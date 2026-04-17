# PLANNING

## Summary

Add variant comparison to the evals system: a new `EvaluationVariant` table holds delta-based overrides (`{model, system_prompt, user_prompt, instructions_delta}`) scoped to a dataset. Runs optionally reference a variant via nullable FK; the runner applies the delta to the step definition before sandbox execution and evaluator resolution, then persists a `delta_snapshot` JSON column for reproducibility. Frontend gains a Variants tab on the dataset detail page, a variant editor with split-pane prod/variant view, a trigger-run-with-variant flow, and a comparison view between runs.

## Plugin & Agents

**Plugin:** python-development, backend-development, frontend-mobile-development
**Subagents:** python-development:subagent, backend-development:subagent, frontend-mobile-development:subagent
**Skills:** python-development:python-testing-patterns, backend-development:api-design-principles, frontend-mobile-development:react-state-management

## Phases

1. **DB models + migration**: Add `EvaluationVariant` table and new columns (`variant_id`, `delta_snapshot`) on `EvaluationRun` via the existing `_migrate_add_columns` pattern.
2. **Backend delta logic + runner integration**: Implement `apply_instruction_delta()` utility, integrate into `EvalRunner._resolve_step_task()`, reorder evaluator resolution after delta application, seed sandbox prompt overrides including `variable_definitions`.
3. **Backend API routes**: Variant CRUD endpoints + extend run trigger endpoint to accept optional `variant_id`.
4. **Frontend API layer**: Add TS types + TanStack Query hooks for variants, extend run hooks to surface `variant_id` + `delta_snapshot`.
5. **Frontend UI**: Variants tab on dataset detail, variant editor (split-pane), trigger run with variant, comparison view route.

## Architecture Decisions

### EvaluationVariant table location
**Choice:** New SQLModel class in `llm_pipeline/evals/models.py`; registered in `init_pipeline_db()` tables list.
**Rationale:** All eval models already live there; `init_pipeline_db()` drives table creation for the whole framework. Adding here keeps the pattern consistent and avoids a separate module for a tightly coupled entity.
**Alternatives:** Separate `llm_pipeline/evals/variant_models.py` — rejected, unnecessary fragmentation.

### Migration strategy for new columns
**Choice:** Add `variant_id` (INTEGER nullable FK) and `delta_snapshot` (TEXT/JSON nullable) to `eval_runs` via `_migrate_add_columns` in the same migration batch.
**Rationale:** Existing `_migrate_add_columns` handles both SQLite (`PRAGMA`+`ALTER TABLE ADD COLUMN`) and Postgres (`information_schema`+`ADD COLUMN IF NOT EXISTS`). No separate Alembic migrations exist in this project.
**Alternatives:** Alembic — not used in this project, would require introducing new tooling.

### `apply_instruction_delta()` placement
**Choice:** New module `llm_pipeline/evals/delta.py` with a pure function `apply_instruction_delta(base_cls, delta) -> type`.
**Rationale:** Isolated from runner and models; independently unit-testable as the research recommends. Uses `create_model(__base__=LLMResultMixin)` per CEO decision, preserving `create_failure()`.
**Alternatives:** Inline in runner — harder to test; in `pipeline.py` — wrong layer.

### Evaluator resolution ordering
**Choice:** In `_resolve_step_task`, call `apply_instruction_delta` first, then pass the resulting class to `_resolve_evaluators`.
**Rationale:** CEO decision. Variant-added/modified fields must be visible to auto-evaluator generation so evaluators match the variant schema.
**Alternatives:** Resolve evaluators from prod step def — rejected by CEO.

### Sandbox prompt override for variants
**Choice:** After `create_sandbox_engine`, UPDATE the sandbox `Prompt` rows whose `prompt_key` matches `step_def.system_instruction_key` / `user_prompt_key` with variant content; also update `variable_definitions` via `merge_variable_definitions(prod_vars, variant_vars)`.
**Rationale:** Existing `create_sandbox_engine` already seeds prompts from prod. Updating sandbox rows post-seed leaves prod untouched and reuses the full execution path.
**Alternatives:** Pass override dict into pipeline execute — requires pipeline API changes.

### delta_snapshot storage
**Choice:** Dedicated `delta_snapshot` JSON column on `EvaluationRun` (NULL for baseline runs).
**Rationale:** CEO decision. Cleaner querying than nested JSON; makes reproducibility auditing straightforward.
**Alternatives:** Nested in `report_data` — rejected by CEO.

### Frontend variant comparison route
**Choice:** `evals.$datasetId.compare.tsx` as a new TanStack Router file-based route; accepts `?baseRunId=X&variantRunId=Y` as search params.
**Rationale:** Follows existing file-based routing pattern (`evals.$datasetId.runs.$runId.tsx`). Search params allow deep-linking to specific comparisons without an extra DB entity.
**Alternatives:** Modal overlay — no deep-link support.

## Implementation Steps

### Step 1: EvaluationVariant model + DB migration
**Agent:** python-development:subagent
**Skills:** python-development:python-testing-patterns
**Context7 Docs:** /fastapi/sqlmodel
**Group:** A

1. Add `EvaluationVariant(SQLModel, table=True)` to `llm_pipeline/evals/models.py` with fields: `id`, `dataset_id` (FK `eval_datasets.id`, index), `name` (str, max 200), `description` (Optional[str]), `delta` (JSON column — dict with keys `model`, `system_prompt`, `user_prompt`, `instructions_delta`), `created_at`, `updated_at`; add index on `dataset_id`.
2. Add nullable `variant_id` (Optional[int], FK `eval_variants.id`) and `delta_snapshot` (Optional[dict], JSON column) fields to `EvaluationRun`.
3. Register `EvaluationVariant.__table__` in `init_pipeline_db()` tables list in `llm_pipeline/db/__init__.py` (after `EvaluationCaseResult.__table__`); import `EvaluationVariant` at top of file.
4. Add `("eval_runs", "variant_id", "INTEGER")` and `("eval_runs", "delta_snapshot", "TEXT")` to `_MIGRATIONS` list in `_migrate_add_columns()`.
5. Update `__all__` in `llm_pipeline/evals/models.py` to include `EvaluationVariant`.
6. Add unit test in `tests/test_eval_runner.py` (or new `tests/test_eval_variants.py`) verifying that `init_pipeline_db()` creates the `eval_variants` table and that `eval_runs` gains `variant_id` + `delta_snapshot` columns on an existing DB.

### Step 2: `apply_instruction_delta()` utility
**Agent:** python-development:subagent
**Skills:** python-development:python-testing-patterns
**Context7 Docs:** /websites/pydantic_dev_validation
**Group:** A

1. Create `llm_pipeline/evals/delta.py` with `apply_instruction_delta(base_cls: type, instructions_delta: list[dict]) -> type` using `pydantic.create_model(__base__=base_cls)`. Each delta item has `op` (`add`|`modify`), `field`, `type_str` (whitelisted Python type strings), and optionally `default`. `remove` is not supported for inherited fields — document this.
2. Implement `_resolve_type(type_str: str) -> type` with a whitelist covering: `str`, `int`, `float`, `bool`, `list`, `dict`, `Optional[str]`, `Optional[int]`, `Optional[float]`, `Optional[bool]`.
3. Export `apply_instruction_delta` from `llm_pipeline/evals/__init__.py`.
4. Write thorough unit tests in `tests/test_eval_variants.py`: add field, modify field, unknown op is ignored, unknown type_str raises ValueError, empty delta returns base class unchanged, result preserves `create_failure()` method.

### Step 3: Runner integration — delta application + prompt override
**Agent:** python-development:subagent
**Skills:** python-development:python-testing-patterns
**Context7 Docs:** /fastapi/sqlmodel
**Group:** B

1. In `llm_pipeline/evals/runner.py`, modify `run_dataset` signature to accept `variant_id: int | None = None`; load `EvaluationVariant` from DB when provided; pass variant delta to `_resolve_step_task` and `_build_step_task_fn`.
2. In `_resolve_step_task`, after `_find_step_def`, if delta has `instructions_delta`: call `apply_instruction_delta(step_def.instructions, delta["instructions_delta"])` to produce a modified instructions class; then call `_resolve_evaluators` with that modified class (not `step_def.instructions`).
3. In `_build_step_task_fn`, accept optional `variant_delta: dict | None`; when present: after `create_sandbox_engine`, update sandbox `Prompt` rows for `system_instruction_key`/`user_prompt_key` with variant's `system_prompt`/`user_prompt` content; merge `variable_definitions` via a new `merge_variable_definitions(prod_vars, variant_vars)` helper; upsert a `StepModelConfig` row in sandbox for variant's `model` override.
4. Implement `merge_variable_definitions(prod_defs: list | None, variant_defs: list | None) -> list` — union by variable name, variant wins on conflict.
5. Store delta snapshot: set `run.delta_snapshot = variant.delta` (copy of the delta dict) when creating the `EvaluationRun` row; set `run.variant_id = variant_id`.
6. Extend `run_dataset_by_name` to accept `variant_id: int | None = None` and pass through.
7. Add integration test in `tests/test_eval_runner.py`: mock a step def with `instructions` class, create an `EvaluationVariant` with all 4 delta types, run with `variant_id`, assert `delta_snapshot` is populated on the resulting run row.

### Step 4: Variant CRUD API routes
**Agent:** backend-development:subagent
**Skills:** backend-development:api-design-principles
**Context7 Docs:** /fastapi/sqlmodel
**Group:** B

1. Add Pydantic request/response models to `llm_pipeline/ui/routes/evals.py`: `VariantItem`, `VariantCreateRequest`, `VariantUpdateRequest`, `VariantListResponse`. `VariantItem` includes: `id`, `dataset_id`, `name`, `description`, `delta`, `created_at`, `updated_at`.
2. Add endpoint `GET /evals/{dataset_id}/variants` -> `VariantListResponse` listing variants for a dataset ordered by `created_at`.
3. Add `POST /evals/{dataset_id}/variants` (201) -> `VariantItem`.
4. Add `GET /evals/{dataset_id}/variants/{variant_id}` -> `VariantItem`.
5. Add `PUT /evals/{dataset_id}/variants/{variant_id}` -> `VariantItem`.
6. Add `DELETE /evals/{dataset_id}/variants/{variant_id}` (204).
7. Extend `POST /evals/{dataset_id}/runs` (`TriggerRunRequest`) to accept optional `variant_id: Optional[int] = None`; pass to `runner.run_dataset()`.
8. Extend `RunListItem` to include `variant_id: Optional[int]` and `delta_snapshot: Optional[dict]`; update `list_eval_runs` and `get_eval_run` to populate these from the DB row.
9. Cascade-delete variants when deleting a dataset (add to `delete_dataset` after runs deletion).
10. Add tests in `tests/ui/` verifying variant CRUD endpoints return correct status codes and payloads.

### Step 5: Frontend API layer — variants + extended run types
**Agent:** frontend-mobile-development:subagent
**Skills:** frontend-mobile-development:react-state-management
**Context7 Docs:** /tanstack/router
**Group:** C

1. In `llm_pipeline/ui/frontend/src/api/evals.ts`, add TS interfaces: `VariantItem`, `VariantCreateRequest`, `VariantUpdateRequest`, `VariantListResponse`. Extend `RunListItem` with `variant_id: number | null` and `delta_snapshot: Record<string, unknown> | null`.
2. Add fetch functions: `fetchVariants(datasetId)`, `fetchVariant(datasetId, variantId)`, `createVariant(datasetId, body)`, `updateVariant(datasetId, variantId, body)`, `deleteVariant(datasetId, variantId)`.
3. Add TanStack Query hooks: `useVariants(datasetId)`, `useVariant(datasetId, variantId)`, `useCreateVariant(datasetId)`, `useUpdateVariant(datasetId)`, `useDeleteVariant(datasetId)`.
4. Extend `useTriggerEvalRun` to accept `{ model?: string; variant_id?: number }` body.
5. In `llm_pipeline/ui/frontend/src/api/query-keys.ts`, add to `evals` key factory: `variants: (datasetId: number) => ['evals', datasetId, 'variants'] as const` and `variant: (datasetId: number, variantId: number) => ['evals', datasetId, 'variants', variantId] as const`.

### Step 6: Frontend — Variants tab + variant editor route
**Agent:** frontend-mobile-development:subagent
**Skills:** frontend-mobile-development:react-state-management
**Context7 Docs:** /tanstack/router
**Group:** D

1. In `evals.$datasetId.index.tsx`, add a third `TabsTrigger`/`TabsContent` for "Variants" alongside Cases and Run History.
2. Implement `VariantsTab` component within the file (or extracted to `src/components/evals/VariantsTab.tsx`): table listing variants by name with created date; "New Variant" button navigating to variant editor route; delete button per row with confirmation.
3. Create new route file `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.variants.$variantId.tsx` with `VariantEditorPage` component:
   - Split-pane layout: left pane shows prod step definition read-only (model, system prompt, user prompt, instructions fields); right pane is editable with the 4 delta sections.
   - Model section: optional model override string input.
   - System prompt / user prompt sections: optional textarea overrides (Monaco if available, else `Textarea`).
   - Instructions delta section: dynamic field list — each row has field name, type dropdown (whitelisted types), default value, op (add/modify); add/remove rows.
   - Save, Discard, and "Run with Variant" buttons; dirty-tracking state (similar to `useCaseEditor` pattern).
   - "Run with Variant" button calls `useTriggerEvalRun` with `{ variant_id }`, shows toast on submit, navigates to Run History tab on success.
4. Create `evals.$datasetId.variants.new.tsx` (or handle via `$variantId=new` guard) that creates a variant then redirects to the editor.
5. Add a "Variants" link/button in the dataset detail header or tab bar linking to variant list.

### Step 7: Frontend — Run comparison view
**Agent:** frontend-mobile-development:subagent
**Skills:** frontend-mobile-development:react-state-management
**Context7 Docs:** /tanstack/router
**Group:** D

1. Create route `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx` with search params `{ baseRunId: number; variantRunId: number }` validated via TanStack Router `validateSearch`.
2. `CompareRunsPage` fetches both runs in parallel via `useEvalRun`; shows loading/error states.
3. Delta summary section: renders `delta_snapshot` from the variant run using `JsonViewer` component (existing, reuse diff mode if available).
4. Stats comparison: side-by-side stat cards (passed/failed/errored, pass rate) for baseline vs variant run.
5. Per-case comparison table: rows are cases (union of both runs' case names); columns: case name, baseline pass/fail + scores, variant pass/fail + scores, delta indicator (improved/regressed/unchanged).
6. In `RunHistoryTab` in `evals.$datasetId.index.tsx`: when 2 or more runs are selected (checkbox column), show a "Compare" button that navigates to `/evals/${datasetId}/compare?baseRunId=X&variantRunId=Y`.
7. Add "Compare with baseline" link in `evals.$datasetId.runs.$runId.tsx` for variant runs (where `variant_id != null`), linking to compare view with the most recent baseline run.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `prompt_key` auto-discovery fails when `system_instruction_key`/`user_prompt_key` are None on step def | High | In `_build_step_task_fn` variant path, skip prompt override silently and log a warning; document in variant editor that prompt overrides require named prompt keys |
| `create_model(__base__=LLMResultMixin)` breaks pydantic-ai Agent output validation for complex nested types | High | Unit test with actual pydantic-ai Agent before runner integration; restrict `type_str` whitelist to scalar + simple types; nested model types are passthrough (not modified) |
| SQLite FK enforcement off by default (no `PRAGMA foreign_keys=ON`) — orphan `variant_id` refs | Low | Nullable FK + application-level cascade delete in `delete_dataset` and `delete_variant` endpoints; FK enforcement not relied upon |
| Instructions delta `remove` op attempted on inherited fields (confidence_score, notes) | Medium | Validate in `apply_instruction_delta`: raise `ValueError` with clear message if `op=remove` targets an inherited field; surface in variant editor UI as disabled field |
| Run comparison with mismatched case names (variant run has subset of cases) | Low | Comparison table uses union of case names; missing entries rendered as "N/A" |
| Concurrent eval runs with same sandbox engine sharing in-memory state | Low | `create_sandbox_engine` creates a fresh engine per `task_fn` invocation (existing pattern); no shared state |
| `merge_variable_definitions` produces conflicting types for same variable name | Medium | Variant definition wins; log a warning; validate that merged definitions are well-formed before persisting to sandbox |

## Success Criteria

- [ ] `EvaluationVariant` table created by `init_pipeline_db()` with correct schema; `eval_runs.variant_id` and `eval_runs.delta_snapshot` columns added via `_migrate_add_columns` on existing DB
- [ ] `apply_instruction_delta()` unit tests pass for add, modify, empty delta, inherited-field remove rejection
- [ ] `EvalRunner.run_dataset(dataset_id, variant_id=X)` produces a run row with `variant_id` and `delta_snapshot` populated
- [ ] Evaluator resolution uses the delta-modified instructions class when `instructions_delta` is provided
- [ ] Sandbox receives correct model, prompt content, and `variable_definitions` overrides for all 4 delta types
- [ ] Variant CRUD endpoints return correct HTTP status codes and payloads; cascade delete removes variants on dataset deletion
- [ ] `POST /evals/{dataset_id}/runs` with `variant_id` triggers a variant run
- [ ] Frontend `useVariants`, `useCreateVariant`, `useDeleteVariant` hooks work against live backend
- [ ] Variants tab renders on dataset detail page; "New Variant" button navigates to editor
- [ ] Variant editor displays prod step definition read-only; delta changes persist on Save
- [ ] "Run with Variant" in editor triggers a run and navigates to Run History
- [ ] Comparison view renders side-by-side stats and per-case delta for two selected runs
- [ ] All existing `uv run pytest` tests continue to pass

---

## Security Constraints (ACE hygiene + future Docker-sandbox readiness)

CEO is wary of arbitrary code execution risk. This app targets enterprise production environments. No exclusions on testing or review. All implementation agents MUST follow these rules:

### Delta validation (enforced in Step 2: `apply_instruction_delta`)
- `_resolve_type(type_str)` MUST use a hard-coded whitelist dict lookup. NEVER use `eval()`, `exec()`, `typing.get_type_hints()`, `importlib`, or any dynamic resolution. Unknown `type_str` raises `ValueError`.
- Whitelist scope: `str`, `int`, `float`, `bool`, `list`, `dict`, `Optional[str]`, `Optional[int]`, `Optional[float]`, `Optional[bool]`. Nothing else.
- `field` names MUST match `^[a-z_][a-z0-9_]*$` via regex; reject anything else with `ValueError`. Prevents injection into pydantic internals, dunder access, or attribute traversal.
- `op` MUST be one of `{"add", "modify"}`. Unknown ops raise `ValueError` (not silently ignored — the research recommendation is superseded).
- `default` MUST be JSON-scalar, list of scalars, or flat dict of scalars. Reject callables, class refs, nested objects. Validate via `json.dumps(default)` round-trip.
- Cap `instructions_delta` list length at 50 entries; reject larger.
- Cap each `type_str`, `field`, `default` string length at 1000 chars.

### Delta serialization (enforced in Step 1, Step 3)
- `delta` and `delta_snapshot` columns MUST store JSON only — no pickled Python objects, no class references, no module paths in values.
- `delta_snapshot` is a frozen copy of the delta at run-time, stored on the `EvaluationRun` row. Never store Python class references or closures.

### `variable_definitions` merge (enforced in Step 3)
- `merge_variable_definitions()` MUST NOT evaluate `auto_generate` expressions during merge. Expression resolution stays in the existing registry-based resolver (`register_auto_generate`), which is a dict lookup, not `eval()`.
- Variant `auto_generate` expressions that reference unregistered names MUST fail at runtime with a clear error, not silently fall through to dynamic lookup.

### Docker-sandbox readiness (architectural invariants)
Even though sandboxing today = separate SQLite engine in-process, the design MUST preserve the ability to later run variant execution in a container:
- `apply_instruction_delta()` stays a pure function — no I/O, no global state, no session access. Can be relocated into a container later with zero refactor.
- `_build_step_task_fn` MUST NOT bake absolute host paths into delta or variant records.
- All data crossing into the sandbox layer MUST be JSON-serializable: delta dict, model string, prompt content strings, variable_definitions list. No passing of Python classes, closures, ORM objects, or file handles.
- The instructions class itself IS a Python class (cannot cross a process boundary), but the reference to reconstruct it (`{module_path, class_name}`) MUST be derivable from the step def. Don't leak the class object into `delta_snapshot` or variant storage.
- `create_sandbox_engine()` stays the clean interface seam. Future Docker implementation swaps the return type behind the same function.

### Test coverage required (enforced in Step 2, Step 3)
- Unit test: `type_str="__import__('os').system('ls')"` → `ValueError`
- Unit test: `field="__class__"` → `ValueError`
- Unit test: `field="items.append"` → `ValueError`
- Unit test: `op="eval"` → `ValueError`
- Unit test: `default=lambda: 1` → `ValueError`
- Unit test: `instructions_delta` length > 50 → `ValueError`
- Integration test: variant with malicious delta payload is rejected at API layer (422), never reaches runner.

### Backend API validation (enforced in Step 4)
- `VariantCreateRequest` / `VariantUpdateRequest` MUST call `apply_instruction_delta()` (dry-run) on the submitted delta before persisting. If validation fails, return HTTP 422 with the ValueError message. Prevents storing invalid deltas in the DB.

---

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** Core logic (`apply_instruction_delta` + runner reordering) is well-scoped with validated approach, but the sandbox prompt override path (especially `variable_definitions` merging) has implementation complexity. Frontend comparison view depends on backend run data being correctly structured. No breaking changes to existing APIs — all additions are additive. Prompt auto-discovery gap is a known open item that needs graceful handling.
**Suggested Exclusions:** none (CEO decision — enterprise production use, ACE risk awareness requires testing + review)
