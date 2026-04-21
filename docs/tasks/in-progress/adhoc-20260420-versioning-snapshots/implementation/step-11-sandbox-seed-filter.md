# IMPLEMENTATION - STEP 11: SANDBOX SEED FILTER
**Status:** completed

## Summary
Verified sandbox.py already has correct `is_latest==True AND is_active==True` seed query filter and `is_latest` copy-through (landed in Steps 6 and 7). Added missing test `test_sandbox_seed_filters_is_latest_is_active` (#11).

## Files
**Created:** none
**Modified:** tests/test_versioning_helpers.py
**Deleted:** none

## Changes
### File: `tests/test_versioning_helpers.py`
Added `TestSandboxSeedFilters` class with `test_sandbox_seed_filters_is_latest_is_active` — seeds prod DB with 3 prompt rows (active+latest, active+non-latest, inactive+latest) and asserts sandbox engine receives only the active+latest row.

## Decisions
### No code changes to sandbox.py
**Choice:** No modifications needed
**Rationale:** Steps 6 and 7 already implemented both the read filter (line 54-55: `Prompt.is_active == True, Prompt.is_latest == True`) and write-side copy-through (line 72: `is_latest=prompt.is_latest`). This step only needed the test.

## Verification
[x] sandbox.py seed query filters on `is_active==True AND is_latest==True`
[x] sandbox.py copy-through includes `is_latest=prompt.is_latest`
[x] test_sandbox_seed_filters_is_latest_is_active passes
[x] no duplicate test exists elsewhere
