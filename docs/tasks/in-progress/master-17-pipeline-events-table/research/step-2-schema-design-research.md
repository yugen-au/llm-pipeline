# Step 2: Schema Design Research - pipeline_events Table

## Researcher: database-architect
## Date: 2026-02-18
## Task: master-17 (Create pipeline_events Database Table)

---

## 1. Key Discovery: Model Already Exists

`PipelineEventRecord` already exists at `llm_pipeline/events/models.py` (created during task 1 work). It is NOT in `state.py` as the task 17 spec originally suggested.

**Location**: `llm_pipeline/events/models.py`
**Used by**: `SQLiteEventHandler` in `llm_pipeline/events/handlers.py`

### Current Schema

```python
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

---

## 2. Schema Analysis

### 2.1 Fields

| Field | Type | Constraint | Assessment |
|-------|------|-----------|------------|
| id | Optional[int] | PK, autoincrement | Matches codebase convention (state.py, prompt.py) |
| run_id | str | max_length=36 | UUID length, correct |
| event_type | str | max_length=100 | Matches event type string lengths |
| pipeline_name | str | max_length=100 | Extra vs task spec; matches PipelineEvent dataclass fields; good for multi-pipeline filtering |
| timestamp | datetime | default_factory=utc_now | Timezone-aware UTC; matches state.py pattern |
| event_data | dict | sa_column=Column(JSON) | Matches codebase JSON column convention |

### 2.2 Deviations from Task 17 Spec

1. **pipeline_name field**: Present in model but not in task 17 spec. This is a **positive deviation** - enables filtering by pipeline without parsing JSON. Matches the PipelineEvent dataclass shape.

2. **Model location**: events/models.py instead of state.py. **Better architecture** - event persistence belongs with event subsystem, not generic pipeline state.

3. **Model name**: `PipelineEventRecord` (not `PipelineEvent`). **Correct** - avoids collision with the dataclass `PipelineEvent` in events/types.py.

---

## 3. Index Strategy Analysis

### 3.1 Current Indexes

| Name | Columns | Purpose |
|------|---------|---------|
| PK (implicit) | id | Row identity, SQLite rowid |
| ix_pipeline_events_run_event | (run_id, event_type) | Composite: both columns or run_id-only queries |
| ix_pipeline_events_type | event_type | Event-type-only filtering across runs |

### 3.2 Query Pattern Coverage

| Query Pattern | SQL WHERE | Served By |
|--------------|-----------|-----------|
| All events for a run | `run_id = ?` | Composite leftmost prefix (run_id) |
| Specific event type in run | `run_id = ? AND event_type = ?` | Composite (exact match) |
| All events of a type | `event_type = ?` | ix_pipeline_events_type |
| Run timeline (ordered) | `run_id = ? ORDER BY id` | Composite filter + PK ordering (free in SQLite) |

### 3.3 Task 17 Spec vs Actual

Task 17 spec proposed separate `Index('ix_pipeline_events_run_id', 'run_id')` and `Index('ix_pipeline_events_event_type', 'event_type')`. The actual implementation uses a **composite index** instead of a separate run_id index.

**Assessment: The composite approach is superior.**

The composite index `(run_id, event_type)` serves all run_id-only queries via the leftmost prefix rule. Adding a separate run_id index would be **redundant** -- it wastes storage and adds write overhead with zero query benefit. The standalone event_type index is still needed since event_type is NOT the leftmost column in the composite.

### 3.4 Index Recommendation: No Changes Needed

- A `(run_id, timestamp)` composite index is unnecessary because events-per-run are bounded (tens to low hundreds per execution) and PK ordering provides natural chronological sort.
- No JSON path indexes needed -- event_data is write-once/read-whole; filtering happens in Python.

---

## 4. SQLModel/SQLAlchemy 2.0 Best Practices

### 4.1 JSON Column Pattern

```python
# Codebase convention (all 3 models with JSON):
event_data: dict = Field(sa_column=Column(JSON))
result_data: dict = Field(sa_column=Column(JSON))
required_variables: Optional[List[str]] = Field(default=None, sa_column=Column(JSON))
```

- Uses `sa_column=Column(JSON)` from `sqlmodel` -- required because SQLModel does not natively map `dict` types.
- SQLAlchemy's `JSON` type maps to SQLite TEXT storage with JSON1 extension functions.
- JSON1 extension available since SQLite 3.9 (2015); all modern Python distributions include it.
- **Context7 confirms**: `sa_column=Column(JSON)` is the correct SQLModel pattern for JSON storage.

### 4.2 Timestamp Handling

```python
# Codebase convention (state.py):
def utc_now():
    return datetime.now(timezone.utc)

# Used as:
timestamp: datetime = Field(default_factory=utc_now)
created_at: datetime = Field(default_factory=utc_now)
```

- Returns **timezone-aware** `datetime` objects (UTC).
- SQLite stores datetimes as ISO 8601 TEXT strings.
- SQLAlchemy's default `DateTime` type (without `timezone=True`) is used across all models.
- This works because UTC is enforced at application level via `utc_now()`.
- Consistent with PipelineStepState and PipelineRunInstance in state.py.

**Note**: Prompt model uses `lambda: datetime.now(timezone.utc)` instead of `utc_now()` -- minor inconsistency but functionally equivalent.

### 4.3 Table Naming Convention

| Model | Table Name | Pattern |
|-------|-----------|---------|
| PipelineStepState | pipeline_step_states | snake_case, plural |
| PipelineRunInstance | pipeline_run_instances | snake_case, plural |
| Prompt | prompts | snake_case, plural |
| PipelineEventRecord | pipeline_events | snake_case, plural |

All follow `snake_case_plural` convention. `pipeline_events` is correct.

### 4.4 Primary Key Convention

All models use:
```python
id: Optional[int] = Field(default=None, primary_key=True)
```

- `Optional[int]` with `default=None` allows SQLite autoincrement to assign the value.
- Consistent across all four models.

### 4.5 __table_args__ Pattern

All models with custom indexes use a tuple of `Index(...)` objects in `__table_args__`. Named indexes follow `ix_{tablename}_{description}` convention.

---

## 5. Integration Gap: init_pipeline_db()

### 5.1 Current State

`llm_pipeline/db/__init__.py` init_pipeline_db() creates tables for:
- PipelineStepState
- PipelineRunInstance
- Prompt

`PipelineEventRecord` is **NOT** in this list.

Currently, `SQLiteEventHandler.__init__()` calls `create_all` for the table independently. This means:
- If using SQLiteEventHandler, the table is created on handler instantiation.
- If NOT using SQLiteEventHandler (e.g., only InMemoryEventHandler), the table is never created.
- If calling `init_pipeline_db()` expecting all framework tables, pipeline_events is missing.

### 5.2 Required Changes for Implementation Phase

1. **Add to init_pipeline_db()**: Import `PipelineEventRecord` and add `PipelineEventRecord.__table__` to the `tables` list in `SQLModel.metadata.create_all()`.

2. **Export from __init__.py**: Add `PipelineEventRecord` to `llm_pipeline/__init__.py` exports.

3. **SQLiteEventHandler.create_all remains**: Keep it as a safety net for standalone handler use (idempotent, no conflict).

### 5.3 Import Chain

```
llm_pipeline/db/__init__.py
  -> imports from llm_pipeline.events.models import PipelineEventRecord
  -> adds PipelineEventRecord.__table__ to create_all tables list

llm_pipeline/__init__.py
  -> imports PipelineEventRecord (from events.models or re-export from events)
  -> adds to __all__
```

---

## 6. Downstream Impact (Task 50)

Task 50 (Create Draft Steps Database Tables) depends on task 17 and will follow the same patterns:
- `sa_column=Column(JSON)` for JSON fields
- `utc_now` factory for timestamps
- Addition to `init_pipeline_db()` tables list

The pattern established here in task 17 sets direct precedent for task 50's implementation.

---

## 7. Summary of Recommendations

| # | Finding | Recommendation |
|---|---------|---------------|
| 1 | Model already exists at events/models.py | Use as-is, do NOT move to state.py |
| 2 | Schema is sound (5 columns + PK) | No schema changes needed |
| 3 | pipeline_name field (extra vs spec) | Keep - valuable for filtering |
| 4 | Composite index is better than spec's separate indexes | Keep current indexing, do not add redundant run_id index |
| 5 | Missing from init_pipeline_db() | Add PipelineEventRecord.__table__ to tables list |
| 6 | Missing from __init__.py exports | Add PipelineEventRecord to exports and __all__ |
| 7 | JSON column pattern | Correct, follows codebase convention |
| 8 | Timestamp pattern | Correct, follows codebase convention |
| 9 | Table naming | Correct, follows snake_case_plural convention |
