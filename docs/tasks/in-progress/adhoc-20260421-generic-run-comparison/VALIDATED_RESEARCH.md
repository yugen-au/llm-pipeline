# Research Summary

## Executive Summary

Both research documents (frontend UI + backend logic) are accurate against the current codebase. All major claims verified by reading source. Key confirmed gaps: CaseResultItem missing `case_id`, frontend TS types stale (missing 4 snapshot fields), compare button variant-gated. Two additional gaps discovered: run status filtering for picker, legacy-run version matching semantics, and aggregate toggle UX. Nine questions consolidated for CEO and all answered -- decisions locked below.

**Locked Decisions:**
- URL params: `baseRunId`/`compareRunId` (accept `variantRunId` as fallback alias for `compareRunId`)
- Labels: "Base" / "Compare" throughout UI
- Delta summary: snapshot diff always (prompt_versions + model_snapshot), not variant-gated
- Export META_PROMPT: neutral comparison prompt ("analyze differences between these two runs")
- Run picker: completed runs only
- Cross-dataset: deferred (same dataset only for now)
- Architecture: client-side matching, no new backend endpoint
- Legacy runs: assume matched when both case_versions null (shared case_names = matched)
- Aggregate scope toggle: only visible when drifted/unmatched > 0

## Domain Findings

### Frontend Comparison Architecture
**Source:** step-1-frontend-comparison-ui-research.md

- Search params `baseRunId`/`variantRunId` with Zod schema CONFIRMED (compare.tsx lines 67-70)
- Case joining by `case_name` via Map, union of keys CONFIRMED (compare.tsx lines 1365-1374)
- Compare button gated on `isVariantRun` CONFIRMED (runs.$runId.tsx lines 199-203)
- `findMostRecentBaseline()` auto-selects most recent non-variant run CONFIRMED (runs.$runId.tsx lines 168-184)
- Delta summary card gated on `deltaSnapshot != null` CONFIRMED (compare.tsx line 1591, 1740)
- 194 occurrences of "Baseline"/"Variant"/"baseline"/"variant" in compare.tsx - substantial rename scope
- Component reuse assessment accurate: DeltaBadge, PassFailBadge, ScoresCell etc are generic; label-coupled components correctly identified

### Frontend TS Type Drift
**Source:** step-1-frontend-comparison-ui-research.md, step-2-backend-comparison-logic-research.md

- Frontend `RunListItem` (evals.ts lines 44-56) has only `delta_snapshot` - MISSING `case_versions`, `prompt_versions`, `model_snapshot`, `instructions_schema_snapshot`
- Backend `RunListItem` (routes/evals.py lines 110-125) has all five Optional[dict] fields
- Frontend `CaseResultItem` (evals.ts lines 58-65) missing `case_id` - backend CaseResultItem (routes/evals.py lines 101-107) also missing it
- DB model `EvaluationCaseResult` (models.py line 95) HAS `case_id: int`

### Backend Snapshot Architecture
**Source:** step-2-backend-comparison-logic-research.md

- `case_versions` built as `{str(c.id): c.version}` CONFIRMED (runner.py line 632)
- case_id derivation path validated: within a single run, `case_result.case_id` matches keys in that run's `case_versions` because both derive from same cases query. Cross-run, different case_ids for same case_name is expected and handled correctly by per-run derivation.
- Runner stores case_id=0 when name_to_id lookup fails (runner.py line 222,237) - minor edge case for deleted cases

### Case Version Matching Strategy
**Source:** step-2-backend-comparison-logic-research.md

- Three buckets (matched/drifted/unmatched) well-defined
- "unknown" fourth bucket for legacy runs (case_versions=null) proposed but semantics underspecified (see open items)
- Client-side Option A recommended by both docs - validated as feasible, requires only adding case_id to CaseResultItem

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Q1: Rename URL params to leftRunId/rightRunId? | Keep `baseRunId`/`compareRunId`. Accept `variantRunId` as fallback alias for `compareRunId`. | Smaller rename scope than left/right. Semantic naming ("base" = reference, "compare" = target). Backward compat via alias. |
| Q2: What labels replace Baseline/Variant? | "Base" / "Compare" | ~194 string replacements in compare.tsx. Labels capture semantic relationship clearly. |
| Q3: Delta summary card for non-variant comparisons? | Snapshot diff always -- use `prompt_versions` + `model_snapshot` to show config diffs between ANY two runs. | Remove variant-gating on delta card. Generalizes to all comparison types. |
| Q4: Export META_PROMPT for non-variant comparisons? | Neutral prompt: "analyze differences between these two runs". | Rewrite existing variant-specific META_PROMPT. Single code path, no branching. |
| Q5: Run picker -- completed only or also failed/partial? | Completed runs only. | Simpler picker, no partial-result confusion. Filter by run status in picker query. |
| Q6: Cross-dataset comparison? | Defer. Same dataset only for now. | Add dataset guard to picker/URL validation. Significant scope reduction. |
| Q7: Client-side matching vs backend endpoint? | Client-side. Frontend computes matched/drifted/unmatched from two RunDetail responses. No new backend endpoint. | No backend work beyond CaseResultItem fix. All matching logic in frontend. |
| Q8: Legacy runs (both case_versions=null) -- matched or unknown bucket? | Assume matched. Shared case_names treated as matched when both null. | No "unknown" fourth bucket needed. Preserves current behavior for old data. Simplifies UI. |
| Q9: Aggregate scope toggle -- always visible or conditional? | Only show when drifted/unmatched > 0. | Reduces UI noise. Toggle hidden when all cases match. |

## Assumptions Validated
- [x] CaseResultItem backend Pydantic model lacks case_id (confirmed routes/evals.py line 101-107)
- [x] Frontend TS RunListItem missing 4 snapshot fields (confirmed evals.ts line 44-56)
- [x] case_versions keyed by str(case.id), not case_name (confirmed runner.py line 632)
- [x] Per-run case_id derivation works: case_result.case_id matches case_versions keys within same run
- [x] Compare button only shown for variant runs (confirmed runs.$runId.tsx line 285)
- [x] No backend comparison endpoint exists (confirmed - only RunDetail fetch per run)
- [x] Delta summary card depends on deltaSnapshot presence (confirmed compare.tsx line 1591)
- [x] All comparison logic is client-side (confirmed - two RunDetail fetches, client joins)

## Open Items
- Cross-dataset comparison deferred to future iteration (CEO decision Q6). Will need dataset guard in picker/URL validation when implemented.
- All 9 CEO questions resolved -- no remaining ambiguities for planning phase.

## Recommendations for Planning
1. **Fix CaseResultItem first** - add `case_id: int` to both backend Pydantic model and frontend TS type. Prerequisite for all version matching work.
2. **Sync frontend TS types** - add 4 missing snapshot fields to RunListItem. Independent of comparison work, reduces tech debt.
3. **Rename URL params** - `baseRunId`/`compareRunId` with `variantRunId` accepted as fallback alias. Zod schema update + accept-both strategy.
4. **Rename labels** - "Base"/"Compare" replacing all ~194 "Baseline"/"Variant" occurrences in compare.tsx and related components.
5. **Generalize delta summary card** - remove variant-gating, use `prompt_versions` + `model_snapshot` snapshot diff for all run pairs.
6. **Rewrite META_PROMPT** - neutral comparison prompt ("analyze differences between these two runs"), not variant-specific.
7. **Client-side matching** - frontend computes matched/drifted/unmatched from two RunDetail responses. No new backend endpoint.
8. **Run picker: completed only** - filter picker to completed runs. No failed/partial.
9. **Legacy run handling** - when both `case_versions` null, treat shared `case_name` as matched. No "unknown" bucket.
10. **Aggregate toggle conditional** - only render when drifted/unmatched > 0.
11. **Defer cross-dataset** - same-dataset constraint for v1. Guard in picker/validation.
