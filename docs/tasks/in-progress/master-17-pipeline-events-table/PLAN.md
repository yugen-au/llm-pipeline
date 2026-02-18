# PLANNING

## Summary

`PipelineEventRecord` already exists in `llm_pipeline/events/models.py`. Task 17 reduces to three integration changes: add `PipelineEventRecord.__table__` to `init_pipeline_db()`, export from `events/__init__.py`, export from `llm_pipeline/__init__.py`. A new test file covers `init_pipeline_db()` creating the `pipeline_events` table (not tested anywhere today).

## Plugin & Agents

**Plugin:** backend-development
**Subagents:** [available agents]
**Skills:** none

## Phases

1. **Integration**: Wire `PipelineEventRecord` into `init_pipeline_db()` and both export layers
2. **Testing**: New test file for `init_pipeline_db()` + `pipeline_events` table verification

## Architecture Decisions

### Use Explicit Table List in init_pipeline_db()

**Choice:** Add `PipelineEventRecord.__table__` to the existing `tables=[...]` list in `init_pipeline_db()` rather than switching to `SQLModel.metadata.create_all(engine)` (no tables filter).

**Rationale:** Existing pattern in `db/__init__.py:60-64` is explicit allowlist. Task 50 (downstream) will add `DraftStep.__table__` and `DraftPipeline.__table__` the same way, confirming the pattern is intentional. Metadata-wide create_all would create any imported SQLModel table accidentally.

**Alternatives:** `SQLModel.metadata.create_all(engine)` -- rejected; too broad, breaks isolation.

### Export from Both events/__init__.py and llm_pipeline/__init__.py

**Choice:** Add `PipelineEventRecord` to `__all__` and imports in both `events/__init__.py` and `llm_pipeline/__init__.py`.

**Rationale:** CEO decision. `events/__init__.py` follows the same re-export pattern already used for all other event types. `llm_pipeline/__init__.py` already exports `PipelineStepState` and `PipelineRunInstance` (the analogous DB models), so `PipelineEventRecord` belongs alongside them.

**Alternatives:** Export only from top-level -- rejected by CEO.

### Test File Location

**Choice:** New file `tests/test_init_pipeline_db.py` at the top-level tests directory.

**Rationale:** No existing db-specific test file exists. `tests/events/test_handlers.py` tests `SQLiteEventHandler`'s own `create_all` (different code path). The new tests target `init_pipeline_db()` specifically, which lives in `llm_pipeline/db/`, not the events subpackage. Top-level test directory matches similar integration-level tests (`test_pipeline.py`).

**Alternatives:** Add to `tests/events/test_handlers.py` -- rejected; mixes responsibilities, wrong module under test.

## Implementation Steps

### Step 1: Integrate PipelineEventRecord into init_pipeline_db()

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo
**Group:** A

1. In `llm_pipeline/db/__init__.py`, add import: `from llm_pipeline.events.models import PipelineEventRecord` alongside existing state imports (line 15-16).
2. Add `PipelineEventRecord.__table__` to the `tables=[...]` list in `init_pipeline_db()` (after `Prompt.__table__`, line 63).
3. Update the docstring of `init_pipeline_db()` (line 39): change "Creates PipelineStepState, PipelineRunInstance, and Prompt tables" to also mention `PipelineEventRecord` / `pipeline_events` table.

### Step 2: Export PipelineEventRecord from events/__init__.py

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/events/__init__.py`, add import from `llm_pipeline.events.models`: `from llm_pipeline.events.models import PipelineEventRecord`. Insert after the `emitter` import (line 73), before `resolve_event` alias.
2. Add `"PipelineEventRecord"` to `__all__` under the `# Base Classes` section or a new `# DB Models` comment grouping, after `"StepScopedEvent"`.

### Step 3: Export PipelineEventRecord from llm_pipeline/__init__.py

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/__init__.py`, add import: `from llm_pipeline.events.models import PipelineEventRecord`. Insert after `from llm_pipeline.state import PipelineStepState, PipelineRunInstance` (line 17).
2. Add `"PipelineEventRecord"` to `__all__` under the `# State` section alongside `"PipelineStepState"` and `"PipelineRunInstance"`.

### Step 4: Add init_pipeline_db() Integration Tests

**Agent:** [plugin:subagent]
**Skills:** none
**Context7 Docs:** /websites/sqlmodel_tiangolo
**Group:** C

1. Create `tests/test_init_pipeline_db.py`.
2. Add test: call `init_pipeline_db()` with an in-memory SQLite engine (`create_engine("sqlite://")`), inspect `engine.dialect.has_table(conn, "pipeline_events")` -- assert table exists.
3. Add test: verify indexes on `pipeline_events` -- inspect `sqlalchemy.inspect(engine).get_indexes("pipeline_events")` and assert `ix_pipeline_events_run_id_event_type` is present.
4. Add test: insert a `PipelineEventRecord` row via a `Session` and query it back -- assert round-trip correctness of `run_id`, `event_type`, `pipeline_name`, `event_data`.
5. Each test uses a fresh in-memory engine (no shared state); clean up with `engine.dispose()`.

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Circular import: `db/__init__.py` -> `events/models.py` -> other modules | High | VALIDATED_RESEARCH.md confirms no circular dependency in this chain; verified by tracing `events/models.py` imports (only `state.py`, `SQLModel`, stdlib) |
| `SQLiteEventHandler.create_all` and `init_pipeline_db()` both create `pipeline_events` -- double-creation | Low | SQLAlchemy `create_all` is idempotent (`CREATE TABLE IF NOT EXISTS`); no data loss, no error |
| Test engine state bleeds between tests | Low | Each test function creates its own `sqlite://` in-memory engine and disposes it after |
| Task 50 imports `DraftStep`/`DraftPipeline` before they exist | Low | Out of scope; task 50 is downstream (pending) and not imported here |

## Success Criteria

- [ ] `init_pipeline_db()` creates `pipeline_events` table when called with a fresh engine
- [ ] `from llm_pipeline.events import PipelineEventRecord` resolves without error
- [ ] `from llm_pipeline import PipelineEventRecord` resolves without error
- [ ] `PipelineEventRecord` present in `llm_pipeline.events.__all__`
- [ ] `PipelineEventRecord` present in `llm_pipeline.__all__`
- [ ] `init_pipeline_db()` docstring mentions `pipeline_events` / `PipelineEventRecord`
- [ ] All 3 new tests in `tests/test_init_pipeline_db.py` pass
- [ ] Existing tests (`pytest`) continue to pass with no regressions

## Phase Recommendation

**Risk Level:** low
**Reasoning:** All changes are additive (new import, list entry, export). No existing logic altered. Model and schema already exist and are tested. No migration needed (SQLite create_all is idempotent). Circular import risk verified absent by research.
**Suggested Exclusions:** testing, review
