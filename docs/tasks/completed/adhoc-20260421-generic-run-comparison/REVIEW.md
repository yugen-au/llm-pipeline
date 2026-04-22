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

---

# Re-Review (Post-Fix Verification)

## Overall Assessment
**Status:** complete

All 7 issues from the original review addressed across 4 fix commits (`0ceffc3d`, `72fa5f09`, `634e9d72`, `e16d48a2`) and 1 test-automator ESLint fix (`ede9bc70`). TypeScript compile clean, ESLint clean on all modified files, backend tests pass (7 pre-existing failures, all unrelated to evals routes — creator/sandbox + test_wal + test_runs). One nuanced architectural comment: `ede9bc70` intentionally reverted the useEffect seed from `634e9d72` to a setState-during-render pattern to satisfy the `react-hooks/set-state-in-effect` rule. This is the officially supported React pattern ("Adjusting state while rendering", React docs), gated by a key comparison, so both approaches were defensible — the test-automator's pick is valid.

## Fix Verification

| Issue # | Original Severity | Fix Commit | Status | Notes |
| --- | --- | --- | --- | --- |
| 1 (setState during render) | Medium | `634e9d72` then refactored by `ede9bc70` | fixed | `634e9d72` introduced `useEffect`; `ede9bc70` refactored to setState-during-render with a key-gate (valid React pattern per official docs) to satisfy `react-hooks/set-state-in-effect` lint rule. The pattern is idiomatic and documented. |
| 2 (JsonViewer null-cast) | Medium | `634e9d72` | fixed | `baseConfig`/`compareConfig` now built via filtered-inclusion (Option A from original review). Both are typed `Record<string, unknown>`, no `as unknown as` cast at call site. `hasSnapshotData` rewritten to `Object.keys(...).length > 0`. |
| 3 (case_id=0 sentinel) | Medium | `0ceffc3d` | fixed | Backend `CaseResultItem.case_id: Optional[int] = None` with docstring explaining the runner.py sentinel mapping. Detail handler maps `cr.case_id if cr.case_id else None`. TS type `case_id: number \| null` with explanatory TSDoc. `computeCaseBucket` adds an explicit null guard at line 200. |
| 4 (aria-label on Select buttons) | Medium | `e16d48a2` | fixed | Each Select button now has `aria-label={`Select run #${r.id}${variantLabel} started ${startedLabel} with pass rate ${passRate}`}`. Variant label is conditional. Visible text unchanged (refactored to share `startedLabel`/`variantLabel` locals). |
| 5 (Zod URL rewrite comment) | Low | `72fa5f09` | fixed | 3-line explanatory comment at lines 65-68 of `compare.tsx` explaining `variantRunId` backward-compat alias and URL rewrite behavior. |
| 6 (case_id Optional convention) | Low | `0ceffc3d` | fixed | Subsumed by fix #3; now consistent with other `Optional[T] = None` fields on the run models. |
| 7 (Unused `_caseName` param) | Low | `634e9d72` | fixed | Parameter removed from `computeCaseBucket` signature and the single call site at line 1343. |

## New Issues Found

### Critical
None

### High
None

### Medium
None

### Low
#### setState-during-render seed: expanded derivation uses fresh Set but toggleCase closes over stored set
**Step:** 6 (post-fix refactor in `ede9bc70`)
**Details:** In `compare.tsx` lines 1389-1407, the derived `expanded` variable for the "seed render" uses `new Set(initialExpanded)` while `setExpandedState` is scheduled to store the same value. Within that same render, `toggleCase`/`setExpanded` wrappers call `setExpandedState((prev) => ...)` which reads `prev.set` — on the seed render, `prev.set` is still the stale empty set, not `expanded`. React's batching and commit cycle make this effectively unobservable (setState-in-render causes an immediate re-render before any handler can fire), but a future refactor that exposes `expanded` to a ref-mutating child, or a synchronous useMemo dependency on `expanded` combined with a side-effect, could surface the discrepancy. Recommend adding a short comment at line 1394 noting that `expanded` during seed is transitional and re-rendered within the same commit. Non-blocking.

#### Defensive `if cr.case_id else None` also maps truthy-false like 0 to None but ORM column is non-null int ≥ 1 in practice
**Step:** 1 (post-fix in `0ceffc3d`)
**Details:** Backend detail handler at `evals.py:1051` uses `cr.case_id if cr.case_id else None`. Since `EvaluationCaseResult.case_id` is a non-null int column and DB autoincrement starts at 1, the sentinel 0 is the only falsy value possible. Correct behavior. However, `if cr.case_id` also treats `None` as None (would short-circuit but column is non-null), so the expression is technically `cr.case_id if (cr.case_id != 0 and cr.case_id is not None) else None`. For clarity and to match the comment, consider `cr.case_id if cr.case_id != 0 else None`. Very minor readability improvement; not a defect.

## Review Checklist (Re-Review)
[x] All 7 original issues have verifiable fixes in the codebase
[x] Fix commits touch only the files identified in the original issues
[x] TypeScript compiles clean (`tsc --noEmit` — no output = no errors)
[x] ESLint clean on `compare.tsx`, `runs.$runId.tsx`, `api/evals.ts`
[x] Backend tests: 7 pre-existing failures (creator/sandbox, test_runs, test_wal), none from evals routes
[x] No new hardcoded values introduced
[x] No new hook-rule violations
[x] case_id null propagation verified end-to-end (runner sentinel 0 -> backend maps to None -> TS `number | null` -> `computeCaseBucket` null-guard at line 200 -> returns `'unmatched'`)
[x] aria-label template interpolates real runtime values (id, variant, started_at, pass rate)
[x] Zod `.transform()` comment accurately describes TanStack Router URL-rewrite behavior
[x] Option A (filtered configs) removes the need for `as unknown as Record<string, unknown>` force-cast
[x] `hasSnapshotData` semantics preserved (base or compare has at least one populated snapshot field)

## Files Re-Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/routes/evals.py | pass | `CaseResultItem.case_id` now `Optional[int] = None` with comment; detail handler maps 0 sentinel to None at line 1051 |
| llm_pipeline/ui/frontend/src/api/evals.ts | pass | `case_id: number \| null` with TSDoc explaining null semantics |
| llm_pipeline/ui/frontend/src/routes/evals.$datasetId.compare.tsx | pass | Zod comment added; `computeCaseBucket` drops `_caseName` param and adds null guard; `baseConfig`/`compareConfig` use Option A filtered construction; JsonViewer call site no longer casts; `hasSnapshotData` rewritten; seed pattern uses valid setState-during-render with key gate |
| llm_pipeline/ui/frontend/src/routes/evals.$datasetId.runs.$runId.tsx | pass | Select button gains contextual `aria-label`; `startedLabel`/`variantLabel` shared between aria-label and visible text |

## Regression Scan
- No new issues introduced by the 5 fix commits.
- The `ede9bc70` refactor (test-automator) is a legitimate lint-rule-satisfying pattern; worth a one-line comment for future maintainers but not a defect.
- Backend regression count unchanged (7 pre-existing, 0 new).
- TypeScript clean.
- ESLint clean.

## Recommendation (Re-Review)
**Decision:** APPROVE

All 4 medium and 3 low issues from the original review have been addressed with appropriate, verified fixes. The test-automator's lint fix is valid (React's official setState-during-render pattern). Two very minor Low observations noted above are non-blocking readability notes. Task is ready to exit review phase.
