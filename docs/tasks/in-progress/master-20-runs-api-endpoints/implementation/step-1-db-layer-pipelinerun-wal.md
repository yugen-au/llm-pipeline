# IMPLEMENTATION - STEP 1: DB LAYER: PIPELINERUN + WAL
**Status:** completed

## Summary
Added PipelineRun SQLModel table to state.py for tracking pipeline run lifecycle. Enabled SQLite WAL mode via event listener in init_pipeline_db(). Removed redundant index=True from run_id fields on PipelineStepState and PipelineRunInstance.

## Files
**Created:** none
**Modified:** llm_pipeline/state.py, llm_pipeline/db/__init__.py
**Deleted:** none

## Changes
### File: `llm_pipeline/state.py`
Added PipelineRun SQLModel table class after PipelineRunInstance. Removed redundant `index=True` from `run_id` on PipelineStepState (line 44) and PipelineRunInstance (line 122) since composite indexes already cover those columns. Added PipelineRun to `__all__`.

```
# Before (PipelineStepState.run_id)
run_id: str = Field(max_length=36, index=True, description="...")

# After
run_id: str = Field(max_length=36, description="...")
```

```
# Before (PipelineRunInstance.run_id)
run_id: str = Field(max_length=36, index=True, description="...")

# After
run_id: str = Field(max_length=36, description="...")
```

```python
# New class added
class PipelineRun(SQLModel, table=True):
    __tablename__ = "pipeline_runs"
    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(max_length=36, unique=True, ...)
    pipeline_name: str = Field(max_length=100, ...)
    status: str = Field(max_length=20, default="running", ...)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = Field(default=None)
    step_count: Optional[int] = Field(default=None)
    total_time_ms: Optional[int] = Field(default=None)
    __table_args__ = (
        Index("ix_pipeline_runs_name_started", "pipeline_name", "started_at"),
        Index("ix_pipeline_runs_status", "status"),
    )
```

### File: `llm_pipeline/db/__init__.py`
Imported `event` from sqlalchemy and `PipelineRun` from state. Added SQLite WAL mode listener after engine assignment. Added PipelineRun.__table__ to create_all tables list.

```
# Before
from sqlalchemy import Engine
from llm_pipeline.state import PipelineStepState, PipelineRunInstance

# After
from sqlalchemy import Engine, event
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun
```

```python
# WAL listener added after _engine = engine
if engine.url.drivername.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_wal(dbapi_conn, conn_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
```

## Decisions
### Redundant index removal
**Choice:** Removed `index=True` from run_id on PipelineStepState and PipelineRunInstance
**Rationale:** Composite indexes `ix_pipeline_step_states_run(run_id, step_number)` and `ix_pipeline_run_instances_run(run_id)` already cover run_id lookups. The standalone index was redundant overhead.

### WAL listener placement
**Choice:** Placed WAL listener inside init_pipeline_db() after engine assignment, guarded by sqlite drivername check
**Rationale:** Both engine creation sites (db/__init__.py and ui/app.py) pass through init_pipeline_db(), so one listener covers both. Safe for :memory: (pragma silently ignored). Follows SQLAlchemy docs pattern for PRAGMA event listeners.

## Verification
[x] PipelineRun class has all specified fields with correct types and defaults
[x] __tablename__ = "pipeline_runs" with correct indexes
[x] run_id has unique=True constraint
[x] Redundant index=True removed from PipelineStepState.run_id
[x] Redundant index=True removed from PipelineRunInstance.run_id
[x] PipelineRun added to __all__ in state.py
[x] WAL mode listener added with sqlite drivername guard
[x] PipelineRun.__table__ added to create_all tables list
[x] PipelineRun imported in db/__init__.py
[x] event imported from sqlalchemy in db/__init__.py
[x] All 511 existing tests pass (16 pre-existing failures in test_retry_ratelimit_events.py due to missing google module - unrelated)

## Review Fix Iteration 0
**Issues Source:** [REVIEW.md]
**Status:** fixed

### Issues Addressed
[x] WAL event listener registered multiple times on repeated init_pipeline_db() calls
[x] PipelineRun not exported from top-level __init__.py

### Changes Made
#### File: `llm_pipeline/db/__init__.py`
Added module-level `_wal_registered_engines` set to track engines with WAL listener. Guard WAL registration with `id(engine) not in _wal_registered_engines` check.

```
# Before
_engine: Optional[Engine] = None
...
if engine.url.drivername.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_wal(dbapi_conn, conn_record):

# After
_engine: Optional[Engine] = None
_wal_registered_engines: set = set()
...
if engine.url.drivername.startswith("sqlite") and id(engine) not in _wal_registered_engines:
    _wal_registered_engines.add(id(engine))

    @event.listens_for(engine, "connect")
    def set_sqlite_wal(dbapi_conn, conn_record):
```

#### File: `llm_pipeline/__init__.py`
Added PipelineRun import and __all__ entry alongside existing state exports.

```
# Before
from llm_pipeline.state import PipelineStepState, PipelineRunInstance
...
"PipelineStepState",
"PipelineRunInstance",

# After
from llm_pipeline.state import PipelineStepState, PipelineRunInstance, PipelineRun
...
"PipelineStepState",
"PipelineRunInstance",
"PipelineRun",
```

### Verification
[x] _wal_registered_engines prevents duplicate listener registration on repeated init_pipeline_db() calls
[x] PipelineRun importable via `from llm_pipeline import PipelineRun`
[x] All 558 tests pass (0 failures)
