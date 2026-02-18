# IMPLEMENTATION - STEP 4: ADD INIT_PIPELINE_DB TESTS
**Status:** completed

## Summary
Created `tests/test_init_pipeline_db.py` with 3 integration tests verifying `init_pipeline_db()` creates and configures the `pipeline_events` table correctly.

## Files
**Created:** `tests/test_init_pipeline_db.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/test_init_pipeline_db.py`
New file with 3 tests in `TestInitPipelineDbPipelineEvents` class.

```
# Before
[file did not exist]

# After
class TestInitPipelineDbPipelineEvents:
    def test_table_creation(self): ...       # inspector.get_table_names() contains pipeline_events
    def test_index_creation(self): ...       # ix_pipeline_events_run_event present
    def test_round_trip_insert(self): ...    # insert + query PipelineEventRecord, assert fields
```

## Decisions
### Index name discrepancy
**Choice:** Used `ix_pipeline_events_run_event` (actual name from `PipelineEventRecord.__table_args__`)
**Rationale:** PLAN.md and task goal mentioned `ix_pipeline_events_run_id_event_type`, but the model in `llm_pipeline/events/models.py` defines `Index("ix_pipeline_events_run_event", ...)`. Ground truth is the code.

### Engine isolation
**Choice:** Each test creates `create_engine("sqlite://")` and calls `engine.dispose()` in a `finally` block
**Rationale:** Matches PLAN.md step 5 requirement; prevents shared state between tests.

## Verification
- [x] `pytest tests/test_init_pipeline_db.py -v` -> 3 passed
- [x] Full suite `pytest -q` -> 468 passed, 16 pre-existing failures in `test_retry_ratelimit_events.py` (ModuleNotFoundError: google), no regressions
