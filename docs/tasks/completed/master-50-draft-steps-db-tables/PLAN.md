# PLANNING

## Summary
Add `DraftStep` and `DraftPipeline` SQLModel table definitions to `llm_pipeline/state.py`, register them in `init_pipeline_db()` in `llm_pipeline/db/__init__.py`, export from `llm_pipeline/__init__.py`, and add integration tests covering table creation, CRUD, JSON serialization, and status transitions. These tables provide cross-session persistence for the pipeline creator UI (downstream tasks 51/52).

## Plugin & Agents
**Plugin:** backend-development, database-design
**Subagents:** [available agents]
**Skills:** none

## Phases
1. Model definitions: Add DraftStep and DraftPipeline to state.py
2. DB registration: Import and register new tables in init_pipeline_db()
3. Package exports: Add new models to llm_pipeline/__init__.py __all__
4. Tests: Integration tests for table creation, CRUD, JSON, unique constraint, status transitions

## Architecture Decisions

### FK: Plain String run_id (No SQLAlchemy Enforcement)
**Choice:** `run_id: Optional[str]` stored without `foreign_key` kwarg on DraftStep
**Rationale:** `GenerationRecord.__tablename__` is `"creator_generation_records"` (not `"generation_records"` as referenced in research). Also, `GenerationRecord.run_id` has no unique constraint, making it an invalid SQLAlchemy FK target. All existing cross-table references in this codebase use plain strings (loose coupling pattern). CEO intent (traceability) is preserved without enforced referential integrity.
**Alternatives:** `generation_record_id: Optional[int]` FK to `creator_generation_records.id` PK - would work but changes the field semantics; adding unique constraint to GenerationRecord.run_id - out of scope for this task.

### Unique Constraint Implementation
**Choice:** `UniqueConstraint('name', name='uq_draft_steps_name')` in `__table_args__` for both models
**Rationale:** CEO decision - re-generation UPDATEs existing row. UniqueConstraint in `__table_args__` (not `Field(unique=True)`) matches `PipelineRun.run_id` pattern which uses `unique=True` in Field; however for composite `__table_args__` dict containing Index + UniqueConstraint, the tuple form is required. Since DraftStep has indexes too, both go in `__table_args__` as a tuple.
**Alternatives:** `Field(unique=True)` on name - simpler but can't coexist with Index entries in same `__table_args__` tuple cleanly; functionally equivalent, use UniqueConstraint for explicit naming.

### Status Field
**Choice:** `status: str = Field(default='draft', max_length=20)` on both models, valid values: draft/tested/accepted/error
**Rationale:** No Enum usage anywhere in codebase - plain str with max_length matches PipelineRun.status pattern exactly. Values documented in field description.
**Alternatives:** Python Enum - not used in codebase, avoided for consistency.

### Table Creation Location
**Choice:** Add `DraftStep.__table__` and `DraftPipeline.__table__` to the existing `tables=[...]` list in `init_pipeline_db()`
**Rationale:** CEO decision; both models in state.py (core, no optional deps), so import is clean. Matches how PipelineStepState, PipelineRunInstance, PipelineRun are handled.
**Alternatives:** Separate `init_creator_db()` - rejected by CEO.

## Implementation Steps

### Step 1: Add DraftStep and DraftPipeline to state.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /sqlmodel/sqlmodel, /sqlalchemy/sqlalchemy
**Group:** A

1. Open `llm_pipeline/state.py`
2. Add `UniqueConstraint` to the sqlalchemy import line (alongside `Index`)
3. After the `PipelineRun` class (before `__all__`), add `DraftStep` SQLModel class with:
   - `__tablename__ = "draft_steps"`
   - `id: Optional[int] = Field(default=None, primary_key=True)`
   - `name: str = Field(max_length=100)`
   - `description: Optional[str] = Field(default=None)`
   - `generated_code: dict = Field(sa_column=Column(JSON))` (required JSON)
   - `test_results: Optional[dict] = Field(default=None, sa_column=Column(JSON))`
   - `validation_errors: Optional[dict] = Field(default=None, sa_column=Column(JSON))`
   - `status: str = Field(default='draft', max_length=20)` with description "draft, tested, accepted, error"
   - `run_id: Optional[str] = Field(default=None, max_length=36)` (no foreign_key - plain string traceability link to creator_generation_records.run_id)
   - `created_at: datetime = Field(default_factory=utc_now)`
   - `updated_at: datetime = Field(default_factory=utc_now)`
   - `__table_args__` tuple: `UniqueConstraint('name', name='uq_draft_steps_name')`, `Index('ix_draft_steps_status', 'status')`, `Index('ix_draft_steps_name', 'name')`
4. After `DraftStep`, add `DraftPipeline` SQLModel class with:
   - `__tablename__ = "draft_pipelines"`
   - `id: Optional[int] = Field(default=None, primary_key=True)`
   - `name: str = Field(max_length=100)`
   - `structure: dict = Field(sa_column=Column(JSON))` (required JSON - references step names as strings)
   - `compilation_errors: Optional[dict] = Field(default=None, sa_column=Column(JSON))`
   - `status: str = Field(default='draft', max_length=20)` with description "draft, tested, accepted, error"
   - `created_at: datetime = Field(default_factory=utc_now)`
   - `updated_at: datetime = Field(default_factory=utc_now)`
   - `__table_args__` tuple: `UniqueConstraint('name', name='uq_draft_pipelines_name')`, `Index('ix_draft_pipelines_status', 'status')`
5. Add `DraftStep` and `DraftPipeline` to `__all__` in state.py

### Step 2: Register tables in init_pipeline_db()
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /sqlmodel/sqlmodel
**Group:** B

1. Open `llm_pipeline/db/__init__.py`
2. Update the import from `llm_pipeline.state` to include `DraftStep, DraftPipeline`
3. Add `DraftStep.__table__` and `DraftPipeline.__table__` to the `tables=[...]` list in `init_pipeline_db()`
4. Update the docstring of `init_pipeline_db()` to mention draft_steps and draft_pipelines tables

### Step 3: Export from package __init__.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Open `llm_pipeline/__init__.py`
2. Update the `from llm_pipeline.state import ...` line to include `DraftStep, DraftPipeline`
3. Add `"DraftStep"` and `"DraftPipeline"` to `__all__` in the `# State` section

### Step 4: Add integration tests
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** /pytest-dev/pytest
**Group:** C

1. Create `tests/test_draft_tables.py`
2. Follow the pattern from `tests/test_init_pipeline_db.py` (in-memory SQLite engine, class-per-concern)
3. `TestDraftStepTableCreation` class:
   - `test_table_creation`: `init_pipeline_db()` creates `draft_steps` table
   - `test_index_creation`: `draft_steps` has `ix_draft_steps_status` and `ix_draft_steps_name` indexes
   - `test_unique_constraint_on_name`: inserting two DraftStep rows with same name raises IntegrityError
4. `TestDraftPipelineTableCreation` class:
   - `test_table_creation`: `init_pipeline_db()` creates `draft_pipelines` table
   - `test_index_creation`: `draft_pipelines` has `ix_draft_pipelines_status` index
   - `test_unique_constraint_on_name`: inserting two DraftPipeline rows with same name raises IntegrityError
5. `TestDraftStepCRUD` class:
   - `test_insert_and_retrieve`: insert DraftStep with generated_code JSON dict, retrieve and assert field equality
   - `test_json_serialization`: generated_code, test_results, validation_errors store and retrieve nested dict correctly
   - `test_optional_json_fields_nullable`: DraftStep with only required fields (name, generated_code) inserts without error; test_results and validation_errors are None
   - `test_run_id_optional`: DraftStep with run_id=None and with run_id="some-uuid" both insert correctly
   - `test_status_transitions`: insert with status='draft', update to 'tested', 'accepted', verify 'accepted' persists
6. `TestDraftPipelineCRUD` class:
   - `test_insert_and_retrieve`: insert DraftPipeline with structure JSON dict, retrieve and assert field equality
   - `test_json_serialization`: structure and compilation_errors store and retrieve nested dict correctly
   - `test_optional_json_fields_nullable`: DraftPipeline with only required fields (name, structure) inserts; compilation_errors is None
   - `test_status_transitions`: insert with status='draft', update to 'error', verify compilation_errors storable at same time

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| SQLModel metadata shared across all tests - another test's table registration may bleed into state | Low | Use `create_engine("sqlite://")` in-memory per test; all tests already follow this pattern |
| `updated_at` not auto-updated on UPDATE (application-managed, not DB trigger) | Low | Matches existing Prompt model pattern; downstream tasks must set updated_at explicitly; document in field description |
| DraftStep.run_id has no FK enforcement - stale run_ids possible | Low | Matches codebase loose-coupling pattern; CEO decision was for traceability not enforcement |
| UniqueConstraint in __table_args__ tuple alongside Index entries - syntax must be a tuple not dict | Low | PipelineRun uses dict form (only one entry); DraftStep/DraftPipeline use tuple form (multiple entries) - verify correct tuple syntax in SQLModel |

## Success Criteria
- [ ] `draft_steps` table created by `init_pipeline_db()` with in-memory SQLite engine
- [ ] `draft_pipelines` table created by `init_pipeline_db()` with in-memory SQLite engine
- [ ] `DraftStep` and `DraftPipeline` importable from `llm_pipeline` top-level
- [ ] `DraftStep` and `DraftPipeline` importable from `llm_pipeline.state`
- [ ] UniqueConstraint on name enforced (IntegrityError on duplicate name insert)
- [ ] JSON columns (generated_code, structure) correctly store and retrieve nested dicts
- [ ] Optional JSON columns (test_results, validation_errors, compilation_errors) default to None
- [ ] DraftStep.run_id stores arbitrary string without FK errors
- [ ] Status field accepts all four values: draft, tested, accepted, error
- [ ] All new tests pass with `pytest tests/test_draft_tables.py`
- [ ] Existing tests unaffected (`pytest` full suite passes)

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Pure additive change - new models and table registrations only. No modification to existing models, no schema migration needed, no breaking changes. The only non-trivial decision (FK vs plain string) is well-understood and documented. Pattern is well-established in codebase.
**Suggested Exclusions:** testing, review
