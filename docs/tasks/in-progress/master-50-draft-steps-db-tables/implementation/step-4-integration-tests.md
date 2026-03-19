# IMPLEMENTATION - STEP 4: INTEGRATION TESTS
**Status:** completed

## Summary
Created `tests/test_draft_tables.py` with 15 integration tests across 4 classes covering table creation, index creation, unique constraint enforcement, CRUD, JSON serialization, optional fields, run_id optionality, and status transitions for `DraftStep` and `DraftPipeline`.

## Files
**Created:** `tests/test_draft_tables.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/test_draft_tables.py`
New file. 4 test classes, 15 tests total. In-memory SQLite engine per test, `engine.dispose()` in finally block matching existing pattern.

```
# Before
[file did not exist]

# After
TestDraftStepTableCreation   - 3 tests: table_creation, index_creation, unique_constraint_on_name
TestDraftPipelineTableCreation - 3 tests: table_creation, index_creation, unique_constraint_on_name
TestDraftStepCRUD            - 5 tests: insert_and_retrieve, json_serialization, optional_json_fields_nullable, run_id_optional, status_transitions
TestDraftPipelineCRUD        - 4 tests: insert_and_retrieve, json_serialization, optional_json_fields_nullable, status_transitions
```

## Decisions
### IntegrityError import source
**Choice:** `from sqlalchemy.exc import IntegrityError`
**Rationale:** SQLModel re-exports are not guaranteed; sqlalchemy.exc is the canonical source matching plan spec.

### Engine-per-test (no shared fixture)
**Choice:** Each test method creates and disposes its own `create_engine("sqlite://")` instance
**Rationale:** Matches `test_init_pipeline_db.py` pattern exactly. SQLModel uses shared metadata; per-test engines isolate state without needing fixture teardown.

## Verification
- [x] `pytest tests/test_draft_tables.py -v` - 15/15 passed in 1.40s
- [x] All 4 test classes present matching plan spec
- [x] unique constraint raises IntegrityError on duplicate name
- [x] JSON nested dicts round-trip correctly
- [x] Optional JSON fields default to None
- [x] run_id=None and run_id=UUID string both accepted
- [x] Status transitions draft -> tested -> accepted verified
- [x] DraftPipeline status=error with compilation_errors stored simultaneously verified
