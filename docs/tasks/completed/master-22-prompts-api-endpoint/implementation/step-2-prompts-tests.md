# IMPLEMENTATION - STEP 2: PROMPTS TESTS
**Status:** completed

## Summary
Created `tests/ui/test_prompts.py` with 17 tests (11 list + 6 detail) covering all specified scenarios. All 17 pass; no regressions in existing 50 tests.

## Files
**Created:** tests/ui/test_prompts.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/ui/test_prompts.py`
New test file. Defines `seeded_prompts_client` fixture seeding 3 Prompt rows (2 active for KEY_CLASSIFY, 1 inactive for KEY_EXTRACT with null required_variables). TestListPrompts covers empty DB, active default filter, category/step_name/prompt_type filters, is_active=false, required_variables fallback, pagination, combined filters, no-match. TestGetPrompt covers 404, grouped variants, prompt_type field set, single variant key, required_variables populated, fallback extraction.

## Decisions
### Import pattern for conftest helpers
**Choice:** `from tests.ui.conftest import _make_app` direct import
**Rationale:** Plan spec called for this; matches how the fixture engine is obtained to seed data before yielding TestClient.

### seeded_prompts_client as standalone fixture (not in conftest.py)
**Choice:** Fixture defined in test_prompts.py itself, not added to conftest.py
**Rationale:** Plan said "add a new seeded_prompts_client fixture" -- scope is prompts tests only. Keeping it local avoids polluting shared conftest with prompt-specific seed data.

## Verification
- [x] 17/17 new tests pass
- [x] 50/50 existing UI tests pass (runs, steps, events)
- [x] required_variables fallback: KEY_EXTRACT null stored -> [] extracted (no {var} in "Extract data.")
- [x] detail endpoint returns inactive prompt (KEY_EXTRACT) without 404
- [x] is_active=True default filters inactive rows from list
