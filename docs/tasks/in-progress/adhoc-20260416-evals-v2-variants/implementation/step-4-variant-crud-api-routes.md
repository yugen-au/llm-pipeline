# IMPLEMENTATION - STEP 4: VARIANT CRUD API ROUTES
**Status:** completed

## Summary
Added variant CRUD (list/create/read/update/delete) under `/api/evals/{dataset_id}/variants`, with dry-run ACE validation on delta. Extended run trigger to accept `variant_id` (validated against dataset) and passes through to runner. `RunListItem`/`RunDetail` expose `variant_id` + `delta_snapshot`. `delete_dataset` cascades variants. Added 30 endpoint tests.

## Files
**Created:** tests/ui/test_evals_routes.py
**Modified:** llm_pipeline/ui/routes/evals.py
**Deleted:** none

## Changes

### File: `llm_pipeline/ui/routes/evals.py`
- Imported `apply_instruction_delta` + `EvaluationVariant`.
- Added Pydantic models `VariantItem`, `VariantCreateRequest`, `VariantUpdateRequest`, `VariantListResponse`.
- Added `_variant_to_item` serializer and `_dry_run_validate_delta` helper (calls `apply_instruction_delta(pydantic.BaseModel, delta["instructions_delta"])`; translates `ValueError` to HTTP 422).
- Added 5 endpoints: `GET /evals/{dataset_id}/variants`, `POST /evals/{dataset_id}/variants` (201), `GET /evals/{dataset_id}/variants/{variant_id}`, `PUT /evals/{dataset_id}/variants/{variant_id}`, `DELETE /evals/{dataset_id}/variants/{variant_id}` (204). Listing ordered by `created_at desc`.
- `TriggerRunRequest`: added optional `variant_id: Optional[int]`.
- `trigger_eval_run`: now takes a `DBSession`, validates dataset exists (404), validates `variant_id` belongs to dataset (422 otherwise), passes `variant_id=` to `runner.run_dataset()`.
- `RunListItem`: added `variant_id: Optional[int]`, `delta_snapshot: Optional[dict]`. `list_eval_runs` and `get_eval_run` populate these.
- `delete_dataset`: after runs/cases deletion, also deletes variants for that dataset in same transaction.

### File: `tests/ui/test_evals_routes.py`
New file. Local `_make_evals_app` fixture (in-memory SQLite + StaticPool, mounts only `evals_router`). Covers:
- POST variant success + 404 on unknown dataset.
- POST malicious deltas (dunder field, `op=remove`, `os.system` type, `__import__(...)` type, traversal field) -> 422 with ValueError message.
- GET list ordered by `created_at desc`; 404 on unknown dataset.
- GET single 200/404 (including wrong-dataset 404).
- PUT full update, partial update (name only preserves delta/description), malicious delta 422, 404.
- DELETE 204 + re-fetch 404; DELETE 404 on unknown.
- Cascade: deleting a dataset removes its variants, leaves other datasets' variants intact.
- Trigger endpoint: valid variant_id passes through (captured via monkeypatched `EvalRunner.run_dataset`), missing `variant_id` still works (None passed through), mismatched-dataset variant 422, nonexistent variant 422, missing dataset 404.
- Run list & detail expose `variant_id` + `delta_snapshot` (including null for baseline runs).

## Decisions

### Dry-run base class for `apply_instruction_delta`
**Choice:** Use `pydantic.BaseModel` as the dry-run base in `_dry_run_validate_delta`.
**Rationale:** API layer does not know the real `step_def.instructions` at variant authoring time. The whitelist / field-name / op / type / default checks all fire regardless of the base class, so ACE protection is complete. The only edge case is `op=modify` of a field inherited from the real base without a `type_str`; that is surfaced at run-time by the runner and cannot be meaningfully checked here. Documented in the helper's docstring.

### `VariantUpdateRequest` partial semantics
**Choice:** All fields optional; omitted fields leave the DB row untouched. Delta is only dry-run-validated when provided.
**Rationale:** Matches the existing `DatasetUpdateRequest` / `CaseUpdateRequest` pattern in the same module. Supports PATCH-like partial updates via PUT (consistent with project's existing conventions — no PATCH endpoints used elsewhere).

### Trigger endpoint dataset validation
**Choice:** 404 when dataset missing, 422 when variant_id is provided but doesn't belong to the dataset.
**Rationale:** 404 for a missing parent resource is standard. 422 for a valid dataset but mismatched variant expresses semantic validation failure, matching the ACE-hygiene pattern (422 for bad delta) and the contract's explicit requirement.

### `delete_dataset` cascade ordering
**Choice:** Delete variants AFTER runs/cases (same transaction, before final `db.delete(ds)`).
**Rationale:** The existing method already deletes case_results, runs, cases in order. Variants have no FK dependents (runs reference variants via nullable FK, but those runs are already deleted). Adding after cases keeps the existing flow untouched and minimizes merge risk with Step 3.

### Runner signature expectations
**Choice:** Call `runner.run_dataset(dataset_id, model=..., variant_id=...)` unconditionally.
**Rationale:** Step 3 (concurrent) is extending the runner to accept `variant_id`. Per the contract we must not edit the runner ourselves. Tests monkeypatch `EvalRunner.run_dataset` so they don't depend on Step 3 landing.

## Verification
- [x] 30 new endpoint tests pass (`uv run pytest tests/ui/test_evals_routes.py -q`)
- [x] Existing `tests/test_eval_variants.py` (Steps 1 & 2) still pass
- [x] `tests/ui/` suite: 365 passed, 2 pre-existing failures unrelated to this step (`test_cli.py::test_atexit_registered_with_cleanup_vite`, `test_runs.py::test_returns_422_when_no_model_configured` — both fail without our changes too; verified via `git stash`).
- [x] Dry-run validation rejects malicious `field` (dunder/traversal), malicious `op`, non-whitelisted `type_str`, including attempted code injection literals.
- [x] Run list/detail responses include `variant_id` and `delta_snapshot` (null for baseline runs).
- [x] Dataset delete cascades variants for that dataset only; other datasets unaffected.
