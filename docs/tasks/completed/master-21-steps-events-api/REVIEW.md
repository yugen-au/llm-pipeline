# Architecture Review

## Overall Assessment
**Status:** complete
Clean, well-structured implementation that closely follows existing `runs.py` patterns. All 54 UI tests pass (27 new + 27 existing, zero regressions). Endpoints are read-only via `DBSession` (ReadOnlySession wrapper), use sync `def`, plain `BaseModel` responses, and `List[T]` style. Architecture decisions from PLAN.md were followed faithfully. No critical or high issues found.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | Uses typing.List/Optional for consistency with runs.py; no 3.11-only features |
| Pydantic v2 | pass | All response models use pydantic.BaseModel |
| SQLModel / SQLAlchemy 2.0 | pass | sqlmodel.select, sqlalchemy.func used correctly |
| Pipeline + Strategy + Step pattern | pass | No changes to core architecture |
| ReadOnlySession for DB reads | pass | All endpoints use DBSession (ReadOnlySession wrapper) |
| Tests with pytest | pass | 27 new tests, all passing |
| No hardcoded values | pass | All constants (UUIDs, limits) are test-scoped or configurable via Query params |

## Issues Found
### Critical
None

### High
None

### Medium
#### `get_step` returns generic 404 for both missing run and missing step
**Step:** 1
**Details:** `get_step` uses a single query on `PipelineStepState` by `(run_id, step_number)`. If the run does not exist, the 404 message says "Step not found" rather than "Run not found". This is functionally correct (the plan explicitly chose single-query for performance) but the test `test_returns_404_for_nonexistent_run` in `TestGetStep` passes only because it checks `status_code == 404`, not the detail message. If a consumer depends on the detail text to distinguish "run missing" from "step missing", this would be a problem. Acceptable per plan rationale but worth noting.

### Low
#### Unused import `pytest` in test_steps.py
**Step:** 5
**Details:** `test_steps.py` line 2 imports `pytest` but no test uses `pytest.raises`, `pytest.mark`, or any other pytest API. Harmless but unnecessary.

#### `_get_run_or_404` docstring inconsistency
**Step:** 1, 3
**Details:** The `_get_run_or_404` helper in `steps.py` has a docstring (`"""Return run or raise 404."""`) while the identical function in `events.py` has none. Minor inconsistency; both work correctly.

#### Event seed data uses `_utc()` with hardcoded offsets creating time-sensitive ordering assumptions
**Step:** 4
**Details:** Seed events use `_utc(-298)`, `_utc(-297)`, etc. which compute timestamps relative to `datetime.now()`. This is the same pattern used by existing run/step seeds so it's consistent, but it creates implicit coupling between seed data ordering and wall-clock time. Not a real risk at this scale.

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/routes/steps.py | pass | 3 response models, 1 helper, 2 endpoints; matches runs.py patterns |
| llm_pipeline/ui/routes/runs.py | pass | 2 new models + 1 endpoint appended; no existing code modified |
| llm_pipeline/ui/routes/events.py | pass | Full rewrite of stub; pagination, filtering, count query all correct |
| tests/ui/conftest.py | pass | 4 event seed rows in separate session block; consistent with existing pattern |
| tests/ui/test_steps.py | pass | 14 tests across 3 classes; comprehensive coverage |
| tests/ui/test_events.py | pass | 13 tests; pagination, filtering, validation boundary tests |
| llm_pipeline/ui/app.py | pass | Unchanged; routers were already registered |
| llm_pipeline/ui/deps.py | pass | Unchanged; DBSession dependency used correctly |
| llm_pipeline/state.py | pass | Unchanged; PipelineStepState/PipelineRun models referenced correctly |
| llm_pipeline/events/models.py | pass | Unchanged; PipelineEventRecord imported and queried correctly |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE
Implementation is clean, consistent with existing patterns, well-tested, and follows all architecture decisions from PLAN.md. The medium-severity item (generic 404 in step detail) is an intentional tradeoff documented in the plan. No changes required.

---

# Architecture Re-Review (Post-Fix)

## Overall Assessment
**Status:** complete
All 4 issues from the initial review have been resolved. 54/54 tests pass. No new issues introduced by the fixes.

## Fix Verification

### MEDIUM (resolved): `get_step` now validates run first
**Step:** 1
**Before:** Single query on `PipelineStepState` -- missing run returned "Step not found".
**After:** `get_step` (line 95) now calls `_get_run_or_404(db, run_id)` before the step query. Missing run returns "Run not found", missing step returns "Step not found". Test `test_returns_404_for_nonexistent_run` (line 63) now asserts `detail == "Run not found"`.

### LOW (resolved): Unused `pytest` import removed from test_steps.py
**Step:** 5
**Before:** `import pytest` on line 2, unused.
**After:** Import removed. File starts with docstring then constants.

### LOW (resolved): `_get_run_or_404` docstring now consistent
**Step:** 1, 3
**Before:** `steps.py` had docstring `"""Return run or raise 404."""`, `events.py` had none.
**After:** Both files have identical docstring `"""Return run or raise 404."""` (steps.py line 53, events.py line 53).

### LOW (acknowledged): Seed data `_utc()` pattern unchanged
**Step:** 4
**Status:** Accepted as-is per initial review. Consistent with existing conftest.py pattern. No fix needed.

## Issues Found
### Critical
None

### High
None

### Medium
None

### Low
None

## Review Checklist
[x] Architecture patterns followed
[x] Code quality and maintainability
[x] Error handling present
[x] No hardcoded values
[x] Project conventions followed
[x] Security considerations
[x] Properly scoped (DRY, YAGNI, no over-engineering)

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/ui/routes/steps.py | pass | `get_step` now calls `_get_run_or_404` before step query |
| llm_pipeline/ui/routes/events.py | pass | `_get_run_or_404` docstring added |
| tests/ui/test_steps.py | pass | Unused import removed; 404 detail assertion added |
| tests/ui/test_events.py | pass | No changes needed; re-verified |

## New Issues Introduced
- None detected

## Recommendation
**Decision:** APPROVE
All previous issues resolved. Implementation is clean, all 54 tests pass, no regressions.
