# Research: SQLite Event Schema Design

## Summary

Design for `pipeline_events` table following established SQLModel/SQLAlchemy 2.0 patterns in `llm_pipeline/state.py`, `llm_pipeline/db/prompt.py`, and `llm_pipeline/db/__init__.py`.

---

## 1. Existing Codebase Patterns

### SQLModel Table Pattern (from `state.py`, `db/prompt.py`)
- `SQLModel` with `table=True`
- Explicit `__tablename__`
- `Optional[int]` primary key with `Field(default=None, primary_key=True)`
- String fields: `Field(max_length=N)`
- JSON columns: `sa_column=Column(JSON)` on `dict` typed fields
- Datetime fields: `Field(default_factory=utc_now)` (UTC-aware)
- Indexes: `__table_args__` tuple with `Index()` objects

### Table Creation Pattern (from `db/__init__.py`)
```python
SQLModel.metadata.create_all(
    engine,
    tables=[PipelineStepState.__table__, PipelineRunInstance.__table__, Prompt.__table__],
)
```
Explicit table list, additive (won't drop existing tables).

### JSON Column Pattern (from `state.py`)
```python
result_data: dict = Field(sa_column=Column(JSON), description="...")
context_snapshot: dict = Field(sa_column=Column(JSON), description="...")
```
SQLite stores JSON as TEXT. SQLAlchemy `JSON` type handles Python dict serialization transparently.

### Event Serialization (from `events/types.py`)
`PipelineEvent.to_dict()` converts all datetimes to ISO strings, producing a JSON-safe dict. `PipelineEvent.resolve_event(event_type, data)` reconstructs from serialized form.

---

## 2. Schema Design

### Model Name

`PipelineEventRecord` -- avoids collision with the `PipelineEvent` dataclass in `events/types.py`.

### Column Definitions

| Column | Python Type | SQLModel/SA Config | SQLite Type | Nullable | Notes |
|---|---|---|---|---|---|
| `id` | `Optional[int]` | `Field(default=None, primary_key=True)` | INTEGER PK AUTOINCREMENT | N | Standard pattern |
| `run_id` | `str` | `Field(max_length=36, index=True)` | VARCHAR(36) | N | UUID, matches `PipelineStepState.run_id` |
| `event_type` | `str` | `Field(max_length=100)` | VARCHAR(100) | N | snake_case (e.g. `llm_call_completed`), derived by `_derive_event_type()` |
| `event_data` | `dict` | `sa_column=Column(JSON)` | TEXT (JSON) | N | Full serialized event via `to_dict()` |
| `timestamp` | `datetime` | `Field(default_factory=utc_now)` | TIMESTAMP | N | Copied from event's `timestamp` field |

### Intentional Duplication

`run_id`, `event_type`, and `timestamp` appear both as top-level columns AND inside `event_data`. This is deliberate:
- **Top-level columns**: Efficient filtering/indexing without JSON parsing
- **event_data JSON**: Full event reconstruction via `PipelineEvent.resolve_event()`

### Proposed SQLModel Class

```python
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import Index
from llm_pipeline.state import utc_now


class PipelineEventRecord(SQLModel, table=True):
    """Persisted pipeline event for SQLiteEventHandler."""
    __tablename__ = "pipeline_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(max_length=36, description="Pipeline run UUID")
    event_type: str = Field(max_length=100, description="Snake-case event type")
    event_data: dict = Field(
        sa_column=Column(JSON),
        description="Full serialized event (from PipelineEvent.to_dict())"
    )
    timestamp: datetime = Field(
        default_factory=utc_now,
        description="Event timestamp (UTC)"
    )

    __table_args__ = (
        Index("ix_pipeline_events_run_id", "run_id"),
        Index("ix_pipeline_events_event_type", "event_type"),
        Index("ix_pipeline_events_run_type", "run_id", "event_type"),
    )
```

---

## 3. Index Design

### Query Patterns and Index Mapping

| Query Pattern | Index Used | Rationale |
|---|---|---|
| All events for a run | `ix_pipeline_events_run_id` | Primary query for run replay/debugging |
| All events of a type | `ix_pipeline_events_event_type` | Aggregate analysis (e.g. all LLM failures) |
| Events of type X for run Y | `ix_pipeline_events_run_type` | Composite covers both columns, avoids scan |
| Events by time range | No dedicated index | Not in task requirements; `timestamp` unindexed. Add later if needed |

### Index Notes
- `run_id` gets its own `Field(index=True)` (matching `PipelineStepState.run_id` pattern) PLUS appears in composite
- SQLAlchemy may deduplicate the single-column index from `Field(index=True)` and the explicit `Index()` in `__table_args__`, but using explicit `Index()` objects in `__table_args__` is cleaner for consistency with existing models
- **Recommendation**: Use only `__table_args__` indexes (drop `index=True` from Field) to avoid potential duplicate index creation. Existing `PipelineStepState` uses both approaches -- `run_id` has `index=True` AND appears in `__table_args__` composite. For the events table, composite index on `(run_id, event_type)` subsumes a standalone `run_id` index (leftmost prefix), so only two indexes are strictly needed: the composite and the standalone `event_type`

### Optimized Index Set (Recommended)

```python
__table_args__ = (
    Index("ix_pipeline_events_run_type", "run_id", "event_type"),
    Index("ix_pipeline_events_event_type", "event_type"),
)
```

The composite `(run_id, event_type)` serves both "all events for run" and "events of type for run" queries via leftmost prefix. The standalone `event_type` index handles "all events of type X" across runs.

---

## 4. JSON Storage Best Practices

### SQLite JSON Type
- SQLite has no native JSON column type; `JSON` columns store as `TEXT`
- SQLAlchemy `Column(JSON)` handles `json.dumps()`/`json.loads()` transparently
- Codebase precedent: `PipelineStepState.result_data` and `context_snapshot` use this exact pattern

### Serialization Flow
```
PipelineEvent instance
  -> event.to_dict()      # datetimes -> ISO strings
  -> stored in event_data  # SQLAlchemy JSON serializes to TEXT
```

### Deserialization / Reconstruction
```
PipelineEventRecord.event_data  # SQLAlchemy JSON deserializes to dict
  -> PipelineEvent.resolve_event(record.event_type, record.event_data)
  -> Typed PipelineEvent subclass instance
```

### Event Data Size Considerations
- Most events are small (<1KB JSON)
- `LLMCallStarting` includes full prompts -- could be 10-50KB
- `LLMCallCompleted` includes raw_response -- could be 10-100KB
- SQLite handles TEXT up to 1GB; no practical concern
- If size becomes an issue, handler could filter out large fields (future optimization)

---

## 5. SQLModel/SQLAlchemy 2.0 Integration

### Where to Define the Model
`llm_pipeline/events/handlers.py` alongside the handler, or as a separate module. Recommendation: define in `handlers.py` since it's only used by `SQLiteEventHandler`. Keep co-located.

### Table Creation Strategy
**Handler self-init** (recommended over adding to `init_pipeline_db()`):

```python
class SQLiteEventHandler:
    def __init__(self, engine: Engine):
        self._engine = engine
        # Create table if not exists (additive, safe to call multiple times)
        SQLModel.metadata.create_all(engine, tables=[PipelineEventRecord.__table__])
```

Rationale:
- Handler is opt-in, table shouldn't exist unless handler is used
- Follows principle of least surprise: enabling handler creates its table
- `create_all()` with explicit table list is idempotent and safe
- Does NOT modify `init_pipeline_db()` -- zero impact on existing code

### Engine Access
Handler receives engine in constructor. Pipeline has engine accessible via:
```python
engine = pipeline._real_session.get_bind()
```
Or user passes the same engine used for pipeline init:
```python
engine = create_engine("sqlite:///pipeline.db")
handler = SQLiteEventHandler(engine=engine)
pipeline = MyPipeline(engine=engine, event_emitter=CompositeEmitter([handler]))
```

### Session Management
Handler should create short-lived sessions per write (not hold a long-lived session):
```python
def emit(self, event: PipelineEvent) -> None:
    record = PipelineEventRecord(
        run_id=event.run_id,
        event_type=event.event_type,
        event_data=event.to_dict(),
        timestamp=event.timestamp,
    )
    with Session(self._engine) as session:
        session.add(record)
        session.commit()
```
This avoids session state accumulation and is safe for concurrent access from different threads (SQLite WAL mode or serialized writes).

---

## 6. Migration Considerations

### This Is a New Table Only
- No modifications to existing tables (`pipeline_step_states`, `pipeline_run_instances`, `prompts`)
- No foreign key relationships to existing tables (run_id is a logical link, not FK)
- Additive schema change: zero risk to existing functionality

### Table Creation Timing
- Created on first `SQLiteEventHandler` instantiation
- `SQLModel.metadata.create_all()` is idempotent -- safe to call on every handler init
- No migration tool (Flyway/Alembic) needed for this; `create_all()` handles new tables

### Future Migration Path
If schema needs changes later (new columns, index changes):
- Option A: Drop and recreate (events are ephemeral/diagnostic, acceptable data loss)
- Option B: Manual ALTER TABLE via Alembic if events become critical data
- Recommendation: Events are diagnostic. Document that schema changes may require table recreation.

### Compatibility
- Works with any SQLite database (file-based or in-memory `:memory:`)
- Works with user-provided engines (not just auto-SQLite)
- No SQLite version requirements beyond what SQLAlchemy 2.0 supports

---

## 7. Scope Boundaries

### In Scope (Task 6)
- `PipelineEventRecord` model definition
- Table creation in handler `__init__`
- Write path: `emit()` -> `PipelineEventRecord` -> session commit
- Basic query support for testing

### Out of Scope
- Task 8: Emitting events from `pipeline.execute()` (downstream)
- Task 18: Exporting in `__init__.py` (downstream)
- Task 26: UIBridge handler (downstream, async)
- Event retention/cleanup policies
- Event data size limits or filtering
- Read-optimized query API (beyond basic retrieval for tests)
