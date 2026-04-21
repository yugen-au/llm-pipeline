# Research Summary

## Executive Summary

Both research documents (frontend UI + backend logic) are accurate against the current codebase. All major claims verified by reading source. Key confirmed gaps: CaseResultItem missing `case_id`, frontend TS types stale (missing 4 snapshot fields), compare button variant-gated. Two additional gaps discovered: run status filtering for picker, legacy-run version matching semantics, and aggregate toggle UX. Nine questions consolidated for CEO.

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
| (pending CEO input) | | |

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
- Q1: Rename `baseRunId`/`variantRunId` to `leftRunId`/`rightRunId`? If yes, accept old params as fallback for bookmarked URLs?
- Q2: What labels replace "Baseline"/"Variant"? Options: (a) "Run A"/"Run B", (b) "Left"/"Right", (c) "Older"/"Newer" by started_at, (d) configurable
- Q3: Delta summary card for non-variant comparisons: (a) show model_snapshot + prompt_versions diff, (b) hide entirely, (c) simplified "config diff"?
- Q4: Export META_PROMPT for non-variant comparisons: (a) neutral comparison prompt, (b) skip meta-prompt, (c) detect and branch?
- Q5: Run picker - show only completed runs or also failed/partial results?
- Q6: Cross-dataset comparison - defer? Both research docs recommend deferring.
- Q7: Client-side matching (Option A) vs backend endpoint? Both docs recommend client-side for v1. Backend endpoint only if perf becomes issue.
- Q8: Legacy runs (case_versions=null) - when BOTH runs lack case_versions, treat shared-name cases as "matched" (preserving current behavior) or show separate "unknown" bucket? Affects aggregate scoping.
- Q9: Aggregate scope toggle - always visible or only when drifted/unmatched cases > 0? When all cases match, the toggle is noise.

## Recommendations for Planning
1. **Fix CaseResultItem first** - add `case_id: int` to both backend Pydantic model and frontend TS type. Prerequisite for all version matching work.
2. **Sync frontend TS types** - add 4 missing snapshot fields to RunListItem. Independent of comparison work, reduces tech debt.
3. **Consider case_name_versions redundant dict** (backend Option C) as insurance - simpler client derivation, negligible storage cost. Not blocking but reduces frontend complexity.
4. **Defer cross-dataset** - both docs agree, significant scope expansion for marginal v1 value.
5. **Client-side matching (Option A)** for v1 - no new endpoints, minimal backend changes, frontend already handles case joining.
6. **URL param rename** - if renaming, implement accept-both strategy (check leftRunId first, fall back to baseRunId) to avoid breaking bookmarks.
7. **Run picker should filter to completed runs by default** with option to include failed - partial results comparison is confusing without clear UX.
8. **Aggregate toggle conditional** - only show when there are actually drifted or unmatched cases to avoid UI noise.
