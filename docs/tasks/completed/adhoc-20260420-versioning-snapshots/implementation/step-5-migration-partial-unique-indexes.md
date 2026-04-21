# IMPLEMENTATION - STEP 5: MIGRATION + PARTIAL UNIQUE INDEXES
**Status:** completed

## Summary
Extended `_MIGRATIONS` with 9 new column entries for versioning/snapshot columns, added `_migrate_partial_unique_indexes(engine)` function that drops legacy indexes, dedupes eval_cases duplicate rows, and creates partial unique indexes. Wired into `init_pipeline_db` between `_migrate_add_columns` and `add_missing_indexes`.

## Files
**Created:** `tests/test_migrations.py`
**Modified:** `llm_pipeline/db/__init__.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/db/__init__.py`
Added 9 entries to `_MIGRATIONS` list for versioning columns (prompts.is_latest, eval_cases.version/is_active/is_latest/updated_at, eval_runs snapshot columns). Added `_migrate_partial_unique_indexes(engine)` function implementing legacy index drops, eval_cases dedupe via ROW_NUMBER window function, and partial unique + supporting index creation. Wired call into `init_pipeline_db`.

### File: `tests/test_migrations.py`
Tests #19, #20, #21 from VALIDATED_RESEARCH section 9.6:
- `test_dedupe_keeps_newest_by_created_at` — verifies newest row keeps is_latest=1
- `test_dedupe_tiebreak_by_id_desc` — verifies id DESC tiebreak when created_at equal
- `test_legacy_indexes_removed` — verifies uq_prompts_key_type and ix_prompts_active dropped
- `test_double_run_no_errors` — verifies idempotency (schema identical after 2 runs)
- `test_full_init_pipeline_db_idempotent` — full init twice no errors

## Decisions
### Dedupe window function approach
**Choice:** ROW_NUMBER OVER (PARTITION BY dataset_id, name ORDER BY created_at DESC, id DESC) as specified
**Rationale:** Matches VALIDATED_RESEARCH exactly; handles both created_at tiebreaks and id tiebreaks

## Verification
[x] All 5 migration tests pass
[x] _MIGRATIONS has 9 new entries matching section 3.1
[x] _migrate_partial_unique_indexes matches section 3.2 spec
[x] Call order in init_pipeline_db matches section 3.3
[x] Function is idempotent via IF NOT EXISTS and try/except
