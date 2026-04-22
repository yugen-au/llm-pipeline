# Task Summary

## Work Completed

Replaced the baseline-only eval comparison flow with a generic any-two-runs comparison system. 8 implementation steps across backend and frontend: adding `case_id` to the backend `CaseResultItem` response, syncing frontend TS types with 4 missing snapshot fields, refactoring URL params to accept `compareRunId` with `variantRunId` backward-compat alias, renaming all user-facing labels from Baseline/Variant to Base/Compare, adding a universal compare button with a run picker dialog on the run detail page, implementing client-side case version matching (matched/drifted/unmatched buckets via `case_versions` snapshots), replacing variant-gated delta summary with a snapshot diff card for any run pair, and rewriting the export meta-prompt and payload to be comparison-neutral.

5 review fixes applied (2 medium resolved, 1 medium resolved by another fix, 2 low) plus 1 auto-fixed ESLint error during re-verification. All tests pass. Review approved cleanly after fixes.

## Files Changed

### Created
None.

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/ui/routes/evals.py` | Added `case_id: Optional[int] = None` to `CaseResultItem`; mapped in both list and detail handlers; docstring explains runner.py sentinel |
| `llm_pipeline/ui/frontend/src/api/evals.ts` | Added 4 snapshot fields to `RunListItem` (`case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot`); added `case_id: number | null` with TSDoc to `CaseResultItem` |
| `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx` | Zod schema with `compareRunId`+`variantRunId` alias via `.transform()`; ~194 Baseline/Variant label renames; `computeCaseBucket` with version matching; `bucketByName` map and version match badges per case row; `showScopeToggle` conditional; snapshot-based delta card (filtered-inclusion, no force-cast); neutral export meta-prompt and comparison payload; all hooks moved before early returns |
| `llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx` | Removed `isVariantRun` gate; removed `findMostRecentBaseline`; added `RunPickerDialog` (completed only, excludes self, sorted desc by `started_at`); contextual `aria-label` on Select buttons |

## Commits Made

| Hash | Message |
| --- | --- |
| `6249de3d` | docs(implementation-A): Step 2 sync frontend TS types |
| `b8c76a6a` | docs(implementation-A): Step 1 add case_id to CaseResultItem |
| `8b48ccac` | docs(implementation-B): Step 3 Zod schema compareRunId alias |
| `aac9ca0a` | docs(implementation-B): Step 4 rename labels Base/Compare |
| `5b037a42` | docs(implementation-B): Step 4 state + task log |
| `e0509022` | docs(implementation-C): Step 5 universal compare button + picker |
| `0da4c5a0` | docs(implementation-D): Step 6 case version matching logic |
| `febfdd6a` | docs(implementation-D): Step 7 delta summary snapshot diff |
| `e22de50e` | docs(implementation-E): Step 8 export neutral meta-prompt |
| `fae357b1` | docs(testing-A): initial test run (ESLint errors found) |
| `d4ebb002` | docs(testing-A): ESLint fixes (hooks-before-returns, unused import, useless escape) |
| `0ceffc3d` | docs(fixing-review-A): Fix #3 case_id Optional[int]=None + TSDoc |
| `72fa5f09` | docs(fixing-review-B): Fix #5 Zod URL-rewrite comment |
| `e16d48a2` | fix(ui): aria-label on run picker Select buttons |
| `634e9d72` | docs(fixing-review-D): Fix #1 setState seed, Fix #2 JsonViewer null-cast, Fix #7 _caseName param |
| `ede9bc70` | docs(testing-A): ESLint fix replace useEffect with setState-during-render key-gate |
| `fef4f306` | docs(testing-A): re-run test results |
| `3bbee64d` | docs(review): initial architect review |
| `012a5ff1` | docs(review-A): re-review post-fix |

## Deviations from Plan

- `CaseResultItem.case_id` initially `int = 0` per plan; review flagged inconsistency with `Optional[T] = None` convention; fixed to `Optional[int] = None` with explicit sentinel mapping. Frontend type updated to `number | null`.
- Step 7 delta card initially built configs with force-cast; review flagged null-safety bypass; fixed to filtered-inclusion (only non-null fields included).
- The expanded seed pattern (Step 6) went through two forms: render-phase setState -> useEffect in `634e9d72` -> reverted to setState-during-render with key-gate in `ede9bc70` to satisfy `react-hooks/set-state-in-effect` lint rule. Final form is the React-documented Adjusting state while rendering pattern.

## Issues Encountered

### React hooks called after early returns (testing phase)
Three `useMemo` hooks (`filteredAggregateStats`, `baseConfig`, `compareConfig`) placed after early-return guards violated rules-of-hooks. ESLint reported 3 errors.

**Resolution:** Moved all three memos before early returns with optional chaining for null safety. Fixed during testing before review.

### Unused VariantItem import (testing phase)
`VariantItem` imported from `@/api/evals` but unused after label rename.

**Resolution:** Removed from import list.

### Useless escape in yamlString regex (testing phase)
Escaped bracket inside character class triggered `no-useless-escape`.

**Resolution:** Changed to unescaped bracket.

### setState-in-effect ESLint error (re-verification after review fixes)
The `useEffect` introduced in `634e9d72` to seed expanded set triggered `react-hooks/set-state-in-effect` from the recommended-latest ruleset.

**Resolution:** Combined seededFor + expanded into single `expandedState: { key, set }` object updated during render with key-gate, removing the effect entirely. Commit `ede9bc70`.

### JsonViewer force-cast bypasses null-safety (review issue #2)
`baseConfig`/`compareConfig` snapshot objects force-cast via `as unknown as Record<string, unknown>` silenced null handling at JsonViewer boundary. Partial nulls could reach DiffView unguarded.

**Resolution:** Filtered-inclusion approach: only non-null snapshot fields included in config objects; `hasSnapshotData` rewritten to `Object.keys(...).length > 0`. Fixed in `634e9d72`.

### aria-label missing on run picker Select buttons (review issue #4)
Select buttons in `RunPickerDialog` announced only Select button with no run context for screen readers.

**Resolution:** Added `aria-label` template interpolating run ID, variant label, started_at, pass rate. Fixed in `e16d48a2`.

### case_id=0 sentinel undocumented and inconsistent typing (review issues #3, #6)
`int = 0` sentinel inconsistent with `Optional[T] = None` on other model fields; no TSDoc in frontend `CaseResultItem` type explaining null semantics.

**Resolution:** `Optional[int] = None` with docstring explaining runner.py sentinel; detail handler maps `case_id == 0` to `None`; TS type `number | null` with TSDoc; `computeCaseBucket` adds explicit null guard. Fixed in `0ceffc3d`.

## Success Criteria

- [x] `GET /evals/{dataset_id}/runs/{run_id}` returns `case_id` on each case result item
- [x] Frontend `RunListItem` TS type includes `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot`
- [x] Compare page URL accepts both `compareRunId` and `variantRunId` params without error
- [x] Compare button visible for ALL completed runs (not just variant runs)
- [x] Run picker shows only completed runs from same dataset excluding current
- [x] Compare page labels show Base and Compare throughout
- [x] Delta summary card renders for all run pairs
- [x] Delta card shows diff of `prompt_versions` + `model_snapshot`
- [x] Case rows show version match indicator when drifted or unmatched
- [x] Aggregate scope toggle only appears when drifted or unmatched count > 0
- [x] Export META_PROMPT is comparison-neutral
- [x] Export JSON payload uses `comparison: {base_run_id, compare_run_id}` (not variant)
- [x] `uv run pytest` passes: 47/47 evals route tests; 1553/1569 total (16 pre-existing, 0 regressions)
- [x] TypeScript compiles without errors (tsc --noEmit clean)
- [x] ESLint clean on all 4 modified files

## Recommendations for Follow-up

1. Add backend test asserting `case_id` is non-null on `CaseResultItem` for a run with known case IDs.
2. Add frontend unit test (Vitest) for `computeCaseBucket` covering matched, drifted, unmatched, and legacy-null paths.
3. Add E2E test (Playwright) for run picker dialog flow once frontend test infra is set up.
4. Use `cr.case_id != 0` explicit check over `if cr.case_id` in `evals.py` for clarity.
5. Add comment near setState-during-render seed block noting expanded is transitional on the seed render.
6. Broaden `JsonViewerProps.before`/`after` to accept `Record<string, unknown> | null` rather than relying on filtered-inclusion at every call site.
7. Address run picker row-level keyboard affordance: rows are div with hover style but only inner button is focusable; consider role=option inside role=listbox with arrow-key navigation for larger datasets.
