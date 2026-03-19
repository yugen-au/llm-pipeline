# Research Step 1: Existing State Models & DB Initialization

## Existing SQLModel Tables

### Framework-level (state.py)
Three models in `llm_pipeline/state.py`, all using `SQLModel, table=True`:

1. **PipelineStepState** (`pipeline_step_states`) - Audit trail per step execution. Fields: pipeline_name, run_id, step_name, step_number, input_hash, result_data (JSON), context_snapshot (JSON), prompt keys, model, timing, token usage. Composite indexes on (run_id, step_number) and (pipeline_name, step_name, input_hash).

2. **PipelineRunInstance** (`pipeline_run_instances`) - Links created DB instances to pipeline runs (polymorphic via model_type + model_id). Indexes on run_id and (model_type, model_id).

3. **PipelineRun** (`pipeline_runs`) - Run lifecycle tracking (running/completed/failed). Fields: run_id (unique), pipeline_name, status, started_at, completed_at, step_count, total_time_ms. Indexes on (pipeline_name, started_at) and status.

### Domain-specific tables (separate modules)

4. **Prompt** (`prompts`) in `llm_pipeline/db/prompt.py` - Prompt templates. Has unique constraint on (prompt_key, prompt_type).

5. **PipelineEventRecord** (`pipeline_events`) in `llm_pipeline/events/models.py` - Persisted event records. Fields: run_id, event_type, pipeline_name, step_name, timestamp, event_data (JSON).

6. **GenerationRecord** (`creator_generation_records`) in `llm_pipeline/creator/models.py` - Tracks code generation runs. Fields: run_id, step_name_generated, files_generated (JSON), is_valid, created_at.

## Common Patterns

### Field conventions
- `id: Optional[int] = Field(default=None, primary_key=True)` for all tables
- `utc_now()` from state.py for timestamps (some use inline lambda)
- `sa_column=Column(JSON)` for dict/list fields
- `Field(max_length=N)` for string columns
- `__tablename__` explicitly set on all models
- `__table_args__` tuple with Index() objects for composite indexes
- `__all__` export list at bottom of each module

### JSON column pattern
```python
result_data: dict = Field(sa_column=Column(JSON), description="...")
# or with Optional:
test_results: Optional[dict] = Field(default=None, sa_column=Column(JSON))
```

### Imports
```python
from sqlmodel import SQLModel, Field, Column, JSON
from sqlalchemy import Index
```

## Database Initialization

### init_pipeline_db() in llm_pipeline/db/__init__.py

Explicit table list passed to `SQLModel.metadata.create_all()`:
```python
SQLModel.metadata.create_all(
    engine,
    tables=[
        PipelineStepState.__table__,
        PipelineRunInstance.__table__,
        PipelineRun.__table__,
        Prompt.__table__,
        PipelineEventRecord.__table__,
    ],
)
```

Also runs:
- `_migrate_add_columns(engine)` - ALTER TABLE for columns added after initial schema
- `add_missing_indexes(engine)` - CREATE INDEX IF NOT EXISTS for performance indexes

### Creator table creation (separate path)
GenerationRecord table is NOT in init_pipeline_db(). Created via `seed_prompts()` in `llm_pipeline/creator/prompts.py`:
```python
SQLModel.metadata.create_all(engine, tables=[GenerationRecord.__table__])
```
This is called by `StepCreatorPipeline.seed_prompts(engine)`.

### Key insight: two-tier table creation
- **Tier 1** (init_pipeline_db): Framework tables always created -- state tracking, prompts, events
- **Tier 2** (on-demand): Optional module tables created when that module is used (e.g., creator)

## Creator Module Structure

`llm_pipeline/creator/` contains:
- `models.py` - FieldDefinition, ExtractionTarget (Pydantic), GenerationRecord (SQLModel table)
- `schemas.py` - 4 Instructions + 4 Context classes for the 4-step meta-pipeline
- `pipeline.py` - StepCreatorPipeline, StepCreatorRegistry, StepCreatorAgentRegistry
- `steps.py` - 4 step classes + GenerationRecordExtraction
- `prompts.py` - Prompt seed data + seed_prompts() function
- `templates/` - Jinja2 templates for code generation
- `sandbox.py` - Docker sandbox execution
- `sample_data.py` - Sample data for testing
- `__init__.py` - Guarded import (requires jinja2), re-exports StepCreatorPipeline

Creator is an optional dependency: `pip install llm-pipeline[creator]` (requires jinja2).

## PipelineDatabaseRegistry Pattern

`PipelineDatabaseRegistry` in `registry.py` declares models at class-definition time:
```python
class StepCreatorRegistry(PipelineDatabaseRegistry, models=[GenerationRecord]):
    pass
```
This is used by pipeline execution for DB operations (save/insert), NOT for table creation. Table creation is handled separately.

## Dependencies

- `sqlmodel>=0.0.14`
- `sqlalchemy>=2.0`
- Both are core dependencies (not optional)

## Downstream Task Analysis

### Task 51 (Visual Pipeline Editor View)
- References `DraftPipeline` for draft persistence
- Frontend component, depends on task 50 tables existing

### Task 52 (Visual Editor API Endpoints)
- `POST /api/editor/compile` creates DraftPipeline with structure + compilation_errors
- `GET /api/editor/drafts` queries DraftPipeline
- Part of `ui` optional dependency, NOT `creator`
- Directly uses DraftPipeline model in endpoint code

## Architectural Decisions Needed

### 1. File placement
**Recommendation**: `llm_pipeline/creator/models.py` (already exists, DraftStep/DraftPipeline are creator-domain).
**Alternative**: `llm_pipeline/state.py` (framework-level, but these aren't framework state).

### 2. Table creation strategy
**Option A**: Add to `init_pipeline_db()` -- always created. Visual editor (task 52) queries DraftPipeline directly from `ui` routes, which is a separate optional dep from `creator`. If tables only created via creator init, editor breaks without creator installed.

**Option B**: Separate init function callable by both creator and editor. More modular but adds complexity.

**Option C**: Add to init_pipeline_db() since both DraftStep and DraftPipeline are cross-cutting (used by both creator and editor modules).

### 3. DraftPipeline <-> DraftStep relationship
Task 50 schema shows no FK between them. DraftPipeline.structure is a JSON blob ("step order, strategy config"). Two possible designs:
- **No FK**: DraftPipeline.structure contains step references as JSON (names or inline config). Simpler.
- **FK**: Add `draft_pipeline_id` on DraftStep. Enables querying "which steps belong to this draft pipeline". More relational.
