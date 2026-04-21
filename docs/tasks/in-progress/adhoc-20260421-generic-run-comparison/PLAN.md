# PLANNING

## Summary

Replace the baseline-only comparison flow with generic any-two-runs comparison. Backend adds `case_id` to `CaseResultItem` and frontend TS types are synced. The compare page is refactored to accept `baseRunId`/`compareRunId` (with `variantRunId` alias), compute matched/drifted/unmatched case buckets client-side, update labels from Baseline/Variant to Base/Compare, replace variant-gated delta card with snapshot diff between any two runs, rewrite the export META_PROMPT to be comparison-neutral, and show a "Compare" button on ALL runs (not just variant runs) via a run picker dialog.

## Plugin & Agents

**Plugin:** frontend-mobile-development, backend-development
**Subagents:** backend-development:backend-architect, frontend-mobile-development:frontend-developer
**Skills:** none

## Phases

1. **Backend fix**: Add `case_id` to `CaseResultItem` Pydantic model (prerequisite for all version matching logic)
2. **Frontend type sync**: Update `RunListItem` TS interface with 4 missing snapshot fields, update `CaseResultItem` with `case_id`
3. **URL + search param refactor**: Accept `compareRunId` (and `variantRunId` as alias) in compare page Zod schema
4. **Label rename**: Replace all ~194 "Baseline"/"Variant" label strings with "Base"/"Compare" throughout compare.tsx
5. **Run detail compare button**: Show compare button on ALL runs, open a run picker dialog (completed runs only, same dataset)
6. **Case matching logic**: Implement matched/drifted/unmatched buckets client-side in compare page, add version match indicators per row
7. **Delta summary card**: Remove variant-gating, build snapshot diff from `prompt_versions` + `model_snapshot` of both runs
8. **Export rewrite**: Rewrite META_PROMPT and export payload to be comparison-neutral (remove variant section from JSON payload, update markdown)

## Architecture Decisions

### Client-side case version matching
**Choice:** Frontend computes matched/drifted/unmatched from two `RunDetail` responses using `case_id` + `case_versions` per run. No new backend endpoint.
**Rationale:** Both runs' `case_versions` maps (`{str(case.id): version}`) are already returned in `RunListItem`. Once `case_id` is added to `CaseResultItem`, each case result can be cross-referenced against both runs' `case_versions` to determine bucket. Legacy runs (both `case_versions` null) treat shared `case_name` as matched.
**Alternatives:** New backend comparison endpoint — deferred; adds API surface area and requires serializing the matching logic server-side.

### Snapshot diff replaces variant delta card
**Choice:** Delta summary card always renders using `prompt_versions` + `model_snapshot` from both runs. Variant-gating removed. `buildBefore`/`buildAfter` approach replaced with direct diff of two `EffectiveConfig`-shaped objects extracted from each run's snapshot fields.
**Rationale:** All runs now carry `prompt_versions` and `model_snapshot` (from `RunListItem`). Diffing them shows actual configuration change regardless of whether a variant was used.
**Alternatives:** Keep variant-gating and only show diff for variant runs — rejected per CEO Q3 decision.

### Run picker dialog on run detail
**Choice:** Replace the variant-gated compare button with a universal "Compare" button that opens a dialog listing all completed runs in the same dataset (excluding the current run). User selects the run to compare against; navigation sets `baseRunId=currentRun&compareRunId=selected` (or inverted — current as base, selected as compare, depending on which is older).
**Rationale:** Any run can now be compared. No dependency on `variant_id`. Completed-only filter prevents partial-result confusion (CEO Q5).
**Alternatives:** Dropdown inline in header — rejected for discoverability; dialog is already used for large-payload warning.

### URL param: baseRunId/compareRunId with variantRunId alias
**Choice:** Zod schema accepts both `compareRunId` and `variantRunId`, coercing `variantRunId` to `compareRunId`. `baseRunId` unchanged.
**Rationale:** Backward-compatible with any existing links that use `variantRunId`. Zod `transform` or `default`/`fallback` with both fields then pick non-zero value.
**Alternatives:** Hard rename to `leftRunId`/`rightRunId` — rejected per CEO Q1.

### Aggregate scope toggle
**Choice:** Show matched-cases-only aggregate toggle conditionally — only render when drifted or unmatched count > 0.
**Rationale:** Reduces UI noise for clean comparisons (CEO Q9).
**Alternatives:** Always show toggle — rejected.

## Implementation Steps

### Step 1: Add case_id to CaseResultItem backend model
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/ui/routes/evals.py`, add `case_id: int = 0` to `CaseResultItem` Pydantic model (lines 101-107)
2. In the route handler that builds `CaseResultItem` list from `EvaluationCaseResult` ORM rows, map `result.case_id` to the field (the ORM model at `llm_pipeline/evals/models.py` line 95 already has `case_id: int`)
3. Verify with existing test suite (`uv run pytest tests/`) — no new tests needed for a field add

### Step 2: Sync frontend TS types
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/ui/frontend/src/api/evals.ts`, update `RunListItem` interface (lines 44-56) to add the 4 missing fields: `case_versions: Record<string, unknown> | null`, `prompt_versions: Record<string, unknown> | null`, `model_snapshot: Record<string, unknown> | null`, `instructions_schema_snapshot: Record<string, unknown> | null`
2. In same file, update `CaseResultItem` interface (lines 58-65) to add `case_id: number`
3. Check `RunDetail extends RunListItem` — no change needed since it inherits

### Step 3: Zod schema — accept compareRunId + variantRunId alias
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** /colinhacks/zod
**Group:** B

1. In `evals.$datasetId.compare.tsx` (lines 67-70), update `compareSearchSchema` to add `compareRunId` as primary param and `variantRunId` as accepted alias: use `z.union` or a `transform` that resolves `compareRunId ?? variantRunId ?? 0` into a single `compareRunId` value
2. Update all references in `CompareRunsPage` from `variantRunId` to `compareRunId`; keep backward-compat for incoming `variantRunId` links
3. Update `handleCompare` in `evals.$datasetId.runs.$runId.tsx` to navigate with `compareRunId` (not `variantRunId`)

### Step 4: Rename Baseline/Variant labels to Base/Compare
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `evals.$datasetId.compare.tsx`, do a systematic find-replace of all user-facing label strings: "Baseline" -> "Base", "Variant" -> "Compare" (approximately 194 occurrences; use search-replace, not manual edits)
2. Rename internal variable/function names for clarity: `variantRun` -> `compareRun`, `variantByName` -> `compareByName`, `variantRunId` -> `compareRunId`, `variantQ` -> `compareRunQ` etc. throughout compare.tsx
3. Update column headers in `<TableHead>`: "Baseline" -> "Base", "Variant" -> "Compare", "Baseline scores" -> "Base scores", "Variant scores" -> "Compare scores"
4. Update `CaseDetailCard` prop names (`baselineResult`/`variantResult` -> `baseResult`/`compareResult`) and all call sites
5. Update `buildPayloadMarkdown` and `aggregateComparisonTable` to use "Base" / "Compare" labels

### Step 5: Run detail — universal compare button + run picker dialog
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. In `evals.$datasetId.runs.$runId.tsx`, remove the `isVariantRun` gate on the compare button (lines 199-204, 285-316)
2. Remove `findMostRecentBaseline` helper and auto-selection logic — no longer needed
3. Add state: `const [pickerOpen, setPickerOpen] = useState(false)`
4. `useEvalRuns(datasetId)` is already called unconditionally — filter for `status === 'completed'` and `id !== runId` for picker candidates
5. Add a `RunPickerDialog` component (inline or in the file): renders a `Dialog` with a scrollable list of completed runs sorted by `started_at` descending; each row shows run ID, started_at, pass rate, and a "Select" button
6. On select: navigate to compare page with `baseRunId = min(runId, selectedId)` and `compareRunId = max(runId, selectedId)` so older run is always base (or let user see current run as `compareRunId` if it was triggered after — just use `baseRunId: selectedId, compareRunId: runId` where selected is the reference)
7. Update compare button to be always enabled (no tooltip disabled state) and open picker dialog

### Step 6: Client-side case version matching
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. In `evals.$datasetId.compare.tsx`, add `VersionBucket` type: `'matched' | 'drifted' | 'unmatched'`
2. Implement `computeCaseBucket(caseName, baseResult, compareResult, baseRun, compareRun): VersionBucket` function:
   - If either result missing: `'unmatched'`
   - If both runs have `case_versions === null`: `'matched'` (legacy — shared name = matched)
   - Otherwise: look up `str(baseResult.case_id)` in `baseRun.case_versions` and `str(compareResult.case_id)` in `compareRun.case_versions`; if versions equal: `'matched'`, else `'drifted'`
3. Extend the `useMemo` that builds `baseByName`/`compareByName`/`allCaseNames` to also compute `bucketByName: Map<string, VersionBucket>`
4. Add aggregate counts: `matchedCount`, `driftedCount`, `unmatchedCount` derived from `bucketByName`
5. Add version match indicator per row in `CaseRow` component: small badge showing `drifted` (amber) or `unmatched` (muted) in a new column or inline with case name; matched cases show nothing
6. Add conditional aggregate scope toggle (only render when `driftedCount + unmatchedCount > 0`): a `Switch` or `SegmentedControl` between "All cases" and "Matched only"; when "Matched only" selected, filter `allCaseNames` to only matched cases for stats computation

### Step 7: Delta summary card — snapshot diff for any two runs
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** D

1. In `evals.$datasetId.compare.tsx`, replace `deltaSnapshot` derivation (line 1576, currently from `variantRun.delta_snapshot`) with snapshot-based diff:
   - Extract `baseConfig: {prompt_versions, model_snapshot}` from `baseRun` (using the newly synced `RunListItem` fields)
   - Extract `compareConfig: {prompt_versions, model_snapshot}` from `compareRun`
2. Remove the `summaryReady` guard that requires `deltaSnapshot != null` (line 1591)
3. Update `summaryBefore` and `summaryAfter` to be built from `baseConfig` and `compareConfig` directly — pass them to `JsonViewer` `before`/`after` props
4. Update the card's "no diff" fallback message: show "No snapshot data recorded for either run" when both configs are null
5. Remove `useVariant` fetch from `CompareRunsPage` (no longer needed for delta card); retain only if still referenced elsewhere (variant name in header — see Step 4)

### Step 8: Export — neutral META_PROMPT and payload
**Agent:** frontend-mobile-development:frontend-developer
**Skills:** none
**Context7 Docs:** -
**Group:** E

1. In `evals.$datasetId.compare.tsx`, replace `META_PROMPT` constant (lines 522-519) with a comparison-neutral version: "# Eval Run Comparison Context\n\nYou are analyzing differences between two evaluation runs of a production LLM step. Given the context below, identify patterns in the failing cases and suggest improvements."
2. In `buildPayloadJSON`, replace the `variant` field with a `comparison` field: `{ base_run_id: number, compare_run_id: number }` — remove variant lookup from args
3. In `buildPayloadMarkdown`, replace the `## Current variant` section with `## Comparison summary` that shows base run ID vs compare run ID, removing variant delta block
4. Update `buildArgs()` and `BuildPayloadArgs` interface to remove `variant` / `variantId` — no longer needed
5. Update `exportFilename` to use `compareRunId` (line 1429 currently uses `variantRunId`)
6. Update column headers in `aggregateComparisonTable` from "Baseline (#N)" / "Variant (#N)" to "Base (#N)" / "Compare (#N)"
7. Update `caseMarkdownSection` to use "base" / "compare" labels instead of "baseline" / "variant"

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `case_id=0` edge case (deleted cases, runner.py line 222) stored with null case_id | Low | Treat `case_id=0` as unresolvable; bucket as `'unmatched'` in version matching logic |
| Zod alias approach for `variantRunId` -> `compareRunId` may conflict with TanStack Router param handling | Medium | Test both old-style (`variantRunId=X`) and new-style (`compareRunId=X`) URL navigation in browser; use `.transform()` or preprocess to merge |
| 194 label replacements in compare.tsx may miss internal variable names or create TS errors | Medium | After replacement, run `tsc --noEmit` to surface type errors; check all component prop names are consistent |
| `RunDetail extends RunListItem` means adding snapshot fields to `RunListItem` also adds them to `RunDetail` — but backend `RunDetail` handler must also return them | Low | Backend `RunDetail` response already includes parent `RunListItem` fields since it fetches full `EvaluationRun` including all columns — verify in `GET /evals/{dataset_id}/runs/{run_id}` handler |
| Run picker with large number of completed runs may be slow to render | Low | Use existing `ScrollArea` with simple list rows; no virtualization needed for typical eval run counts |
| Removing `useVariant` from compare page if variant name still shown in header | Low | Keep `useVariant` only if `compareRun.variant_id != null` display is retained; otherwise remove import |

## Success Criteria

- [ ] `GET /evals/{dataset_id}/runs/{run_id}` returns `case_id` on each case result item
- [ ] Frontend `RunListItem` TS type includes `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot`
- [ ] Compare page URL accepts both `compareRunId` and `variantRunId` params without error
- [ ] Compare button on run detail page is visible for ALL completed runs (not just variant runs)
- [ ] Run picker dialog shows only completed runs from the same dataset, excluding current run
- [ ] Compare page labels show "Base" and "Compare" (not "Baseline"/"Variant") throughout
- [ ] Delta summary card renders for all run pairs (not gated on `delta_snapshot != null`)
- [ ] Delta card shows diff of `prompt_versions` + `model_snapshot` between base and compare runs
- [ ] Each case row shows a version match indicator when bucket is drifted or unmatched
- [ ] Aggregate scope toggle only appears when drifted or unmatched count > 0
- [ ] Export META_PROMPT is comparison-neutral (no variant-specific language)
- [ ] Export JSON payload `variant` field replaced with `comparison: {base_run_id, compare_run_id}`
- [ ] `uv run pytest` passes after backend change
- [ ] TypeScript compiles without errors after frontend changes

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** The scope is large (1891-line file, ~194 label replacements, new case matching logic, snapshot diff change, run picker dialog) but all decisions are locked and research is validated. The main risks are TS type consistency after the large rename and the Zod alias approach. No new backend endpoints or schema migrations required. Frontend work dominates and is self-contained to 3 files.
**Suggested Exclusions:** review
