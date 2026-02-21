# Architecture Review

## Overall Assessment
**Status:** complete
Clean, minimal implementation. Both steps match the plan exactly. pyproject.toml changes are correct PEP 621. Import guard is well-placed at the single dispatch point. No regressions introduced.

## Project Guidelines Compliance
**CLAUDE.md:** D:\Documents\claude-projects\llm-pipeline\CLAUDE.md
| Guideline | Status | Notes |
| --- | --- | --- |
| Tests pass | pass | 675 passed; 1 pre-existing failure (test_events_router_prefix) unrelated |
| Warnings fixed | pass | No new warnings introduced |
| No hardcoded values | pass | Error message string is the only literal, appropriate for user-facing output |
| Error handling present | pass | ImportError caught with friendly stderr message + sys.exit(1) |
| Commit format | pass | Commits use type(scope): description pattern |

## Issues Found
### Critical
None

### High
None

### Medium
#### Broad ImportError catch may mask application bugs
**Step:** 2
**Details:** The bare `except ImportError` in `_run_ui()` catches any ImportError raised during the entire execution of `_run_dev_mode` / `_run_prod_mode` call trees, not just missing `fastapi`/`uvicorn` imports. If application code (e.g. `create_app`, a router module, or a user's pipeline code) raises an ImportError for an unrelated reason, the user sees "UI dependencies not installed" instead of the real traceback. The PLAN.md acknowledges this risk and deems it acceptable. Given the current codebase size this is fine, but as the app grows it could mask real bugs. A targeted guard (checking `e.name` against known packages) would be more precise. Flagging as medium since the plan explicitly accepted this trade-off.

#### No test for the CLI import guard path
**Step:** 2
**Details:** The implementation doc claims "Import guard test passes (test_ui.py::test_missing_ui_deps or similar)" but no such test exists in `tests/ui/test_cli.py` or `tests/test_ui.py`. The existing `TestImportGuard` class in `test_ui.py` tests `llm_pipeline/ui/__init__.py`'s guard, not the `_run_ui()` try/except. The new code path (stderr message + sys.exit(1) on ImportError) is untested. This is a gap -- a test that patches `create_app` to raise ImportError and asserts the exit code and stderr message would be trivial and valuable.

### Low
#### Test assertions use loose version checks
**Step:** 1
**Details:** `TestPyprojectToml.test_ui_group_contains_fastapi` asserts `any("fastapi" in dep for dep in ui_deps)` without checking the version bound. The version was bumped from `>=0.100` to `>=0.115.0` but existing tests would pass with either. Not a blocker since the actual pyproject.toml is correct, but pinned-version assertions would catch regressions.

## Review Checklist
[x] Architecture patterns followed -- deferred imports, single dispatch point guard
[x] Code quality and maintainability -- minimal diff, clear error message
[x] Error handling present -- ImportError -> stderr + exit(1)
[x] No hardcoded values -- user-facing string is appropriate
[x] Project conventions followed -- commit format, file structure, CLAUDE.md guidelines
[x] Security considerations -- no new attack surface; `0.0.0.0` bind in prod existed before this change
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- no unnecessary abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| pyproject.toml | pass | [project.scripts], [ui], [dev] all correct per plan |
| llm_pipeline/ui/cli.py | pass | Import guard correctly placed at _run_ui entry |
| tests/test_ui.py | pass | Existing tests pass; no new tests for CLI guard (noted above) |
| tests/ui/test_cli.py | pass | Existing CLI tests unaffected by change |

## New Issues Introduced
- None detected beyond the medium-severity items noted above

## Recommendation
**Decision:** APPROVE
Both changes are correct, minimal, and match the plan. The broad ImportError catch is an acknowledged trade-off documented in PLAN.md. The missing CLI guard test is a gap but not blocking given the simplicity of the code path. Recommend adding a test in a follow-up.
