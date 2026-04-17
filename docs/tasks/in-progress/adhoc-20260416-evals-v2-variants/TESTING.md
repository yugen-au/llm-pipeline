# Testing Results

## Summary
**Status:** passed

All 120 evals-v2-variants tests pass. 15 pre-existing failures in unrelated test files confirmed to be pre-existing on the branch (identical failures reproduced with stash applied — zero regressions introduced by this implementation). Frontend TypeScript compiles with no errors.

## Automated Testing

### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| test_eval_variants.py | Steps 1-3: DB schema, delta utility, merge helpers, sandbox override, runner integration | tests/test_eval_variants.py |
| test_eval_runner.py | Step 3 extended: baseline runner + variant-id pass-through | tests/test_eval_runner.py |
| test_evals_routes.py | Step 4: variant CRUD endpoints, cascade delete, run trigger with variant_id | tests/ui/test_evals_routes.py |

### Test Execution
**Pass Rate:** 120/120 (evals-v2-variants scope) | 1440/1455 total (15 pre-existing failures excluded)

**Targeted run (new tests only):**
```
============================= test session starts =============================
collected 120 items

tests/test_eval_variants.py - 86 passed
tests/test_eval_runner.py - 6 passed
tests/ui/test_evals_routes.py - 28 passed

============================== 120 passed, 1 warning in 4.93s =============================
```

**Full suite:**
```
15 failed, 1440 passed, 6 skipped, 5 warnings in 43.27s
```

**Pre-existing failures confirmed (identical on stash, not introduced by this branch):**
- tests/creator/test_sandbox.py::TestStepSandbox_WithMockDocker (6 tests) — `_discover_framework_path` attribute missing from StepSandbox; unrelated to evals
- tests/test_evaluators.py::TestFieldMatchEvaluator (7 tests) — FieldMatchEvaluator not callable + repr mismatch; unrelated to evals
- tests/ui/test_cli.py::TestDevModeWithFrontend::test_atexit_registered_with_cleanup_vite — atexit registered twice; unrelated to evals
- tests/ui/test_runs.py::TestTriggerRun::test_returns_422_when_no_model_configured — returns 202 instead of 422; unrelated to evals

### Failed Tests
None introduced by this implementation. All 15 failing tests reproduce identically with stash applied.

## Build Verification
- [x] `uv run pytest` exits 0 for all 120 evals-v2-variants tests
- [x] `npm run type-check` (`tsc -b --noEmit`) exits 0 with no output — no TypeScript errors
- [x] No new warnings introduced in evals test output (one pre-existing pydantic_evals DeprecationWarning for event loop)

## Success Criteria (from PLAN.md)
- [x] `EvaluationVariant` table created by `init_pipeline_db()` with correct schema; `eval_runs.variant_id` and `eval_runs.delta_snapshot` columns added via `_migrate_add_columns` on existing DB — verified by TestFreshDbCreation + TestMigrationOnExistingDb
- [x] `apply_instruction_delta()` unit tests pass for add, modify, empty delta, inherited-field remove rejection — verified by TestApplyInstructionDelta (55 cases)
- [x] `EvalRunner.run_dataset(dataset_id, variant_id=X)` produces a run row with `variant_id` and `delta_snapshot` populated — verified by TestRunnerVariantIntegration::test_run_with_variant_persists_variant_id_and_snapshot
- [x] Evaluator resolution uses the delta-modified instructions class when `instructions_delta` is provided — verified by TestRunnerVariantIntegration::test_evaluator_resolution_uses_modified_instructions_class
- [x] Sandbox receives correct model, prompt content, and `variable_definitions` overrides — verified by TestApplyVariantToSandbox (6 cases)
- [x] Variant CRUD endpoints return correct HTTP status codes and payloads; cascade delete removes variants on dataset deletion — verified by TestCreateVariant, TestListVariants, TestGetVariant, TestUpdateVariant, TestDeleteVariant, TestDeleteDatasetCascade
- [x] `POST /evals/{dataset_id}/runs` with `variant_id` triggers a variant run — verified by TestTriggerRunWithVariant
- [x] Frontend `useVariants`, `useCreateVariant`, `useDeleteVariant` hooks compile without type errors — verified by tsc --noEmit
- [ ] Frontend hooks work against live backend — requires manual UI validation (no live backend in test scope)
- [ ] Variants tab renders on dataset detail page — requires manual UI validation
- [ ] Variant editor displays prod step definition read-only; delta changes persist on Save — requires manual UI validation
- [ ] "Run with Variant" triggers run and navigates to Run History — requires manual UI validation
- [ ] Comparison view renders side-by-side stats and per-case delta — requires manual UI validation
- [x] All existing `uv run pytest` tests continue to pass (15 pre-existing failures confirmed pre-existing, zero regressions)

## Security Criteria (ACE hygiene — all must pass)
- [x] `type_str="__import__('os').system('ls')"` → ValueError — PASS (TestApplyInstructionDelta::test_unknown_type_str_raises + test_non_whitelisted_types_rejected)
- [x] `field="__class__"` → ValueError — PASS (TestApplyInstructionDelta::test_malicious_field_name_raises[__class__])
- [x] `field="items.append"` → ValueError — PASS (TestApplyInstructionDelta::test_malicious_field_name_raises[items.append])
- [x] `op="eval"` → ValueError — PASS (TestApplyInstructionDelta::test_unknown_op_raises[eval])
- [x] `default=lambda: 1` → ValueError — PASS (TestApplyInstructionDelta::test_callable_default_rejected)
- [x] `instructions_delta` length > 50 → ValueError — PASS (TestApplyInstructionDelta::test_oversized_delta_rejected)
- [x] Malicious delta payload at API layer → 422 — PASS (TestCreateVariant::test_create_variant_malicious_delta_returns_422, 5 parametrized cases; TestUpdateVariant::test_update_malicious_delta_returns_422)
- [x] `delta_snapshot` stores JSON only (no pickled objects) — verified by test_run_delta_snapshot_round_trip (round-trip through JSON column)

## Human Validation Required

### Frontend UI — Variants tab
**Step:** Step 6
**Instructions:** Start UI with `uv run llm-pipeline ui --dev`, open a dataset detail page, verify "Variants" tab appears alongside Cases and Run History.
**Expected Result:** Third tab labeled "Variants" with variant list table and "New Variant" button.

### Frontend UI — Variant editor
**Step:** Step 6
**Instructions:** Click "New Variant", fill in name, add an instructions delta row, save.
**Expected Result:** Variant created and editor shows split-pane with prod step read-only on left, delta on right.

### Frontend UI — Run with Variant
**Step:** Step 6
**Instructions:** In variant editor, click "Run with Variant". Check Run History tab.
**Expected Result:** New run appears with variant_id populated; delta_snapshot visible on run detail.

### Frontend UI — Comparison view
**Step:** Step 7
**Instructions:** Select two runs in Run History (one baseline, one variant), click "Compare".
**Expected Result:** Side-by-side stats and per-case delta table render at /evals/{datasetId}/compare.

## Issues Found
None

## Recommendations
1. Fix 15 pre-existing test failures (unrelated to this branch) in a separate task — they span creator/sandbox, evaluators, CLI, and runs routes.
2. Add vitest frontend unit tests for new variant hooks and components in a follow-up (currently no frontend test runner is exercised by CI).
