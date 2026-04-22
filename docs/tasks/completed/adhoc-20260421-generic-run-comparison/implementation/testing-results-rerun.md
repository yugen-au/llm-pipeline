# Testing Results — Re-run (Post Review Fixes)

## Summary
**Status:** passed
Re-verification after 5 review fixes (commits 0ceffc3d, 72fa5f09, e16d48a2, 634e9d72, Step 7 via 634e9d72). One additional ESLint error found and fixed: `react-hooks/set-state-in-effect` triggered by the Step 6 `useEffect`/setState pattern. Fixed by replacing `seededFor` useState + useEffect with combined `expandedState` object updated during render. Pytest: 16 failures matching pre-existing baseline, 0 new regressions.

## Automated Testing

### Test Scripts Created
| Script | Purpose | Location |
| --- | --- | --- |
| uv run pytest | Backend regression check | tests/ |
| npx tsc --noEmit | TS type correctness | llm_pipeline/ui/frontend/ |
| npx eslint src/... | Lint errors in modified files | llm_pipeline/ui/frontend/ |

### Test Execution
**Pass Rate:** 1553/1569 backend tests (16 pre-existing failures, 0 regressions)

```
TSC: no errors (clean)
ESLint (4 modified files): 0 problems after fix
pytest: 16 failed, 1553 passed, 6 skipped
```

### Failed Tests
None related to this work. All 16 pre-existing:
- `tests/creator/test_sandbox.py` — 6 failures (Docker mock)
- `tests/test_evaluators.py` — 7 failures (FieldMatchEvaluator)
- `tests/ui/test_cli.py::TestDevModeWithFrontend::test_atexit_registered_with_cleanup_vite`
- `tests/ui/test_runs.py::TestTriggerRun::test_returns_422_when_no_model_configured`
- `tests/ui/test_websocket.py::TestLiveStream::test_live_stream_multiple_clients`

## Build Verification
- [x] `uv run pytest` — 16 pre-existing failures, 0 new regressions
- [x] `npx tsc --noEmit` — clean
- [x] `npx eslint` on all 4 modified files — clean after fix
- [x] No import errors

## Success Criteria (from PLAN.md)
- [x] Step 1: `CaseResultItem.case_id: Optional[int] = None` — backend parses, TS type `number | null`, `computeCaseBucket` handles null
- [x] Step 3: Zod transform URL rewrite comment added — no functional change, no type errors
- [x] Step 5: `aria-label` on run picker Select buttons — no type errors, ESLint clean
- [x] Step 6: setState-during-render moved from useEffect — ESLint `set-state-in-effect` resolved (fix applied this run)
- [x] Step 7: Resolved by Step 6 fix — filtered configs verified clean

## Human Validation Required
None new. Previous validation items from initial TESTING.md remain applicable.

## Issues Found

### setState-in-effect ESLint error in compare.tsx
**Severity:** medium
**Step:** Step 6
**Details:** The `useEffect` seeding expanded set called `setExpanded` + `setSeededFor`, triggering `react-hooks/set-state-in-effect` from `recommended-latest` ruleset. Fixed by combining both into `expandedState: { key: string; set: Set<string> }` updated synchronously during render, eliminating the effect. `useEffect`, `useRef` imports removed as unused. Fix committed: `ede9bc70`.

## Recommendations
1. No further automated fixes needed — all review fix commits verified clean
