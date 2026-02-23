# Architecture Review

## Overall Assessment
**Status:** complete
Implementation delivers all 5 planned integration gaps (E2E trigger+WS, error handling, combined filters, CORS headers, WS disconnect cleanup) as 19 passing tests in a single new file. No source files modified. Code follows established conftest patterns closely. The E2E threading approach with a gate event is a pragmatic solution to the WS-concurrency challenge. Minor style and duplication issues identified but nothing blocking.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Tests pass | pass | 19/19 pass, verified via `pytest tests/ui/test_integration.py` |
| No hardcoded values | pass | UUIDs match conftest seed constants; no magic strings beyond those |
| Error handling present | pass | Tests verify error paths (failing pipeline, disconnect cleanup) |
| No source file changes under llm_pipeline/ | pass | `git diff dev -- llm_pipeline/ --stat` returns empty |
| pytest runner + conventions | pass | Class-based tests, fixtures, same import style as sibling files |

## Issues Found
### Critical
None

### High
None

### Medium
#### Significant code duplication across E2E test methods
**Step:** 1
**Details:** `test_trigger_then_ws_receives_pipeline_started`, `test_trigger_then_ws_receives_pipeline_completed`, and `test_trigger_ws_stream_complete_sent_on_finish` share ~25 lines of identical setup/orchestration code (POST, wait for row, collect events, emit via UIBridge, wait for done, set gate). A shared helper method like `_trigger_and_collect(self)` returning `(run_id, received)` would reduce the 3 methods to ~5 lines each and make future maintenance easier. Not a functional issue but a maintainability concern given the boilerplate-to-assertion ratio.

#### _make_emitting_pipeline_factory() defined but unused
**Step:** 1
**Details:** The module defines `_make_emitting_pipeline_factory()` (lines 66-120) but no test class uses it. The E2E tests switched to `_make_no_op_factory()` + manual UIBridge emission to avoid timing races, which is correct -- but the unused factory is dead code and should be removed to avoid confusion.

### Low
#### Inline import of UIBridge inside test methods
**Step:** 1
**Details:** `from llm_pipeline.ui.bridge import UIBridge` appears as a local import inside each of the 3 `TestE2ETriggerWebSocket` test methods instead of at module level. While harmless, it deviates from the module-level import convention used by every other test file in `tests/ui/`. Moving it to the top-level imports section would be more consistent.

#### Inline import of timedelta
**Step:** 1
**Details:** `from datetime import timedelta` is imported inline inside `test_runs_filter_pipeline_name_and_started_after` and `test_runs_filter_pipeline_name_and_started_after_no_match`. `timedelta` is already available from the module-level `from datetime import datetime, timezone` line -- just needs adding to that import tuple.

#### _test_gate monkey-patching on engine object
**Step:** 1
**Details:** `app.state.engine._test_gate = gate` (line 211) attaches a test-only attribute directly to the SQLAlchemy Engine instance. This works but is fragile -- a SQLAlchemy upgrade could freeze engine attributes. An alternative would be storing the gate in `app.state` (e.g., `app.state._test_gate`) and reading it from the factory via the engine's parent app. Low risk given this is test-only code.

## Review Checklist
[x] Architecture patterns followed - uses _make_app() + StaticPool pattern, class-based test organization, same fixture conventions as sibling files
[x] Code quality and maintainability - generally good; medium-severity duplication in E2E class
[x] Error handling present - tests cover both happy and error paths (GAP 3 failure flow, GAP 5 disconnect)
[x] No hardcoded values - seed UUIDs defined as module constants matching conftest
[x] Project conventions followed - starlette.testclient, autouse _clean_manager, _wait_for_connection helper
[x] Security considerations - N/A (test file only, no production code)
[x] Properly scoped (DRY, YAGNI, no over-engineering) - mostly; dead code (_make_emitting_pipeline_factory) and E2E duplication noted

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| tests/ui/test_integration.py | pass | 19 tests, all passing, covers all 5 planned gaps |
| tests/ui/conftest.py | pass | Reference file; _make_app() and seeded_app_client correctly reused |
| tests/ui/test_runs.py | pass | Reference file; patterns consistent with new tests |
| tests/ui/test_websocket.py | pass | Reference file; _clean_manager and _wait_for_connection patterns correctly replicated |
| tests/ui/test_events.py | pass | Reference file; filter/pagination patterns consistent |
| llm_pipeline/ui/bridge.py | pass | Source verified; UIBridge.emit() and complete() behavior matches test assumptions |
| llm_pipeline/ui/routes/runs.py | pass | Source verified; trigger_run error handling matches GAP 3 test expectations |
| llm_pipeline/ui/routes/websocket.py | pass | Source verified; ConnectionManager.disconnect() cleanup matches GAP 5 test expectations |

## New Issues Introduced
- Dead code: `_make_emitting_pipeline_factory()` is defined but never called (medium)
- None detected beyond items listed in Issues Found above

## Recommendation
**Decision:** CONDITIONAL
Approve after removing `_make_emitting_pipeline_factory()` (dead code). The E2E duplication and inline imports are style nits that can be addressed optionally. All tests pass and cover the intended gaps correctly.
