# Research Summary

## Executive Summary

Both research files independently confirmed the same finding: `PipelineEventRecord` already exists at `llm_pipeline/events/models.py` with a complete, convention-compliant schema. Task 17's original spec (create `PipelineEvent` in `state.py`) is outdated. The actual scope reduces to three integration changes: (1) add `PipelineEventRecord.__table__` to `init_pipeline_db()`, (2) export from `events/__init__.py`, (3) export from `llm_pipeline/__init__.py`. All research claims verified against source code.

Three gaps identified that research did not address: export chain completeness (now resolved), docstring update, and init_pipeline_db()-specific testing.

## Domain Findings

### Model Existence and Correctness
**Source:** step-1-existing-codebase-analysis.md, step-2-schema-design-research.md

- `PipelineEventRecord` at `llm_pipeline/events/models.py:16` is complete and tested (tests in `tests/events/test_handlers.py`)
- Name `PipelineEvent` is taken by the frozen dataclass base in `events/types.py:58` -- `PipelineEventRecord` naming is intentional and avoids collision
- Schema: 5 fields + PK (id, run_id, event_type, pipeline_name, timestamp, event_data)
- `pipeline_name` field is extra vs task 17 spec but is a positive deviation (matches dataclass shape, enables filtering)
- Composite index `(run_id, event_type)` is superior to task 17 spec's separate indexes (leftmost prefix serves run_id-only queries)
- All conventions verified: `Optional[int]` PK, `utc_now` factory, `sa_column=Column(JSON)`, `ix_{tablename}_{suffix}` index naming, snake_case plural tablename

### init_pipeline_db() Integration
**Source:** step-1-existing-codebase-analysis.md, step-2-schema-design-research.md

- `llm_pipeline/db/__init__.py:58-65` uses explicit `tables=[...]` list with 3 tables; `PipelineEventRecord` missing
- `SQLiteEventHandler.__init__()` at `handlers.py:158-159` independently creates the table (idempotent, safe to keep)
- Import chain verified safe: `db/__init__.py -> events/models.py -> state.py` -- no circular dependency risk

### Export Chain (resolved)
**Source:** validator analysis of `events/__init__.py`, `handlers.py`, `llm_pipeline/__init__.py`

- `events/__init__.py` does NOT currently export `PipelineEventRecord`
- `events/handlers.py` includes `PipelineEventRecord` in its `__all__` but `events/__init__.py` doesn't re-export it
- `llm_pipeline/__init__.py` has no `PipelineEventRecord` import or `__all__` entry
- **CEO decision:** Export from BOTH `events/__init__.py` AND `llm_pipeline/__init__.py`

### Docstring Gap (not covered by research)
**Source:** validator analysis of `db/__init__.py:37-45`

- `init_pipeline_db()` docstring says "Creates PipelineStepState, PipelineRunInstance, and Prompt tables"
- Must be updated after adding PipelineEventRecord

### Test Gap (not covered by research)
**Source:** validator analysis of `tests/events/test_handlers.py`

- Existing tests cover PipelineEventRecord via `SQLiteEventHandler`'s own `create_all` call
- No test verifies `init_pipeline_db()` creates the `pipeline_events` table
- Task 17 testStrategy specifically calls for "Test table creation with init_pipeline_db()"

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Should PipelineEventRecord be exported from events/__init__.py in addition to llm_pipeline/__init__.py? | YES - export from BOTH levels for maximum accessibility (CEO decision) | 3 files changed instead of 2; cleaner public API |

## Assumptions Validated

- [x] PipelineEventRecord is the correct model; no separate PipelineEvent SQLModel needed (name collision with dataclass base)
- [x] Model location in events/models.py is correct (not state.py as task spec suggests)
- [x] Schema follows all codebase conventions (PK, utc_now, JSON column, indexes, tablename)
- [x] Composite index (run_id, event_type) is superior to spec's separate indexes
- [x] pipeline_name field is a positive deviation from spec (enables filtering)
- [x] init_pipeline_db() needs PipelineEventRecord.__table__ added to tables list
- [x] SQLiteEventHandler's independent create_all is idempotent and safe to keep
- [x] No circular import risk in the proposed import chain
- [x] No dependency version changes needed
- [x] Task 50 (downstream) follows same pattern, confirming precedent
- [x] Export from both events/__init__.py and llm_pipeline/__init__.py (CEO approved)

## Open Items

None. All questions resolved.

## Implementation Checklist (for planning phase)

### File: `llm_pipeline/db/__init__.py`
1. Add import: `from llm_pipeline.events.models import PipelineEventRecord`
2. Add `PipelineEventRecord.__table__` to the `tables=[...]` list in `init_pipeline_db()`
3. Update docstring: mention PipelineEventRecord/pipeline_events table

### File: `llm_pipeline/events/__init__.py`
4. Add import: `from llm_pipeline.events.models import PipelineEventRecord`
5. Add `"PipelineEventRecord"` to `__all__`

### File: `llm_pipeline/__init__.py`
6. Add import: `from llm_pipeline.events.models import PipelineEventRecord`
7. Add `"PipelineEventRecord"` to `__all__`

### File: new test (e.g., `tests/test_db_init.py` or added to existing db tests)
8. Test: call `init_pipeline_db()` with in-memory SQLite engine, verify `pipeline_events` table exists
9. Test: verify indexes exist on the created table
10. Test: insert and query PipelineEventRecord via init_pipeline_db()-created engine
