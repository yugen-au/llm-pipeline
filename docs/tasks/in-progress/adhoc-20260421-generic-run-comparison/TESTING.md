# Testing Results

## Summary
**Status:** passed
All 8 implementation steps verified. Backend pytest passes with only pre-existing failures (16, up from 15 baseline — one additional pre-existing failure in `test_wal.py`). TypeScript compiles clean. ESLint had 5 errors in compare.tsx introduced by Step 4/6/7 refactors — all fixed during this testing phase (hooks-after-early-return violations, unused import, useless escape). No regressions introduced.

## Automated Testing

### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| npx tsc --noEmit | TS type correctness | llm_pipeline/ui/frontend/ |
| npx eslint src/... | Lint errors in modified files | llm_pipeline/ui/frontend/ |
| uv run pytest | Backend regression check | tests/ |
| uv run pytest tests/ui/test_evals_routes.py | Evals-specific backend tests | tests/ui/test_evals_routes.py |

### Test Execution
**Pass Rate:** 1553/1569 backend tests (16 pre-existing failures, 0 regressions)

Evals route tests: 47/47 passed

```
TSC: no errors (TSC_OK)
ESLint: no errors after fixes (0 problems)
pytest: 16 failed, 1553 passed, 6 skipped (all 16 failures pre-existing)
tests/ui/test_evals_routes.py: 47 passed
```

### Failed Tests
None related to this work. All 16 failures are pre-existing:
- `tests/creator/test_sandbox.py` — 6 failures (pre-existing Docker mock issues)
- `tests/test_evaluators.py` — 7 failures (pre-existing FieldMatchEvaluator)
- `tests/ui/test_cli.py::TestDevModeWithFrontend::test_atexit_registered_with_cleanup_vite` — 1 pre-existing
- `tests/ui/test_runs.py::TestTriggerRun::test_returns_422_when_no_model_configured` — 1 pre-existing
- `tests/ui/test_wal.py::TestWALMode::test_file_based_sqlite_sets_wal` — 1 pre-existing

## Build Verification
- [x] `uv run pytest` — 1553 passed, 16 pre-existing failures, 0 new failures
- [x] `npx tsc --noEmit` — no errors
- [x] `npx eslint` on modified files — no errors after fixes
- [x] Backend `case_id` mapped correctly in `evals.py` line 1046 (`case_id=cr.case_id`)
- [x] Frontend `RunListItem` snapshot fields added (`case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot`)
- [x] Frontend `CaseResultItem.case_id: number` added

## Success Criteria (from PLAN.md)
- [x] `GET /evals/{dataset_id}/runs/{run_id}` returns `case_id` on each case result item — verified in `evals.py` line 1046
- [x] Frontend `RunListItem` TS type includes `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot` — in `api/evals.ts`
- [x] Compare page URL accepts both `compareRunId` and `variantRunId` params — Zod schema uses `z.preprocess` alias
- [x] Compare button on run detail page visible for ALL completed runs — `isVariantRun` gate removed in `runs.$runId.tsx`
- [x] Run picker dialog shows only completed runs from same dataset excluding current — filter in `RunPickerDialog`
- [x] Compare page labels show "Base" and "Compare" (not "Baseline"/"Variant") — label rename complete
- [x] Delta summary card renders for all run pairs — variant-gating removed, snapshot-based diff
- [x] Delta card shows diff of `prompt_versions` + `model_snapshot` between base and compare runs — `baseConfig`/`compareConfig` memos
- [x] Each case row shows version match indicator when bucket is drifted or unmatched — `bucketByName` + badge in `CaseRow`
- [x] Aggregate scope toggle only appears when drifted or unmatched count > 0 — `showScopeToggle` conditional
- [x] Export META_PROMPT is comparison-neutral — updated constant
- [x] Export JSON payload `variant` field replaced with `comparison: {base_run_id, compare_run_id}` — `buildPayloadJSON` updated
- [x] `uv run pytest` passes after backend change — 47/47 evals route tests pass
- [x] TypeScript compiles without errors after frontend changes — `tsc --noEmit` clean

## Issues Found (fixed during testing)

### React hooks called after early returns
**Severity:** high
**Step:** Step 6 (case matching logic) and Step 7 (delta summary card)
**Details:** Three `useMemo` hooks (`filteredAggregateStats`, `baseConfig`, `compareConfig`) were placed after early-return guards (lines 1521–1563), violating rules-of-hooks. ESLint reported 3 `react-hooks/rules-of-hooks` errors. Fixed by moving all three memos before the early returns and adding optional chaining (`?.`) for `baseRun`/`compareRun` null safety.

### Unused VariantItem import
**Severity:** low
**Step:** Step 4 (label rename / import cleanup)
**Details:** `VariantItem` was imported from `@/api/evals` but not used after the rename. Removed from import list.

### Useless escape in yamlString regex
**Severity:** low
**Step:** Step 8 (export rewrite) or pre-existing
**Details:** `\[` inside a character class does not need escaping. Changed `\[` to `[`. ESLint `no-useless-escape` rule.

## Human Validation Required

### Compare button visible on all completed runs
**Step:** Step 5
**Instructions:** Open any completed eval run detail page (not a variant run). Verify "Compare" button is visible and clickable. Click it — a dialog should appear listing other completed runs from the same dataset.
**Expected Result:** Button present, dialog opens with completed runs list, selecting a run navigates to compare page with `baseRunId` and `compareRunId` params.

### Compare page accepts old variantRunId URL
**Step:** Step 3
**Instructions:** Navigate to `/evals/{datasetId}/compare?baseRunId=X&variantRunId=Y` (using old param name). Verify page loads correctly.
**Expected Result:** Page loads the comparison for runs X and Y without error.

### Delta card for non-variant run pair
**Step:** Step 7
**Instructions:** Compare two baseline (non-variant) runs. Verify the delta summary card renders (not hidden). If both runs have null `prompt_versions`/`model_snapshot`, verify "No snapshot data recorded for either run" message shows.
**Expected Result:** Delta card always visible; shows diff or no-data message.

### Case version match indicators
**Step:** Step 6
**Instructions:** Compare two runs where the same case was updated between runs (different `case_versions`). Verify drifted cases show amber badge. Verify aggregate scope toggle appears when drifted/unmatched count > 0.
**Expected Result:** Amber "drifted" badge on affected case rows; scope toggle visible.

## Recommendations
1. Add backend test asserting `case_id` is non-zero on `CaseResultItem` response for a run with known case IDs
2. Add frontend unit test (Vitest) for `computeCaseBucket` with matched/drifted/unmatched scenarios
3. Consider adding E2E test (Playwright) for the run picker dialog flow once test infra is set up
