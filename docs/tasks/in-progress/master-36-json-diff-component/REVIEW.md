# Architecture Review

## Overall Assessment
**Status:** complete

Solid implementation. Backend fix aligns event and DB semantics. JsonDiff component is well-structured with correct memoization, clean recursive tree construction, and proper dual-theme color patterns. One medium-severity bug in the tree algorithm for array-valued nested objects. All other findings are low severity.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Named function exports (no default) | pass | `JsonDiff`, `ContextEvolution`, `StepDetailPanel` all named exports |
| Props interfaces inline above component | pass | `JsonDiffProps`, `DiffNodeProps` defined inline |
| 4-state pattern (loading/error/empty/content) | pass | ContextEvolution preserves all 4 states; JsonDiff has empty diff state |
| `cn()` from `@/lib/utils` for conditional classes | pass | Used in DiffNode leaf rendering |
| Pydantic/SQLModel backend conventions | pass | No schema changes; `dict(self._context)` is a plain dict compatible with JSON column |
| Test coverage present | pass | 6 vitest tests for ContextEvolution covering all states |
| No hardcoded values | pass | `maxDepth` parameterized with default; colors in named constant |
| Error handling present | pass | `formatValue` has try/catch for JSON.stringify; `formatJson` retained for other tabs |

## Issues Found
### Critical
None

### High
None

### Medium
#### Array index type mismatch in buildDiffTree recursion
**Step:** 3
**Details:** `changedKeys` is typed `Set<string | number>` and populated from `d.path[0]` which microdiff returns as `number` for array indices. The unchanged-key loop at line 99-104 uses `Object.keys(after)` which always returns strings. When `buildDiffTree` recurses into an array-valued property (e.g. `tags: ['a', 'b']`), microdiff emits paths like `[0]`, `[1]` as numbers but `Object.keys(array-cast-to-Record)` returns `"0"`, `"1"`. The `changedKeys.has(key)` check fails because `Set.has(0)` does not match `"0"`, causing changed array elements to also appear as "unchanged" duplicates. Fix: normalize `changedKeys` to store `String(key)` consistently, i.e. change `changedKeys.add(key)` to `changedKeys.add(String(key))` at line 60. In practice the current pipeline context data is predominantly flat key-value (strings, numbers, booleans) so this rarely triggers, but it will surface if any context key holds an array or nested object that gets diffed at depth > 1.

### Low
#### formatJson helper retained but partially dead
**Step:** 5
**Details:** `formatJson` was previously used in ContextDiffTab's side-by-side pre blocks. After replacement with JsonDiff, it is no longer used there. However it IS still used in InputTab (line 100), ResponseTab (line 172), and ExtractionsTab (line 304), so removal would be wrong. The implementation correctly retained it. No action needed; noting for documentation completeness.

#### useState initializer for expanded paths does not re-sync on prop changes
**Step:** 3
**Details:** `expanded` state is initialized via `useState(() => collectPaths(tree, ...))` which only runs on mount. If `before`/`after` props change without unmounting (e.g., during a live run where context grows incrementally), newly added branch nodes at depth < maxDepth won't auto-expand. The implementation note correctly states components are keyed/remounted on step change, so this only affects the edge case of a single step's context growing during an active run. Impact is purely cosmetic (new branches start collapsed). Not worth adding a `useEffect` sync given the trade-off of re-render complexity vs. marginal UX gain.

#### Backend test fixture asserts specific context_snapshot shape
**Step:** 1
**Details:** `tests/ui/conftest.py` line 111 seeds `context_snapshot={"k": "v"}` directly in the DB fixture, and `tests/ui/test_steps.py` line 41 asserts `context_snapshot == {"k": "v"}`. These tests pass because the fixture inserts data directly (bypasses `_save_step_state`), so the backend change does not break them. However, this means the accumulated-context behavior is not integration-tested via the API. Existing event lifecycle tests in `tests/events/test_step_lifecycle_events.py` test event emission but not the DB-persisted `context_snapshot` shape. Consider adding an integration test that verifies `_save_step_state` persists accumulated context.

#### Test assertions use lower-bound counts rather than exact values
**Step:** 6
**Details:** Tests use `>= 2` and `>= 4` for addition marker counts. This is intentionally loose per the implementation notes (resilient to ordering/formatting changes), but it means tests won't catch regressions where fewer additions are rendered than expected. Acceptable trade-off for a UI component test.

## Review Checklist
[x] Architecture patterns followed -- JsonDiff at `src/components/` for cross-domain reuse is correct; used by both `runs/ContextEvolution` and `runs/StepDetailPanel`
[x] Code quality and maintainability -- clean separation between tree construction (`buildDiffTree`), rendering (`DiffNode` memo), and orchestration (`JsonDiff`); helper functions extracted
[x] Error handling present -- `formatValue` catches JSON.stringify failures; empty diff renders graceful message
[x] No hardcoded values -- colors in `diffColors` constant, `maxDepth` parameterized
[x] Project conventions followed -- named exports, inline props interfaces, `cn()` usage, dual-theme color classes matching StatusBadge/StepTimeline patterns
[x] Security considerations -- no user input rendered as HTML; all values go through `formatValue`/`String()` text content
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- single component serves both integration points; no unnecessary abstractions; microdiff at 0.5KB is minimal dependency

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| `llm_pipeline/pipeline.py` (line 946) | pass | One-line change aligns DB storage with event semantics at line 381; `result_data` unchanged |
| `llm_pipeline/ui/frontend/src/components/JsonDiff.tsx` | pass (with medium issue) | Well-structured; array index type mismatch in recursion (medium) |
| `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.tsx` | pass | Clean integration; prev snapshot computed inline; first step gets `before={}` |
| `llm_pipeline/ui/frontend/src/components/runs/StepDetailPanel.tsx` | pass | ContextDiffTab updated; new_keys badges retained; formatJson correctly kept for other tabs |
| `llm_pipeline/ui/frontend/src/components/runs/ContextEvolution.test.tsx` | pass | 6 tests covering all states; diff-aware assertions replace raw JSON checks |
| `llm_pipeline/ui/frontend/package.json` | pass | `microdiff@^1.5.0` in dependencies (not devDependencies); zero peer-dep issues |

## New Issues Introduced
- Array index type mismatch in `buildDiffTree` recursion (medium) -- duplicate unchanged entries when diffing array-valued context keys at depth > 1
- No backend integration test for accumulated `context_snapshot` shape after the `pipeline.py` fix

## Recommendation
**Decision:** CONDITIONAL
Approve after fixing the medium-severity array index type mismatch. One-line fix: change `changedKeys.add(key)` to `changedKeys.add(String(key))` at `JsonDiff.tsx` line 60. All other findings are low severity and acceptable as-is or as future improvements.
