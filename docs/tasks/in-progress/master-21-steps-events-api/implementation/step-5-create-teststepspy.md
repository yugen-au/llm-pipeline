# IMPLEMENTATION - STEP 5: CREATE TEST_STEPS.PY
**Status:** completed

## Summary
Created comprehensive test suite for steps list/detail and context evolution endpoints with 14 tests across 3 classes.

## Files
**Created:** tests/ui/test_steps.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/ui/test_steps.py`
New file with 3 test classes:
- `TestListSteps` (5 tests): 200 with items, ordering, field presence, empty list, 404
- `TestGetStep` (4 tests): 200 with full detail, all fields, 404 step, 404 run
- `TestContextEvolution` (5 tests): 200 with snapshots, ordering, fields, empty, 404

All tests use `seeded_app_client` fixture. Constants match test_runs.py plus NONEXISTENT sentinel.

## Decisions
None

## Verification
[x] 14/14 tests pass in test_steps.py
[x] 41/41 tests pass in full tests/ui/ suite (no regressions)
[x] Follows test_runs.py patterns (class-based, assert status + body)

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] LOW: Remove unused `import pytest` line
[x] IMPORTANT: `TestGetStep::test_returns_404_for_nonexistent_run` now asserts detail message is "Run not found"

### Changes Made
#### File: `tests/ui/test_steps.py`
Removed unused import, added detail assertion on 404.
```
# Before
import pytest
...
    def test_returns_404_for_nonexistent_run(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{NONEXISTENT}/steps/1")
        assert resp.status_code == 404

# After
(no import pytest)
...
    def test_returns_404_for_nonexistent_run(self, seeded_app_client):
        resp = seeded_app_client.get(f"/api/runs/{NONEXISTENT}/steps/1")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "Run not found"
```

### Verification
[x] 14/14 tests pass in test_steps.py
[x] No regressions
