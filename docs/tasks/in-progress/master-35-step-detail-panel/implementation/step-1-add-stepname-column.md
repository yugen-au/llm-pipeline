# IMPLEMENTATION - STEP 1: ADD STEP_NAME COLUMN
**Status:** completed

## Summary
Added nullable `step_name` column to `PipelineEventRecord` with composite index for efficient server-side event filtering by step. Added ALTER TABLE migration for existing DBs and step_name extraction on emit.

## Files
**Created:** none
**Modified:** `llm_pipeline/events/models.py`, `llm_pipeline/events/handlers.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/events/models.py`
Added `step_name` nullable column after `pipeline_name` and composite index on `(run_id, step_name)`.
```python
# Before
    pipeline_name: str = Field(
        max_length=100,
        description="Pipeline name in snake_case",
    )
    timestamp: datetime = Field(...)

    __table_args__ = (
        Index("ix_pipeline_events_run_event", "run_id", "event_type"),
        Index("ix_pipeline_events_type", "event_type"),
    )

# After
    pipeline_name: str = Field(
        max_length=100,
        description="Pipeline name in snake_case",
    )
    step_name: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Step name for step-scoped events, None for pipeline-level events",
    )
    timestamp: datetime = Field(...)

    __table_args__ = (
        Index("ix_pipeline_events_run_event", "run_id", "event_type"),
        Index("ix_pipeline_events_type", "event_type"),
        Index("ix_pipeline_events_run_step", "run_id", "step_name"),
    )
```

### File: `llm_pipeline/events/handlers.py`
Added `text` and `OperationalError` imports. Added ALTER TABLE migration in `__init__` after `create_all`. Updated `emit` to extract and pass `step_name`.
```python
# Before (imports)
from sqlalchemy import Engine
from sqlmodel import Session, SQLModel

# After (imports)
from sqlalchemy import Engine, text
from sqlalchemy.exc import OperationalError
from sqlmodel import Session, SQLModel
```

```python
# Before (__init__)
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        SQLModel.metadata.create_all(
            engine, tables=[PipelineEventRecord.__table__]
        )

# After (__init__)
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        SQLModel.metadata.create_all(
            engine, tables=[PipelineEventRecord.__table__]
        )
        try:
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE pipeline_events "
                        "ADD COLUMN step_name VARCHAR(100)"
                    )
                )
                conn.commit()
        except OperationalError:
            pass  # column already exists
```

```python
# Before (emit)
    def emit(self, event: "PipelineEvent") -> None:
        session = Session(self._engine)
        try:
            record = PipelineEventRecord(
                run_id=event.run_id,
                event_type=event.event_type,
                pipeline_name=event.pipeline_name,
                timestamp=event.timestamp,
                event_data=event.to_dict(),
            )

# After (emit)
    def emit(self, event: "PipelineEvent") -> None:
        step_name: str | None = getattr(event, "step_name", None)
        session = Session(self._engine)
        try:
            record = PipelineEventRecord(
                run_id=event.run_id,
                event_type=event.event_type,
                pipeline_name=event.pipeline_name,
                step_name=step_name,
                timestamp=event.timestamp,
                event_data=event.to_dict(),
            )
```

## Decisions
### Migration approach
**Choice:** ALTER TABLE with try/except OperationalError
**Rationale:** No Alembic in project. `create_all` does not add columns to existing tables. SQLite only supports ADD COLUMN. Exception catch makes it idempotent.

### step_name extraction via getattr
**Choice:** `getattr(event, "step_name", None)` rather than direct attribute access
**Rationale:** Safe fallback for any event type. Pipeline-level events (PipelineStarted, PipelineCompleted) have `step_name=None` on base class; getattr is defensive.

## Verification
[x] step_name column added after pipeline_name with Optional[str], max_length=100
[x] Composite index ix_pipeline_events_run_step on (run_id, step_name) in __table_args__
[x] ALTER TABLE migration runs in __init__ after create_all, catches OperationalError
[x] emit extracts step_name via getattr and passes to PipelineEventRecord constructor
[x] All 405 event tests pass
[x] All 10 SQLite-specific tests pass

## Review Fix Iteration 1
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] MEDIUM: ALTER TABLE migration adds step_name column for existing DBs but does NOT create composite index (run_id, step_name). New DBs get index via create_all but existing DBs miss it.

### Changes Made
#### File: `llm_pipeline/events/handlers.py`
Added second try/except block after ALTER TABLE migration to create the composite index using `CREATE INDEX IF NOT EXISTS` (idempotent in SQLite).
```python
# Before
        except OperationalError:
            pass  # column already exists

    def emit(self, event: "PipelineEvent") -> None:

# After
        except OperationalError:
            pass  # column already exists
        # Ensure composite index exists for existing DBs.
        # create_all does not add indexes to existing tables.
        try:
            with engine.connect() as conn:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS "
                        "ix_pipeline_events_run_step "
                        "ON pipeline_events (run_id, step_name)"
                    )
                )
                conn.commit()
        except OperationalError:
            pass  # index already exists or table doesn't exist yet

    def emit(self, event: "PipelineEvent") -> None:
```

### Verification
[x] All 31 handler tests pass
[x] CREATE INDEX IF NOT EXISTS is idempotent - safe for new and existing DBs
