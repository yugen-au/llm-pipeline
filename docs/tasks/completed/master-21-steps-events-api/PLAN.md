# Implement Steps and Events API Endpoints (Task 21)

## Summary

Add 4 REST endpoints across 3 files: step list and step detail in `steps.py`, context evolution in `runs.py`, and event list with pagination in `events.py`. Also update `events.py` router prefix and extend `conftest.py` with event seed data. All endpoints are DB-only, sync def, using the existing `DBSession` dependency pattern.

## Plugin & Agents

- **Plugin:** backend-development, python-development
- **Subagents:** backend-dev (route implementation), python-dev (tests)

## Phases

1. **Route Implementation**: Implement endpoints in `steps.py`, `runs.py`, and fix `events.py` prefix + implement endpoint
2. **Test Infrastructure**: Extend `conftest.py` with event seed data, create `test_steps.py` and `test_events.py`

## Architecture Decisions

### Context endpoint placement
- **Choice:** `runs.py` under path `/{run_id}/context`
- **Rationale:** Runs router has `prefix="/runs"`, so the path fits naturally. Context is a run-level aggregated view of step data. No prefix changes needed anywhere.
- **Alternatives:** steps.py with path hack -- rejected, unclean router structure

### Events data source
- **Choice:** DB-only (`PipelineEventRecord` table)
- **Rationale:** `SQLiteEventHandler` persists events near-real-time. REST GET endpoints should use durable queryable data. InMemoryEventHandler is volatile in-process, appropriate for WebSocket live streaming (task 25).
- **Alternatives:** Dual-source (InMemoryEventHandler + DB) -- rejected per CEO decision, increases scope unnecessarily

### Events pagination
- **Choice:** Optional `offset`/`limit` with defaults 0/100, matching `runs.py` pattern
- **Rationale:** A run can emit 50-200+ events. Pagination prevents large responses.
- **Alternatives:** No pagination -- rejected, inconsistent with runs.py and poor for large event sets

### `_get_run_or_404` helper
- **Choice:** Module-level function defined in `steps.py`, not extracted to shared module
- **Rationale:** Only two callers (steps.py for step list + context; events.py needs its own since it imports separately). Minimal duplication (2 files, identical 3-line helper). No shared module needed for this scale.
- **Alternatives:** Shared `helpers.py` -- over-engineering for 2 callers; each file defines its own

### Type annotation style
- **Choice:** `List[T]` from `typing` (not `list[T]`)
- **Rationale:** `runs.py` uses `List[T]` throughout (e.g. line 5 import, line 56 `List[StepSummary]`). Consistency within the file/module matters more than Python 3.11+ modernization.
- **Alternatives:** `list[T]` -- rejected for inconsistency with existing code

### Step detail 404 strategy
- **Choice:** Single query -- check step by `(run_id, step_number)`, return "Step not found" for miss
- **Rationale:** One DB query instead of two. Hits composite index `ix_pipeline_step_states_run(run_id, step_number)` directly. The step list endpoint already validates run existence separately.
- **Alternatives:** Two-query (check run first, then step) -- rejected, extra query with marginal UX benefit

## Implementation Steps

### Step 1: Implement steps.py
**Agent:** backend-development
**Skills:** none

File: `C:/Users/SamSG/Documents/claude_projects/llm-pipeline/llm_pipeline/ui/routes/steps.py`

Replace the 4-line stub with full implementation:

1. Add imports: `datetime`, `typing.Annotated`, `typing.List`, `typing.Optional`, `fastapi.APIRouter`, `fastapi.HTTPException`, `fastapi.Query`, `pydantic.BaseModel`, `sqlmodel.select`, `llm_pipeline.state.PipelineRun`, `llm_pipeline.state.PipelineStepState`, `llm_pipeline.ui.deps.DBSession`
2. Keep router: `APIRouter(prefix="/runs/{run_id}/steps", tags=["steps"])`
3. Define response models (plain `BaseModel`, not SQLModel):
   - `StepListItem`: `step_name: str`, `step_number: int`, `execution_time_ms: Optional[int] = None`, `model: Optional[str] = None`, `created_at: datetime`
   - `StepListResponse`: `items: List[StepListItem]`
   - `StepDetail`: all 13 `PipelineStepState` columns mapped to Pydantic fields (`step_name`, `step_number`, `pipeline_name`, `run_id`, `input_hash`, `result_data: dict`, `context_snapshot: dict`, `prompt_system_key: Optional[str] = None`, `prompt_user_key: Optional[str] = None`, `prompt_version: Optional[str] = None`, `model: Optional[str] = None`, `execution_time_ms: Optional[int] = None`, `created_at: datetime`)
4. Define `_get_run_or_404(db, run_id)` helper: `select(PipelineRun).where(PipelineRun.run_id == run_id)`, `db.exec(stmt).first()`, raise `HTTPException(404, "Run not found")` if None
5. Implement `GET ""` (`list_steps`):
   - Params: `run_id: str`, `db: DBSession`
   - Call `_get_run_or_404(db, run_id)`
   - Query: `select(PipelineStepState).where(run_id == run_id).order_by(step_number)`, `db.exec(stmt).all()`
   - Return `StepListResponse(items=[StepListItem(...) for s in steps])`
6. Implement `GET "/{step_number}"` (`get_step`):
   - Params: `run_id: str`, `step_number: int`, `db: DBSession`
   - Query: `select(PipelineStepState).where(run_id == run_id, step_number == step_number)`, `db.exec(stmt).first()`
   - Raise `HTTPException(404, "Step not found")` if None
   - Return `StepDetail(...)` with manual field mapping

### Step 2: Add context evolution endpoint to runs.py
**Agent:** backend-development
**Skills:** none

File: `C:/Users/SamSG/Documents/claude_projects/llm-pipeline/llm_pipeline/ui/routes/runs.py`

Append to existing file (after `trigger_run`):

1. Add 2 new response models after existing model definitions:
   - `ContextSnapshot`: `step_name: str`, `step_number: int`, `context_snapshot: dict`
   - `ContextEvolutionResponse`: `run_id: str`, `snapshots: List[ContextSnapshot]`
2. Add `GET "/{run_id}/context"` endpoint (`get_context_evolution`):
   - Params: `run_id: str`, `db: DBSession`
   - Validate run: `select(PipelineRun).where(run_id == run_id)`, raise 404 if None
   - Query: same `steps_stmt` as `get_run` -- `select(PipelineStepState).where(run_id == run_id).order_by(step_number)`
   - Return `ContextEvolutionResponse(run_id=run_id, snapshots=[ContextSnapshot(step_name=s.step_name, step_number=s.step_number, context_snapshot=s.context_snapshot) for s in steps])`
   - Note: `PipelineStepState` already imported at line 12; `List` already imported at line 5

### Step 3: Implement events.py
**Agent:** backend-development
**Skills:** none

File: `C:/Users/SamSG/Documents/claude_projects/llm-pipeline/llm_pipeline/ui/routes/events.py`

Replace the 4-line stub with full implementation:

1. Add imports: `datetime`, `typing.Annotated`, `typing.List`, `typing.Optional`, `fastapi.APIRouter`, `fastapi.HTTPException`, `fastapi.Query`, `pydantic.BaseModel`, `sqlmodel.select`, `sqlalchemy.func`, `llm_pipeline.events.models.PipelineEventRecord`, `llm_pipeline.state.PipelineRun`, `llm_pipeline.ui.deps.DBSession`
2. **Change router prefix**: `APIRouter(prefix="/runs/{run_id}/events", tags=["events"])` (was `/events`)
3. Define response models:
   - `EventItem`: `event_type: str`, `pipeline_name: str`, `run_id: str`, `timestamp: datetime`, `event_data: dict`
   - `EventListResponse`: `items: List[EventItem]`, `total: int`, `offset: int`, `limit: int`
4. Define `EventListParams(BaseModel)`: `event_type: Optional[str] = None`, `offset: int = Query(default=0, ge=0)`, `limit: int = Query(default=100, ge=1, le=500)`
5. Define `_get_run_or_404(db, run_id)` helper (same as steps.py -- local copy)
6. Implement `GET ""` (`list_events`):
   - Params: `run_id: str`, `params: Annotated[EventListParams, Depends()]`, `db: DBSession`
   - Call `_get_run_or_404(db, run_id)`
   - Count query: `select(func.count()).select_from(PipelineEventRecord).where(run_id == run_id)` + optional `event_type` filter
   - Data query: `select(PipelineEventRecord).where(run_id == run_id)` + optional filter + `.order_by(PipelineEventRecord.timestamp).offset(params.offset).limit(params.limit)`
   - Return `EventListResponse(items=[EventItem(...) for e in events], total=total, offset=params.offset, limit=params.limit)`

### Step 4: Extend conftest.py with event seed data
**Agent:** python-development
**Skills:** none

File: `C:/Users/SamSG/Documents/claude_projects/llm-pipeline/tests/ui/conftest.py`

1. Add import: `from llm_pipeline.events.models import PipelineEventRecord`
2. In `seeded_app_client` fixture, after `session.commit()` for steps, add a new `with Session(engine) as session:` block (or extend existing) with event rows:
   - `event1`: `run_id=RUN_1`, `event_type="pipeline_started"`, `pipeline_name="alpha_pipeline"`, `timestamp=_utc(-298)`, `event_data={"event_type": "pipeline_started", "run_id": RUN_1}`
   - `event2`: `run_id=RUN_1`, `event_type="step_started"`, `pipeline_name="alpha_pipeline"`, `timestamp=_utc(-297)`, `event_data={"event_type": "step_started", "run_id": RUN_1, "step_name": "step_a"}`
   - `event3`: `run_id=RUN_1`, `event_type="step_completed"`, `pipeline_name="alpha_pipeline"`, `timestamp=_utc(-294)`, `event_data={"event_type": "step_completed", "run_id": RUN_1, "step_name": "step_a"}`
   - `event4`: `run_id=RUN_1`, `event_type="pipeline_completed"`, `pipeline_name="alpha_pipeline"`, `timestamp=_utc(-291)`, `event_data={"event_type": "pipeline_completed", "run_id": RUN_1}`
   - 3 seed constants (`RUN_1`, etc.) are not defined in conftest.py -- use the literal UUIDs matching `seeded_app_client` data: `"aaaaaaaa-0000-0000-0000-000000000001"`
   - `session.add()` all 4 events, `session.commit()`

### Step 5: Create test_steps.py
**Agent:** python-development
**Skills:** none

File: `C:/Users/SamSG/Documents/claude_projects/llm-pipeline/tests/ui/test_steps.py`

1. Define constants at top: `RUN_1 = "aaaaaaaa-0000-0000-0000-000000000001"`, `RUN_2 = "aaaaaaaa-0000-0000-0000-000000000002"`, `RUN_3 = "aaaaaaaa-0000-0000-0000-000000000003"`, `NONEXISTENT = "ffffffff-0000-0000-0000-000000000099"`
2. Class `TestListSteps`:
   - `test_returns_200_with_steps_for_run1` -- expect 2 items
   - `test_steps_ordered_by_step_number_asc` -- verify ascending order
   - `test_step_fields_present` -- check `step_name`, `step_number`, `execution_time_ms`, `created_at`, `model` keys
   - `test_returns_empty_list_for_run_with_no_steps` -- RUN_3 has 0 steps
   - `test_returns_404_for_nonexistent_run`
3. Class `TestGetStep`:
   - `test_returns_200_with_full_step_detail` -- check `result_data`, `context_snapshot`, `pipeline_name`, `run_id`
   - `test_step_detail_fields_present` -- all expected fields
   - `test_returns_404_for_nonexistent_step_number`
   - `test_returns_404_for_nonexistent_run`
4. Class `TestContextEvolution`:
   - `test_returns_200_with_snapshots_for_run1` -- expect 2 snapshots
   - `test_snapshots_ordered_by_step_number_asc`
   - `test_snapshot_fields_present` -- check `step_name`, `step_number`, `context_snapshot`
   - `test_returns_empty_snapshots_for_run_with_no_steps` -- RUN_3
   - `test_returns_404_for_nonexistent_run`

### Step 6: Create test_events.py
**Agent:** python-development
**Skills:** none

File: `C:/Users/SamSG/Documents/claude_projects/llm-pipeline/tests/ui/test_events.py`

1. Define constants: `RUN_1`, `RUN_2`, `RUN_3`, `NONEXISTENT`
2. Class `TestListEvents`:
   - `test_returns_200_with_events_for_run1` -- expect 4 items (seeded above)
   - `test_events_ordered_by_timestamp_asc`
   - `test_event_fields_present` -- check `event_type`, `pipeline_name`, `run_id`, `timestamp`, `event_data`
   - `test_response_pagination_fields_present` -- check `items`, `total`, `offset`, `limit`
   - `test_total_matches_row_count`
   - `test_filter_by_event_type` -- filter `event_type=pipeline_started`, expect 1 item
   - `test_filter_by_event_type_no_match` -- filter `event_type=nonexistent_type`, expect 0 items, 200 status
   - `test_returns_empty_list_for_run_with_no_events` -- RUN_2 has no events seeded
   - `test_returns_404_for_nonexistent_run`
   - `test_pagination_limit` -- `limit=2`, expect 2 items
   - `test_pagination_offset` -- `offset=2, limit=10`, expect 2 items (events 3 and 4)
   - `test_limit_above_500_returns_422`
   - `test_negative_offset_returns_422`

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `events.py` router prefix change breaks existing `/api/events` path (if any client uses it) | Low -- stub router had no endpoints, no clients exist | Verified: events.py is a 4-line stub with no endpoints. Breaking change is safe. |
| `context_snapshot` JSON column returns None for steps without snapshots | Medium -- `StepDetail.context_snapshot: dict` would fail serialization | Seed data in conftest.py uses `{}` (empty dict), not None. Check `PipelineStepState` column default -- if nullable, use `Optional[dict] = None` in `StepDetail` and `ContextSnapshot`. Verify during implementation. |
| Duplicate `_get_run_or_404` in steps.py and events.py causes drift | Low -- helper is 3 lines, no logic | Acceptable for current scale. Can extract to `helpers.py` in a future refactor task. |
| Events query ORDER BY timestamp without covering index causes filesort | Low performance impact -- 50-200 rows per run, filesort at this cardinality is <1ms | Acceptable. No index needed for this scale. |
| `model` field in `StepListItem` conflicts with `StepSummary` in runs.py | None -- they are separate Pydantic models in separate files | `StepSummary` (runs.py lines 41-45) has no `model` field; `StepListItem` (steps.py) adds it. No conflict. |

## Success Criteria

- [ ] `GET /api/runs/{run_id}/steps` returns steps ordered by `step_number` asc, 404 for unknown run
- [ ] `GET /api/runs/{run_id}/steps/{step_number}` returns full detail with `result_data`, `context_snapshot`, 404 for missing step
- [ ] `GET /api/runs/{run_id}/context` returns ordered snapshots with `step_name`, `step_number`, `context_snapshot`
- [ ] `GET /api/runs/{run_id}/events` returns paginated events with `total`, supports `event_type` filter, 404 for unknown run
- [ ] All endpoints use sync `def`, `DBSession` dependency, plain `BaseModel` responses matching runs.py conventions
- [ ] `pytest tests/ui/test_steps.py tests/ui/test_events.py` passes (all tests green)
- [ ] `pytest tests/ui/` passes (no regressions in test_runs.py)
- [ ] No changes to `app.py` (routers already registered)
