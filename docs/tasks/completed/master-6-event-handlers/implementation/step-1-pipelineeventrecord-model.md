# IMPLEMENTATION - STEP 1: PIPELINEEVENTRECORD MODEL
**Status:** completed

## Summary
Created `llm_pipeline/events/models.py` with `PipelineEventRecord(SQLModel, table=True)` for the `pipeline_events` table. Model follows all conventions from `state.py`: `Optional[int]` PK, `Field(max_length=N)`, `sa_column=Column(JSON)`, `default_factory=utc_now`. Two optimised indexes per architecture decision.

## Files
**Created:** `llm_pipeline/events/models.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/events/models.py`
New file. Defines `PipelineEventRecord` SQLModel table class with:
- 6 columns: `id` (PK), `run_id`, `event_type`, `pipeline_name`, `timestamp`, `event_data` (JSON)
- 2 indexes: `ix_pipeline_events_run_event` (composite: run_id + event_type), `ix_pipeline_events_type` (standalone: event_type)
- `__repr__` method
- `__all__` exports
- Imports `utc_now` from `llm_pipeline.state` (reuse, not duplicate)

```python
# Key structure
class PipelineEventRecord(SQLModel, table=True):
    __tablename__ = "pipeline_events"
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(max_length=36)
    event_type: str = Field(max_length=100)
    pipeline_name: str = Field(max_length=100)
    timestamp: datetime = Field(default_factory=utc_now)
    event_data: dict = Field(sa_column=Column(JSON))
    __table_args__ = (
        Index("ix_pipeline_events_run_event", "run_id", "event_type"),
        Index("ix_pipeline_events_type", "event_type"),
    )
```

## Decisions
### utc_now import source
**Choice:** Import `utc_now` from `llm_pipeline.state` rather than redefining
**Rationale:** Single source of truth for UTC timestamp factory; state.py already defines and exports it. Avoids duplication.

### No Field(index=True) on run_id
**Choice:** Omit standalone run_id index; rely on composite index leftmost prefix
**Rationale:** Per VALIDATED_RESEARCH.md decision 3 -- composite `(run_id, event_type)` covers run_id-only queries via leftmost prefix. Reduces storage overhead.

## Verification
[x] Model imports successfully
[x] `__tablename__` = "pipeline_events"
[x] 6 columns: id, run_id, event_type, pipeline_name, timestamp, event_data
[x] 2 indexes: ix_pipeline_events_run_event, ix_pipeline_events_type
[x] `__repr__` returns expected format
[x] `__all__` exports PipelineEventRecord
[x] Table creation works with SQLite in-memory engine
[x] JSON field round-trips dict correctly
[x] timestamp defaults to UTC via utc_now
[x] Follows state.py conventions (Optional[int] PK, Field(max_length=N), sa_column=Column(JSON))
