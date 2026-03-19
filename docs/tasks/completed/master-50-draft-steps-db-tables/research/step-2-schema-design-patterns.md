# Research Step 2: Schema Design Patterns for draft_steps & draft_pipelines

## JSON Column Patterns in SQLModel/SQLAlchemy 2.0

### Established codebase pattern
All JSON columns in the project use `sa_column=Column(JSON)`:

```python
from sqlmodel import SQLModel, Field, Column, JSON

# Required JSON field (always has data)
result_data: dict = Field(sa_column=Column(JSON), description="...")

# Optional/nullable JSON field
test_results: Optional[dict] = Field(default=None, sa_column=Column(JSON))

# JSON list field
files_generated: list[str] = Field(default_factory=list, sa_column=Column(JSON))
```

Files using this pattern: `state.py` (result_data, context_snapshot), `events/models.py` (event_data), `db/prompt.py` (required_variables), `creator/models.py` (files_generated).

### Application to DraftStep/DraftPipeline

| Column | Type | Nullable | Rationale |
|--------|------|----------|-----------|
| `DraftStep.generated_code` | `dict = Field(sa_column=Column(JSON))` | No | Always populated -- the step's whole purpose is code generation. Keys: instructions, step, extractions, prompts |
| `DraftStep.test_results` | `Optional[dict] = Field(default=None, sa_column=Column(JSON))` | Yes | Null until tests run |
| `DraftStep.validation_errors` | `Optional[dict] = Field(default=None, sa_column=Column(JSON))` | Yes | Null when valid |
| `DraftPipeline.structure` | `dict = Field(sa_column=Column(JSON))` | No | Always has step order + strategy config |
| `DraftPipeline.compilation_errors` | `Optional[dict] = Field(default=None, sa_column=Column(JSON))` | Yes | Null when valid |

### SQLite/Postgres JSON compatibility
- SQLAlchemy's `JSON` type maps to `TEXT` on SQLite (serialized via json.dumps/loads) and native `JSONB` on Postgres
- Both backends tested in this project (see step-1 research: init_pipeline_db supports LLM_PIPELINE_DATABASE_URL for Postgres)
- No JSON path queries needed for these columns (they store blobs read/written atomically)
- GIN indexes on JSON NOT recommended since queries filter by status, not JSON contents

### JSON structure documentation (via Field description)
```python
generated_code: dict = Field(
    sa_column=Column(JSON),
    description="Generated code artifacts: {instructions: str, step: str, extractions: str | None, prompts: str | None}"
)
```

## Status Field Design

### Codebase precedent: plain string
Every status field in the project uses `str` with `max_length`:
- `PipelineRun.status`: "running", "completed", "failed" -- `Field(max_length=20, default="running")`
- `PipelineEventRecord.event_type`: free-form string, not constrained
- No `Enum` imports or usage anywhere in the project

### Recommended pattern for DraftStep
```python
status: str = Field(default="draft", max_length=20, description="draft | tested | accepted | error")
```

Valid transitions:
```
draft -> tested    (after test_results populated)
draft -> error     (validation/generation failure)
tested -> accepted (user accepts the step)
tested -> error    (re-validation fails)
error -> draft     (user re-triggers generation)
```

### Recommended pattern for DraftPipeline
```python
status: str = Field(default="draft", max_length=20, description="draft | valid | accepted | error")
```

Valid transitions:
```
draft -> valid   (compilation succeeds, task 52)
draft -> error   (compilation fails)
valid -> accepted (user accepts the pipeline)
error -> draft   (user modifies and retries)
```

### Why NOT Enum
1. Consistency -- no Enum usage in codebase
2. SQLite compat -- Enum maps to VARCHAR with CHECK constraint on Postgres but just TEXT on SQLite; inconsistent behavior
3. Flexibility -- draft lifecycle may gain states without requiring schema migration
4. Simplicity -- validation at application layer (Pydantic validator or setter logic) is sufficient

### Alternative: string Enum (document, don't enforce at DB level)
```python
from enum import StrEnum

class DraftStepStatus(StrEnum):
    DRAFT = "draft"
    TESTED = "tested"
    ACCEPTED = "accepted"
    ERROR = "error"
```
This could be used in application code for type safety without using `sa_type=Enum(...)`. However, no precedent exists in the codebase, so defer this to implementation task (50).

## Relationship Pattern: DraftPipeline -> DraftStep

### Analysis
Downstream task 52 (editor API) shows:
```python
draft = DraftPipeline(
    name=request.name,
    structure=request.pipeline_structure,  # JSON dict
    status='valid'
)
```

DraftPipeline.structure contains step references as JSON (step order, strategy config). Steps are created independently by the StepCreator meta-pipeline. Pipelines reference steps loosely by name within the JSON structure.

### Recommendation: No FK, JSON-based references

Reasons:
1. **No Relationship usage anywhere in the project** -- adding FK + Relationship() would be a pattern divergence
2. **Downstream code (task 52) already uses JSON structure** -- no FK in the sample code
3. **Lifecycle independence** -- DraftStep exists independently of any DraftPipeline. A step can be drafted without being part of a pipeline. Multiple pipelines can reference the same step by name.
4. **Loose coupling matches domain** -- pipelines reference steps by name (same as `PipelineConfig` strategies), not by DB identity

### DraftPipeline.structure JSON shape
```json
{
  "steps": ["sentiment_analysis", "topic_extraction", "summarization"],
  "strategy": "default",
  "strategy_config": {}
}
```

### If FK is ever needed (future option)
A link table `draft_pipeline_steps` could be added later without modifying existing tables:
```python
class DraftPipelineStep(SQLModel, table=True):
    __tablename__ = "draft_pipeline_steps"
    pipeline_id: int = Field(foreign_key="draft_pipelines.id", primary_key=True)
    step_id: int = Field(foreign_key="draft_steps.id", primary_key=True)
    order: int
```
This is out of scope for task 50 but documented for future reference.

## Timestamp Patterns

### created_at
Two patterns exist in the codebase:
```python
# Pattern A: shared utc_now() from state.py (used by PipelineStepState, PipelineRunInstance, PipelineRun)
from llm_pipeline.state import utc_now
created_at: datetime = Field(default_factory=utc_now)

# Pattern B: inline lambda (used by Prompt, GenerationRecord)
created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

Both produce timezone-aware UTC datetimes. Pattern A is cleaner (shared function, testable/mockable).

### Recommendation for DraftStep/DraftPipeline
Use `utc_now` from `llm_pipeline/state.py` (Pattern A). The creator/models.py module already imports from state.py indirectly, and the function is exported via `__all__`.

```python
from llm_pipeline.state import utc_now

created_at: datetime = Field(default_factory=utc_now)
updated_at: datetime = Field(default_factory=utc_now)
```

### updated_at auto-update
The only existing `updated_at` field is on `Prompt`, which uses `default_factory` (sets on INSERT only, no auto-update on UPDATE).

**Option A: Match existing Prompt pattern (application-level update)**
```python
updated_at: datetime = Field(default_factory=utc_now)
# Application code must set draft.updated_at = utc_now() before commit
```

**Option B: SQLAlchemy onupdate (auto-update on UPDATE)**
```python
from sqlalchemy import Column, DateTime
updated_at: datetime = Field(
    sa_column=Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
)
```

**Recommendation**: Option A for consistency with existing Prompt pattern. The draft lifecycle is explicitly managed (set-status calls in tasks 51/52), so application-level update is natural. The calling code already has to make explicit status changes, adding `updated_at = utc_now()` is trivial.

Note: `sa_column=Column(DateTime(timezone=True), ...)` is the correct way to get timezone-aware datetime columns in SQLAlchemy, but since the project uniformly uses `default_factory=utc_now` without specifying the column type, Python-side timezone awareness is sufficient.

## Index Considerations

### Status-based queries (primary access pattern)
Task 51 (visual editor) and task 52 (editor API) query drafts by status:
- "List all draft steps" (filter by status)
- "List pipeline drafts" (task 52: `session.query(DraftPipeline).all()`)
- "Get drafts in error state" (for retry UX)

### Recommended indexes

**DraftStep:**
```python
__table_args__ = (
    Index("ix_draft_steps_status", "status"),
    Index("ix_draft_steps_name", "name"),
)
```
- `ix_draft_steps_status`: Supports filtering by status (the primary query pattern)
- `ix_draft_steps_name`: Supports lookup by step name (referenced from DraftPipeline.structure)

**DraftPipeline:**
```python
__table_args__ = (
    Index("ix_draft_pipelines_status", "status"),
)
```
- `ix_draft_pipelines_status`: Supports status-based filtering

### Why NOT more indexes
- Low cardinality tables (tens to hundreds of rows, not millions) -- draft state is per-user/session
- No composite indexes needed until query patterns prove otherwise
- JSON columns NOT indexed (queries don't filter by JSON contents)
- `name` index on DraftStep is optional but cheap and useful for the JSON-reference lookup from DraftPipeline.structure

### Comparison with existing index patterns
| Table | Row volume | Index strategy |
|-------|-----------|----------------|
| pipeline_runs | Thousands | Composite (pipeline_name, started_at), single (status) |
| pipeline_events | Thousands-millions | Composite (run_id, event_type), single (event_type) |
| draft_steps | Tens-hundreds | Single (status), single (name) |
| draft_pipelines | Tens-hundreds | Single (status) |

Draft tables use minimal indexes because volume is low and access patterns are simple.

## Proposed Schema Summary

### DraftStep
```python
class DraftStep(SQLModel, table=True):
    __tablename__ = "draft_steps"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, description="Step name in snake_case")
    description: Optional[str] = Field(default=None, description="Human-readable step description")
    generated_code: dict = Field(
        sa_column=Column(JSON),
        description="Generated artifacts: {instructions: str, step: str, extractions: str | None, prompts: str | None}",
    )
    test_results: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    validation_errors: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    status: str = Field(default="draft", max_length=20, description="draft | tested | accepted | error")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index("ix_draft_steps_status", "status"),
        Index("ix_draft_steps_name", "name"),
    )
```

### DraftPipeline
```python
class DraftPipeline(SQLModel, table=True):
    __tablename__ = "draft_pipelines"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, description="Pipeline name in snake_case")
    structure: dict = Field(
        sa_column=Column(JSON),
        description="Pipeline structure: {steps: list[str], strategy: str, strategy_config: dict}",
    )
    compilation_errors: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    status: str = Field(default="draft", max_length=20, description="draft | valid | accepted | error")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    __table_args__ = (
        Index("ix_draft_pipelines_status", "status"),
    )
```

## Table Creation Strategy

Following the two-tier pattern from step-1 research:

### Recommended: Extend seed_prompts() or add parallel init function
```python
# In llm_pipeline/creator/prompts.py (or new creator/db.py)
def init_creator_tables(engine: Engine) -> None:
    from llm_pipeline.creator.models import GenerationRecord, DraftStep, DraftPipeline
    SQLModel.metadata.create_all(
        engine,
        tables=[GenerationRecord.__table__, DraftStep.__table__, DraftPipeline.__table__],
    )
```

This keeps creator tables out of `init_pipeline_db()` (correct -- creator is optional) while ensuring all creator tables are created together.

### Cross-cutting concern: editor routes (task 52)
Task 52's `ui` routes import DraftPipeline directly. If `ui` is installed without `creator`, the table won't exist. Two solutions:
1. Editor routes import DraftPipeline from a shared location (not creator-specific)
2. Editor routes call `init_creator_tables()` on startup

This is an implementation concern for tasks 51/52, not a schema design issue. Flag for downstream.

## File Location

**Recommended**: Add DraftStep and DraftPipeline to `llm_pipeline/creator/models.py` alongside GenerationRecord.

Rationale:
- Same domain (creator/draft lifecycle)
- Same module already has the only other creator-specific SQLModel table
- Imports follow existing pattern (`from .models import ...`)
- Consistent with codebase organization (domain-specific models in domain modules)
