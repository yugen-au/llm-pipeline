# Step 1: Existing Codebase Analysis for Task 17

## Critical Deviation: PipelineEventRecord Already Exists

`llm_pipeline/events/models.py` already defines `PipelineEventRecord(SQLModel, table=True)` with `__tablename__ = "pipeline_events"`. Created in task 6 (event handlers). The model is complete and tested.

Task 17's description assumes this model doesn't exist and proposes a class named `PipelineEvent` -- but that name is taken by the dataclass base in `events/types.py`. The existing `PipelineEventRecord` naming is intentional to avoid collision.

### What Task 17 Actually Needs

1. **Add `PipelineEventRecord.__table__` to `init_pipeline_db()`** -- currently only `SQLiteEventHandler.__init__` creates the table
2. **Export `PipelineEventRecord` from `llm_pipeline/__init__.py`**
3. Model definition itself is DONE -- no new model needed

---

## Existing SQLModel Patterns

### File: `llm_pipeline/state.py`

Two models: `PipelineStepState`, `PipelineRunInstance`

**Primary key pattern:**
```python
id: Optional[int] = Field(default=None, primary_key=True)
```

**String fields:**
```python
pipeline_name: str = Field(max_length=100, description="...")
run_id: str = Field(max_length=36, index=True, description="...")
```

**JSON columns:**
```python
result_data: dict = Field(sa_column=Column(JSON), description="...")
context_snapshot: dict = Field(sa_column=Column(JSON), description="...")
```

**Timestamps:**
```python
from llm_pipeline.state import utc_now  # shared helper
created_at: datetime = Field(default_factory=utc_now)
```

**utc_now helper (state.py:19-21):**
```python
def utc_now():
    return datetime.now(timezone.utc)
```

**Tablename convention:** explicit `__tablename__`, snake_case plural (e.g., `pipeline_step_states`, `pipeline_run_instances`)

**Index pattern:**
```python
__table_args__ = (
    Index("ix_{tablename}_{suffix}", "col1", "col2"),
)
```
Index naming: `ix_` prefix + tablename + descriptive suffix.

### File: `llm_pipeline/db/prompt.py`

Model: `Prompt`

Same patterns as state.py except:
- Uses `lambda: datetime.now(timezone.utc)` instead of `utc_now` for timestamps (minor inconsistency)
- Includes `UniqueConstraint` in `__table_args__`
- Has `__repr__` method

### File: `llm_pipeline/events/models.py` (THE EXISTING TABLE)

Model: `PipelineEventRecord`

```python
class PipelineEventRecord(SQLModel, table=True):
    __tablename__ = "pipeline_events"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(max_length=36, description="...")
    event_type: str = Field(max_length=100, description="...")
    pipeline_name: str = Field(max_length=100, description="...")
    timestamp: datetime = Field(default_factory=utc_now, description="...")
    event_data: dict = Field(sa_column=Column(JSON), description="...")

    __table_args__ = (
        Index("ix_pipeline_events_run_event", "run_id", "event_type"),
        Index("ix_pipeline_events_type", "event_type"),
    )
```

Follows all established conventions. Has `__repr__`.

**Comparison vs task 17 spec:**
| Aspect | Task 17 Spec | Existing PipelineEventRecord |
|--------|-------------|------------------------------|
| Class name | `PipelineEvent` | `PipelineEventRecord` (avoids collision) |
| pipeline_name field | Missing | Present |
| run_id index | Standalone | Composite (run_id, event_type) -- better |
| event_type index | Standalone | Standalone -- same |
| `__repr__` | Not specified | Present |

---

## Database Initialization: `llm_pipeline/db/__init__.py`

### init_pipeline_db()

```python
def init_pipeline_db(engine: Optional[Engine] = None) -> Engine:
    global _engine
    if engine is None:
        db_path = get_default_db_path()
        db_url = f"sqlite:///{db_path}"
        engine = create_engine(db_url, echo=False)
    _engine = engine
    SQLModel.metadata.create_all(
        engine,
        tables=[
            PipelineStepState.__table__,
            PipelineRunInstance.__table__,
            Prompt.__table__,
        ],
    )
    return engine
```

**Current tables registered:** PipelineStepState, PipelineRunInstance, Prompt
**Missing:** PipelineEventRecord -- needs adding

**Pattern:** Explicit `tables=[...]` list, not blanket `create_all()`. Each table imported at module top.

### Current imports in db/__init__.py

```python
from llm_pipeline.db.prompt import Prompt
from llm_pipeline.state import PipelineStepState, PipelineRunInstance
```

Need to add: `from llm_pipeline.events.models import PipelineEventRecord`

### SQLiteEventHandler creates table independently

`handlers.py:157-159`:
```python
def __init__(self, engine: Engine) -> None:
    self._engine = engine
    SQLModel.metadata.create_all(engine, tables=[PipelineEventRecord.__table__])
```

This is idempotent (safe to call multiple times). After integration into init_pipeline_db(), both paths will work.

---

## Exports: `llm_pipeline/__init__.py`

### Current structure

```python
from llm_pipeline.state import PipelineStepState, PipelineRunInstance

__all__ = [
    # Core
    "PipelineConfig", "LLMStep", "LLMResultMixin", "step_definition",
    # Strategy
    "PipelineStrategy", "PipelineStrategies", "StepDefinition",
    # Data handling
    "PipelineContext", "PipelineExtraction", "PipelineTransformation", "PipelineDatabaseRegistry",
    # State
    "PipelineStepState", "PipelineRunInstance",
    # Types
    "ArrayValidationConfig", "ValidationContext",
    # DB
    "init_pipeline_db",
    # Session
    "ReadOnlySession",
]
```

**Missing:** `PipelineEventRecord` -- should be added under State section alongside existing state models.

---

## Dependencies (pyproject.toml)

```
sqlmodel>=0.0.14
sqlalchemy>=2.0
pydantic>=2.0
```

No version changes needed for task 17.

---

## Downstream Scope Boundary (Task 50)

Task 50 adds DraftStep/DraftPipeline tables. OUT OF SCOPE for task 17. Task 50 depends on task 17, confirming the pattern: define table -> integrate into init_pipeline_db() -> export.

---

## Summary of Required Changes for Task 17

1. `llm_pipeline/db/__init__.py`: Import PipelineEventRecord, add to create_all tables list
2. `llm_pipeline/__init__.py`: Import and export PipelineEventRecord
3. NO new model definition needed -- PipelineEventRecord already exists and is correct
