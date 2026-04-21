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

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] Sandbox variant prompt queries omit is_active filter in _apply_variant_to_sandbox

### Changes Made
#### File: `llm_pipeline/evals/runner.py`
Added `Prompt.is_active == True` filter to both prompt queries in `_apply_variant_to_sandbox` (system and user lookups) for defense-in-depth consistency.

```
# Before (line ~839)
select(Prompt).where(
    Prompt.prompt_key == system_key,
    Prompt.prompt_type == "system",
    Prompt.is_latest == True,
)

# After
select(Prompt).where(
    Prompt.prompt_key == system_key,
    Prompt.prompt_type == "system",
    Prompt.is_active == True,
    Prompt.is_latest == True,
)
```

Same pattern applied to user prompt query (~line 868).

### Verification
[x] All 4 prompt queries in runner.py now filter on both is_active and is_latest
[x] Pattern matches existing queries at lines 684-685 and 766-767
