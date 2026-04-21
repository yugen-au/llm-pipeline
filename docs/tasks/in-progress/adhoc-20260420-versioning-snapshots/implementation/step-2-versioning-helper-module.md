# IMPLEMENTATION - STEP 2: VERSIONING HELPER MODULE
**Status:** completed

## Summary
Created `llm_pipeline/db/versioning.py` with generic versioning helpers (`_utc_now`, `_bump_minor`, `save_new_version`, `get_latest`, `soft_delete_latest`) that mediate all version writes for any SQLModel with `is_latest`/`is_active`/`version`/`updated_at` columns. Wrote 23 tests covering all 8 required test scenarios from VALIDATED_RESEARCH 9.1.

## Files
**Created:** `llm_pipeline/db/versioning.py`
**Modified:** `tests/test_versioning_helpers.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/db/versioning.py`
New module implementing the generic versioning engine. Key functions:
- `_utc_now()` — timezone-aware UTC timestamp
- `_bump_minor(version)` — increments last segment of dotted version
- `save_new_version(session, model_cls, key_filters, new_fields, version=None)` — flips prior row's `is_latest=False`, flushes, inserts new row with `is_latest=True`
- `get_latest(session, model_cls, **filters)` — returns single active+latest row
- `soft_delete_latest(session, model_cls, **key_filters)` — sets `is_active=False`, keeps `is_latest=True`

### File: `tests/test_versioning_helpers.py`
Extended from 12 compare_versions tests to 23 total tests. Added:
- `TestBumpMinor` — edge cases (1.9->1.10, single segment, three segments, non-numeric ValueError)
- `TestSaveNewVersion` — bump+flip, managed-col guard, explicit-version validation, updated_at on soft-delete
- `TestPartialUniqueIndex` — bypasses helper to verify DB-level partial unique constraint
- `TestSoftDeleteAndRecreate` — 3 versions + soft-delete + recreate resets to 1.0; verifies 4 total rows
- `TestGetLatest` — excludes inactive and non-latest rows

## Decisions
### Flush-before-insert discipline
**Choice:** Two `session.flush()` calls in `save_new_version` — one after flipping prior, one after inserting new row
**Rationale:** SQLite checks partial unique indexes at statement boundaries; flush after flip releases the slot before INSERT claims it

### SQLite naive datetime handling in tests
**Choice:** Strip tzinfo for comparison assertions in tests
**Rationale:** SQLite returns naive datetimes even when stored with tz; helper writes tz-aware but round-trip loses it

## Verification
[x] `uv run pytest tests/test_versioning_helpers.py` — 23 passed
[x] All 8 required test scenarios from VALIDATED_RESEARCH 9.1 covered
[x] Partial unique index verified at DB level (test #2)
[x] No forbidden managed cols allowed in new_fields
[x] Helper imports `compare_versions` from `llm_pipeline.utils.versioning` (Step 1 dependency)
