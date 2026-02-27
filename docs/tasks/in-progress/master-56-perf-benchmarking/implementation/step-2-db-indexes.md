# IMPLEMENTATION - STEP 2: DB-INDEXES
**Status:** completed

## Summary
Added two performance indexes to pipeline_runs table via add_missing_indexes() helper in db/__init__.py, called from init_pipeline_db() after create_all(). Follows exact SQLiteEventHandler pattern (text() + conn.execute() + conn.commit() in try/except OperationalError).

## Files
**Created:** none
**Modified:** llm_pipeline/db/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/db/__init__.py`
Added `text` and `OperationalError` imports. Created `add_missing_indexes(engine)` function with two CREATE INDEX IF NOT EXISTS statements. Called from `init_pipeline_db()` after `create_all()`. Exported in `__all__`.

```
# Before
from sqlalchemy import Engine, event
from sqlmodel import SQLModel, Session, create_engine

# After
from sqlalchemy import Engine, event, text
from sqlalchemy.exc import OperationalError
from sqlmodel import SQLModel, Session, create_engine
```

```
# Before (init_pipeline_db, after create_all)
    )

    return engine

# After
    )

    # Add performance indexes that create_all skips on existing tables
    add_missing_indexes(engine)

    return engine
```

New function:
```python
def add_missing_indexes(engine: Engine) -> None:
    _INDEX_STATEMENTS = [
        "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_started ON pipeline_runs (started_at)",
        "CREATE INDEX IF NOT EXISTS ix_pipeline_runs_status_started ON pipeline_runs (status, started_at)",
    ]
    for stmt in _INDEX_STATEMENTS:
        try:
            with engine.connect() as conn:
                conn.execute(text(stmt))
                conn.commit()
        except OperationalError:
            pass
```

## Decisions
### Index naming convention
**Choice:** ix_pipeline_runs_started and ix_pipeline_runs_status_started
**Rationale:** Matches existing ix_pipeline_runs_name_started and ix_pipeline_runs_status naming pattern in PipelineRun.__table_args__

### Loop over statements vs separate try/except blocks
**Choice:** Loop with per-statement try/except
**Rationale:** More concise, easily extensible for future indexes, same isolation as separate blocks since each gets its own connection context

## Verification
[x] Both indexes created on fresh DB (verified via sqlite_master query)
[x] Idempotent - calling add_missing_indexes multiple times succeeds without error
[x] Existing indexes (ix_pipeline_runs_name_started, ix_pipeline_runs_status) preserved
[x] All 583 existing tests pass (1 pre-existing failure in test_events_router_prefix unrelated to changes)
[x] Pattern matches SQLiteEventHandler (handlers.py L175-188): text() + conn.execute() + conn.commit() in try/except OperationalError
