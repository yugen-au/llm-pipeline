# Testing Results

## Summary
**Status:** passed
119 versioning-specific tests pass. 15 suite-level failures are pre-existing (confirmed via `git stash` round-trip — identical failures before and after the diff). No regressions from versioning-snapshots implementation.

## Automated Testing

### Versioning Feature Test Files
| File | Tests | Result |
| --- | --- | --- |
| tests/test_versioning_helpers.py | 24 | all passed |
| tests/test_migrations.py | 5 | all passed |
| tests/test_eval_runner.py | 11 | all passed |
| tests/prompts/test_yaml_sync.py | 27 | all passed |
| tests/evals/test_yaml_sync.py | 5 | all passed |
| tests/ui/test_evals_routes.py | 52 | all passed |

### Full Suite
**Pass Rate:** 1554/1569 (119/119 versioning tests; 15 pre-existing failures)

```
platform win32 -- Python 3.13.3, pytest-9.0.2
collected 1575 items

15 failed (pre-existing), 1554 passed, 6 skipped in 45.00s
```

### Pre-existing Failures (not caused by this branch)
Confirmed pre-existing by running identical test set on stashed branch — same 15 failures.

| Test(s) | Root Cause |
| --- | --- |
| TestStepSandbox_WithMockDocker (6) | `_discover_framework_path` removed from class; test mocks stale attr |
| TestFieldMatchEvaluator (7) | Evaluator no longer callable directly; `repr` format changed upstream |
| test_atexit_registered_with_cleanup_vite | CLI now calls `atexit.register` twice; test expects once |
| test_returns_422_when_no_model_configured | Route returns 202+background failure instead of 422 |

## Success Criteria
- [x] tests/test_versioning_helpers.py — 24 passed (Steps 1, 2, 6)
- [x] tests/test_migrations.py — 5 passed (Step 5)
- [x] tests/prompts/test_yaml_sync.py — 27 passed (Step 7)
- [x] tests/evals/test_yaml_sync.py — 5 passed (Steps 8, 10)
- [x] tests/test_eval_runner.py — 11 passed (Step 9)
- [x] tests/ui/test_evals_routes.py — 52 passed (Steps 8, 12)
- [x] Full `uv run pytest` — no new failures introduced
- [ ] Manual: UI prompt edit → new version row + YAML updated (human validation)
- [ ] Manual: eval run → EvaluationRun.prompt_versions populated (human validation)
- [ ] Manual: soft-delete + recreate cycle (human validation)
- [ ] Grep audit for missed is_latest filter sites (not run in testing session)
