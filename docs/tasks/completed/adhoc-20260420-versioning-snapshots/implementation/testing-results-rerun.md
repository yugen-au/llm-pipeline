# Testing Results — Post-Review-Fix Rerun

## Summary
**Status:** passed
No regressions introduced by the two review fixes. Identical failure set to prior run (15 pre-existing, 0 new).

## Automated Testing

### Test Execution
**Pass Rate:** 1554/1569 (15 pre-existing failures, unchanged)

```
platform win32 -- Python 3.13.3, pytest-9.0.2
collected 1575 items

15 failed, 1554 passed, 6 skipped, 5 warnings in 44.85s
```

### Failed Tests
All 15 failures are pre-existing and unrelated to this branch (confirmed in prior run via `git stash` round-trip).

| Test(s) | Count | Pre-existing cause |
| --- | --- | --- |
| tests/creator/test_sandbox.py::TestStepSandbox_WithMockDocker | 6 | stale mock attr `_discover_framework_path` |
| tests/test_evaluators.py::TestFieldMatchEvaluator | 7 | evaluator no longer directly callable; repr format changed |
| tests/ui/test_cli.py::TestDevModeWithFrontend::test_atexit_registered_with_cleanup_vite | 1 | CLI now calls `atexit.register` twice; test expects once |
| tests/ui/test_runs.py::TestTriggerRun::test_returns_422_when_no_model_configured | 1 | route returns 202 + background failure instead of 422 |

## Fixes Verified (commits 61063bbc, 89eab9da)

| Fix | File | Tests exercising it |
| --- | --- | --- |
| Case rename 409 guard | llm_pipeline/ui/routes/evals.py | tests/ui/test_evals_routes.py (52 passed) |
| is_active filter in runner | llm_pipeline/evals/runner.py | tests/test_eval_runner.py (11 passed) |

## Build Verification
- [x] `uv run pytest` completes without import errors or collection errors
- [x] 1554 tests pass (same as pre-fix baseline)
- [x] 0 new failures introduced

## Success Criteria
- [x] No new failures vs prior run (15 pre-existing == 15 current)
- [x] evals routes tests all pass (52/52)
- [x] eval runner tests all pass (11/11)
- [x] versioning helper/migration/yaml-sync tests all pass

## Issues Found
None

## Recommendations
1. Pre-existing failures (sandbox, evaluators, CLI atexit, runs 422) should be tracked separately as tech debt — none are related to this feature branch.
