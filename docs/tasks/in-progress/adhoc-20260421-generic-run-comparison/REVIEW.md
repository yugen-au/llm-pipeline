# Architecture Review

## Overall Assessment
**Status:** complete

The refactor is cohesive, well-scoped, and delivers on the locked architecture decisions. Backend change is minimal and correct (`case_id` propagated from ORM to Pydantic response on both `/runs` and `/runs/{run_id}` handlers). Frontend client-side version matching is implemented sensibly and guards legacy-null cases. Zod backward-compat alias via `.transform(...)` works. The rename from Baseline/Variant -> Base/Compare is consistent; residual `variant*` identifiers are all intentional (backward-compat alias, variant-name display when `variant_id != null`, shadcn `variant` prop, and React-hook names). Rules-of-hooks violations flagged during testing have been fixed: all `useMemo` calls precede early returns. Export payload and meta-prompt are comparison-neutral. Run picker flow is correct (current run -> `compareRunId`, selected -> `baseRunId`; completed-only; excludes self; sorted desc by `started_at`). A handful of medium/low-grade issues worth addressing in follow-up, but nothing blocks merge.

## Project Guidelines Compliance
**CLAUDE.md:** c:\Users\SamSG\Documents\claude-projects\llm-pipeline\.claude\CLAUDE.md

| Guideline | Status | Notes |
| --- | --- | --- |
| Pydantic v2 models | pass | `CaseResultItem` updated with `case_id: int = 0` default matches ORM row nullability guard |
| Backend uses SQLModel / SQLAlchemy 2.0 | pass | No changes to DB layer; `EvaluationCaseResult.case_id` already present |
| Never assume architecture / always ask CEO | pass | Step 6 doc explicitly records one-null-side => matched decision per CEO intent |
| TDD strict (pytest) | partial | pytest 1553 passed with 0 new regressions; no new unit tests for `computeCaseBucket` (recommended in TESTING.md but not added) |
| Front-end: no test runner configured yet | pass | Manual validation acknowledged; tsc + ESLint clean |
| Be concise; sacrifice grammar | pass | Commits follow `type(scope): desc` pattern |
| Auto-discovery pipelines convention | n/a | No pipeline code touched |

## Issues Found
### Critical
None

### High
None

### Medium
#### setState called during render
**Step:** 6
**Details:** `evals.$datasetId.compare.tsx` lines 1394-1398 calls `setExpanded(...)` and `setSeededFor(...)` directly in the function body (not in an effect or handler). React tolerates this pattern when it converges in one additional render (the `seedKey !== seededFor` gate provides that), but it is non-idiomatic, brittle (any future edit that mutates `initialExpanded` without also updating `seededFor` would loop), and not signposted by comments beyond "seed expanded set exactly once". Recommend replacing with `useEffect(() => { ... }, [seedKey])` or the `useSyncExternalStore`-style "derived state from key" pattern using a single `useState` with a `key` comparison. At minimum, add an assertion comment noting this is intentional render-phase state update.

#### JsonViewer diff-mode prop typed as non-null object but fed snapshot shape with null values
**Step:** 7
**Details:** `JsonViewerProps` discriminated union requires `before: Record<string, unknown>` (no `null`), but `baseConfig`/`compareConfig` contain `prompt_versions: null | Record<string, unknown>` and `model_snapshot: null | Record<string, unknown>`. The call site force-casts via `as unknown as Record<string, unknown>` (line 1781-1782). This compiles but: (a) the cast silences legitimate null handling at the `JsonViewer` boundary, (b) `hasSnapshotData` only guards against both sides being entirely null — partial nulls (e.g. base has data, compare does not) still rely on `DiffView` handling `{ prompt_versions: null, model_snapshot: {...} }` gracefully. Recommend narrowing the types by building `baseConfig` only from non-null fields, or broadening `JsonViewerProps.before`/`after` to accept `null` / `Record<string, unknown> | null` to reflect real input shape.

#### Backend `case_id` default of `0` is a sentinel that silently propagates to clients
**Step:** 1
**Details:** `CaseResultItem.case_id: int = 0` uses 0 as a "missing" sentinel (matching `runner.py` lines 222/237 `name_to_id.get(..., 0)`). Frontend `computeCaseBucket` lookups of `String(0)` in `case_versions` will return `undefined` -> `'unmatched'`, which is safe behavior but the contract is implicit. Recommend either: (a) type as `Optional[int] = None` and map `None` explicitly, OR (b) document the `0` sentinel in the model docstring and in the frontend `CaseResultItem.case_id` TSDoc. No TS comment currently explains why `case_id` is a plain `number` without `| null`.

#### Run picker: rows lack aria-label on Select button and row-level keyboard affordance
**Step:** 5
**Details:** In `RunPickerDialog` (runs.$runId.tsx lines 430-458), each run row renders an unlabeled `<Button>Select</Button>`. Screen readers will announce "Select button" with no run context between items. Also, rows are `<div>` with hover style but only the inner button is focusable, so keyboard users cannot activate a row by tabbing to it directly. Recommendations: add `aria-label={`Select run #${r.id} from ${started_at}`}` to the Select button, or make the entire row a `<button>` / `role="option"` inside a `role="listbox"` with arrow-key navigation. For small lists current UX is acceptable but not ideal for accessibility.

### Low
#### Zod transform drops `variantRunId` from the resolved shape — TanStack Router may rewrite URLs
**Step:** 3
**Details:** After `.transform(({ baseRunId, compareRunId, variantRunId }) => ({ baseRunId, compareRunId: compareRunId || variantRunId || 0 }))`, the search shape no longer includes `variantRunId`. TanStack Router's zod-adapter treats the transformed output as the canonical search state and will strip the unused param from the URL on subsequent navigations. Behavior is correct (backward-compat preserved on first load) but users who bookmark `?variantRunId=X` may see the URL silently rewritten. Consider documenting this in a code comment near the schema.

#### Backend default `case_id: int = 0` differs from `variant_id: Optional[int] = None` convention
**Step:** 1
**Details:** Other optional fields on the run models use `Optional[T] = None` (e.g. `variant_id`, `delta_snapshot`, `case_versions`). Using `= 0` on `CaseResultItem.case_id` is inconsistent. If it's meant to never be missing (because FK is non-null at DB level), then the default is unnecessary — it should just be `case_id: int`. If it can be 0 for orphans, that's a magic number.

#### `compareRun.variant_id`-gated variant-name fetch uses stale query when compareRun is undefined
**Step:** 4
**Details:** `useVariant(datasetId, variantIdForLookup)` at line 1292 will re-fetch whenever `compareRun?.variant_id` changes. `useVariant` presumably handles `variantId === 0` by disabling the query (confirmed in `useVariant` implementation — only enabled when `variantId > 0`). OK, but this is incidental correctness. A more explicit approach: `useVariant(datasetId, compareRun?.variant_id ?? 0)`.

#### Tooltip on disabled Compare button wraps disabled button in span — correct Radix pattern but inconsistent with no-picker-button case
**Step:** 5
**Details:** `runs.$runId.tsx` lines 272-290 wrap the disabled `<Button disabled>` in a `<span>` inside `TooltipTrigger` (required because disabled buttons don't fire pointer events). Correct. However, the non-empty-list branch doesn't wrap the enabled button in a Tooltip at all — a minor UX inconsistency (no tooltip on the enabled state). Not a bug.

#### `_caseName` param unused in `computeCaseBucket`
**Step:** 6
**Details:** Line 188: `function computeCaseBucket(_caseName: string, baseResult, compareResult, baseRun, compareRun)` — the first arg is unused (prefixed with `_` to silence ESLint). Recommend removing the parameter entirely. If retained for future expansion (e.g. name-based matching for orphaned cases), add a TODO comment.

#### "Matched only" filter: `filteredBaseStats`/`filteredCompareStats` recompute even when matchedOnly is false
**Step:** 6
**Details:** The `useMemo` at line 1521-1555 runs on every render regardless of `matchedOnly` state (it short-circuits to nulls when `!matchedOnly`, which is fine) but the dependency list includes `filteredCaseNames`, `baseByName`, `compareByName`, `baseRun`, `compareRun`. When `matchedOnly` is false these deps are still valid so no extra work happens except the early-return object allocation. Negligible performance impact. Acceptable.

## Review Checklist
[x] Architecture patterns followed (client-side matching per CEO decision; snapshot-diff over variant-gate)
[x] Code quality and maintainability (functions cohesive; types exported from evals.ts; module-level memos and handlers readable)
[x] Error handling present (`baseRunId === 0 || compareRunId === 0` early return; error state fallback on query failure; "No snapshot data" fallback)
[x] No hardcoded values (CLIPBOARD_WARNING_BYTES = 100 KB is a named const; meta-prompt is a const; no magic numbers in core logic except `case_id=0` sentinel flagged above)
[x] Project conventions followed (Pydantic v2, TanStack Query hooks, shadcn primitives, TanStack Router file-based routes)
[x] Security considerations (no user input reaches eval/dangerouslySetInnerHTML; clipboard writes size-gated; no XSS surface introduced)
[x] Properly scoped (DRY, YAGNI, no over-engineering) — YAGNI observed (no new backend endpoint, no Switch primitive added, no cross-dataset logic)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/routes/evals.py | pass | `CaseResultItem.case_id` added; populated at both list/detail handlers (lines 983-1001, 1044-1052); `RunListItem` already carries snapshot fields and list handler populates them |
| llm_pipeline/ui/frontend/src/api/evals.ts | pass | `RunListItem` + `CaseResultItem` TS types synced; `RunDetail extends RunListItem` unchanged |
| llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx | pass | Zod schema + transform correct; all hooks precede early returns; Base/Compare rename consistent; snapshot-diff replaces variant delta; export payload neutral |
| llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx | pass | Compare button always rendered (disabled + tooltip when no candidates); picker dialog filters completed-only, excludes self, sorted desc; navigation sets currentRun as `compareRunId` |

## New Issues Introduced
- Medium: setState-during-render pattern for seeding expanded set (Step 6) — works but fragile
- Medium: JsonViewer force-cast bypasses null-safety in type system (Step 7)
- Medium: `case_id=0` sentinel undocumented in both backend model and frontend type (Step 1)
- Medium: Run picker dialog lacks per-item aria-label and row-level keyboard focus (Step 5)
- Low: Unused `_caseName` parameter in `computeCaseBucket` (Step 6)
- Low: Zod schema strips `variantRunId` post-transform, causing URL rewrite on navigation (Step 3)
- Low: `case_id: int = 0` inconsistent with other `Optional[T] = None` conventions (Step 1)

## Recommendation
**Decision:** APPROVE

All success criteria from PLAN.md are met, backend tests pass (0 new regressions from 16 pre-existing failures), TypeScript is clean, ESLint is clean, and the architecture decisions locked before implementation are faithfully executed. The medium/low issues are quality-of-implementation concerns, not correctness defects — they warrant follow-up tickets but do not block this merge. The setState-during-render and JsonViewer-cast patterns should be cleaned up in a follow-up pass, and the accessibility gaps on the run picker should be addressed before the picker is used on larger datasets. Unit tests for `computeCaseBucket` (flagged as a recommendation in TESTING.md) are the single most valuable next step to lock in the matching semantics.
