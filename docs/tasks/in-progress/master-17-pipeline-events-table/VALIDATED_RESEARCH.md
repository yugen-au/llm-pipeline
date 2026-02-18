# Research Summary

## Executive Summary

Both research files independently confirmed the same finding: `PipelineEventRecord` already exists at `llm_pipeline/events/models.py` with a complete, convention-compliant schema. Task 17's original spec (create `PipelineEvent` in `state.py`) is outdated. The actual scope reduces to two integration changes: (1) add `PipelineEventRecord.__table__` to `init_pipeline_db()`, (2) export from `__init__.py`. All research claims verified against source code.

Three gaps identified that research did not address: export chain completeness, docstring update, and init_pipeline_db()-specific testing.

## Domain Findings

### Model Existence and Correctness
**Source:** step-1-existing-codebase-analysis.md, step-2-schema-design-research.md

- `PipelineEventRecord` at `llm_pipeline/events/models.py:16` is complete and tested (tests in `tests/events/test_handlers.py`)
- Name `PipelineEvent` is taken by the frozen dataclass base in `events/types.py:58` -- `PipelineEventRecord` naming is intentional
- Schema: 5 fields + PK (id, run_id, event_type, pipeline_name, timestamp, event_data)
- `pipeline_name` field is extra vs task 17 spec but is a positive deviation (matches dataclass shape, enables filtering)
- Composite index `(run_id, event_type)` is superior to task 17 spec's separate indexes (leftmost prefix serves run_id-only queries)
- All conventions verified: `Optional[int]` PK, `utc_now` factory, `sa_column=Column(JSON)`, `ix_{tablename}_{suffix}` index naming, snake_case plural tablename

### init_pipeline_db() Integration
**Source:** step-1-existing-codebase-analysis.md, step-2-schema-design-research.md

- `llm_pipeline/db/__init__.py:58-65` uses explicit `tables=[...]` list with 3 tables; `PipelineEventRecord` missing
- `SQLiteEventHandler.__init__()` at `handlers.py:158-159` independently creates the table (idempotent, safe to keep)
- Import chain verified safe: `db/__init__.py -> events/models.py -> state.py` -- no circular dependency risk

### Export Chain Gap (not covered by research)
**Source:** validator analysis of `events/__init__.py`, `handlers.py`, `__init__.py`

- `events/__init__.py` does NOT export `PipelineEventRecord` (it exports all event types and emitters but not the persistence model)
- `events/handlers.py` includes `PipelineEventRecord` in its `__all__` but `events/__init__.py` doesn't re-export it
- `llm_pipeline/__init__.py` has no `PipelineEventRecord` import or `__all__` entry
- Decision needed on whether to add to `events/__init__.py`, `llm_pipeline/__init__.py`, or both

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
| Should PipelineEventRecord be exported from events/__init__.py in addition to llm_pipeline/__init__.py? | pending | Determines import chain and public API surface |

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

## Open Items

- Export chain: should PipelineEventRecord be added to `events/__init__.py` as well, or only to `llm_pipeline/__init__.py`?
- init_pipeline_db() docstring must mention PipelineEventRecord after integration
- New test needed: verify init_pipeline_db() creates pipeline_events table (not just SQLiteEventHandler)

## Recommendations for Planning

1. Scope is minimal: 2 file changes (db/__init__.py, llm_pipeline/__init__.py), possibly 3 if adding to events/__init__.py
2. Use direct import `from llm_pipeline.events.models import PipelineEventRecord` in db/__init__.py (consistent with how Prompt is imported from db/prompt.py)
3. Add PipelineEventRecord to events/__init__.py for API completeness (persistence model should be accessible from the events subpackage)
4. Add PipelineEventRecord to llm_pipeline/__init__.py under a new "Events" section in __all__ (it's not a "State" model)
5. Update init_pipeline_db() docstring to include PipelineEventRecord
6. Write test: call init_pipeline_db() with in-memory engine, verify pipeline_events table exists via sqlite_master query
7. Task 50 should follow exact same integration pattern established here
