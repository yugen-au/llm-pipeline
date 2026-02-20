# Research Summary

## Executive Summary

Validated two research files against actual codebase for task 21 (Steps and Events API Endpoints). All DB model schemas, query patterns, router registrations, test infrastructure, and dependency injection patterns confirmed correct. Three architectural ambiguities surfaced and resolved via CEO input: events use DB-only source (no InMemoryEventHandler), context endpoint lives in runs.py, events get optional pagination. One internal contradiction between research files (step-1 said DB-only, step-2 proposed dual-source) resolved by CEO decision aligning with step-1. Minor inaccuracies documented below (non-blocking).

## Domain Findings

### Route Patterns & Registration
**Source:** step-1, step-2

- `runs.py`: `APIRouter(prefix="/runs", tags=["runs"])` -- confirmed at line 17
- `steps.py` stub: `APIRouter(prefix="/runs/{run_id}/steps", tags=["steps"])` -- confirmed, 4 lines total
- `events.py` stub: `APIRouter(prefix="/events", tags=["events"])` -- confirmed, must change to `prefix="/runs/{run_id}/events"`
- All routers registered in `app.py` lines 64-69 with `prefix="/api"` -- no app.py changes needed
- Sync `def` endpoints (not `async def`) -- confirmed pattern in runs.py line 101 comment. FastAPI wraps in threadpool. Correct for sync SQLite backend.

### Database Models
**Source:** step-1

All columns, types, and indexes verified against source:

- `PipelineStepState` (`llm_pipeline/state.py` lines 24-103): All 13 columns match research exactly. Indexes `ix_pipeline_step_states_run(run_id, step_number)` and `ix_pipeline_step_states_cache(pipeline_name, step_name, input_hash)` confirmed.
- `PipelineEventRecord` (`llm_pipeline/events/models.py` lines 16-55): All 6 columns match. Indexes `ix_pipeline_events_run_event(run_id, event_type)` and `ix_pipeline_events_type(event_type)` confirmed.
- `PipelineRun` (`llm_pipeline/state.py` lines 144-178): Confirmed for run existence validation (404 guard).
- `PipelineEventRecord.__table__` is in `init_pipeline_db()` create_all list (`db/__init__.py` line 79) -- table exists in test DB via `_make_app()`.

### Dependency Injection
**Source:** step-1

- `DBSession = Annotated[ReadOnlySession, Depends(get_db)]` in `deps.py` line 27 -- confirmed
- `get_db()` creates `Session(engine)`, wraps in `ReadOnlySession`, closes in finally -- confirmed lines 10-24
- ReadOnlySession allows: `exec`, `execute`, `scalar`, `scalars`, `query`, `get` -- confirmed
- ReadOnlySession blocks: `add`, `add_all`, `delete`, `flush`, `commit`, `merge`, `refresh`, `expire`, `expire_all`, `expunge`, `expunge_all` -- confirmed (research omitted `expire_all` and `expunge_all`, non-impactful)

### Query Patterns
**Source:** step-1, step-2

Verified against runs.py implementation:
- Count: `select(func.count()).select_from(Model)` with `.where()` -- runs.py lines 112-114
- Data: `select(Model).where(...).order_by(...).offset(...).limit(...)` -- runs.py lines 117-124
- Execute: `db.exec(stmt).all()` -- runs.py line 125
- Scalar: `db.scalar(count_stmt)` -- runs.py line 114
- 404: `HTTPException(status_code=404, detail="...")` -- runs.py line 152
- Manual model-to-response mapping (no ORM serialization) -- runs.py lines 127-143

### Response Model Patterns
**Source:** step-1, step-2

Verified against runs.py:
- All response/request models are plain `BaseModel` (not SQLModel) -- confirmed
- List responses use wrapper with `items`, `total`, `offset`, `limit` -- `RunListResponse` lines 34-38
- Optional fields: `Optional[T] = None` -- confirmed throughout
- runs.py uses `List[T]` from typing (not `list[T]`) -- research step-2 section 4 claims `list[T]`, actual code uses `List[T]`. New code should follow existing `List[T]` for consistency within this codebase.

### Test Infrastructure
**Source:** step-1, step-2

Verified against `tests/ui/conftest.py`:
- `_make_app()`: FastAPI + `StaticPool` in-memory SQLite with `check_same_thread=False` -- confirmed lines 18-56
- `app_client` fixture: empty DB -- confirmed lines 59-62
- `seeded_app_client` fixture: 3 PipelineRun rows + 3 PipelineStepState rows -- confirmed lines 67-142
- Seeded data matches: RUN_1 (completed, alpha, 2 steps), RUN_2 (failed, beta, 1 step), RUN_3 (running, alpha, 0 steps)
- No PipelineEventRecord rows seeded yet -- extension needed for events tests
- Test patterns in `test_runs.py`: class-based groups (`TestListRuns`, `TestGetRun`, `TestTriggerRun`), constants for run IDs at top, assert status codes + body structure -- confirmed

### Existing StepSummary Model
**Source:** runs.py (not in research)

Important: runs.py already defines `StepSummary` (lines 41-45) with fields: `step_name`, `step_number`, `execution_time_ms`, `created_at`. It does NOT include `model`. Research step-2 proposes `StepListItem` with `model` field added -- this is a new addition to the step summary, not matching existing `StepSummary`. The new `StepListItem` in steps.py can include `model` without conflicting since it's a separate response model.

### Events Handler API
**Source:** step-2, verified against `events/handlers.py`

InMemoryEventHandler API confirmed (lines 84-136):
- `get_events(run_id=...)` returns `list[dict]` -- confirmed line 110
- `get_events_by_type(event_type, run_id=...)` returns `list[dict]` -- confirmed line 122
- Thread-safe via `threading.Lock` -- confirmed line 103
- **NOT USED**: Per CEO decision, events endpoint is DB-only. InMemoryEventHandler details documented for reference only; task 25 (WebSocket) is the appropriate consumer.

SQLiteEventHandler confirmed (lines 139-179):
- Session-per-emit with commit -- events persisted near-real-time
- Uses `PipelineEventRecord` model directly

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Events data source: DB-only or dual-source (InMemoryEventHandler + DB)? Step-1 says DB-only, step-2 proposes dual-source, task spec says "InMemoryEventHandler (active) or pipeline_events (persisted)". | DB-only. SQLiteEventHandler persists near-real-time. Task 25 handles WebSocket/live events. Keep task 21 scope clean. | Eliminates dual-source pattern from step-2 section 3. No need to wire InMemoryEventHandler into trigger_run or add app.state.active_event_handlers. Removes `source` field from EventListResponse. Simplifies implementation significantly. |
| Context endpoint placement: runs.py or steps.py? steps.py prefix is `/runs/{run_id}/steps`, context path `/runs/{run_id}/context` doesn't fit. | runs.py. Context is a run-level resource, /runs/{run_id}/context fits naturally under /runs prefix, no prefix changes needed. | Context endpoint goes in runs.py alongside get_run. steps.py implements only step list and step detail. No router prefix changes needed for steps.py. |
| Events pagination: yes or no? Task spec silent on it. | Yes, optional offset/limit. Consistent with existing runs.py pattern. | Events endpoint gets `offset` (default 0) and `limit` (default 100) query params matching runs.py conventions. Count query needed for `total` field. |

## Assumptions Validated

- [x] `PipelineStepState` schema matches research table (13 columns, 2 indexes) -- verified against `state.py` lines 24-103
- [x] `PipelineEventRecord` schema matches research table (6 columns, 2 indexes) -- verified against `events/models.py` lines 16-55
- [x] `pipeline_events` table created by `init_pipeline_db()` -- verified in `db/__init__.py` line 79
- [x] steps.py stub exists with correct prefix `/runs/{run_id}/steps` -- verified, 4-line file
- [x] events.py stub exists with prefix `/events` (needs change to `/runs/{run_id}/events`) -- verified, 4-line file
- [x] All routers already registered in app.py -- no app.py changes needed -- verified lines 64-69
- [x] Sync def endpoints correct for SQLite backend -- confirmed pattern and reasoning
- [x] `DBSession` type alias works with `Annotated[ReadOnlySession, Depends(get_db)]` -- verified deps.py
- [x] ReadOnlySession allows exec/execute/scalar/scalars/query/get -- verified readonly.py
- [x] `seeded_app_client` fixture has 3 runs + 3 steps, no events -- verified conftest.py
- [x] Index `ix_pipeline_step_states_run(run_id, step_number)` covers step list ORDER BY and step detail WHERE -- verified state.py line 101
- [x] Index `ix_pipeline_events_run_event(run_id, event_type)` covers events filtered and unfiltered queries -- verified events/models.py line 53
- [x] `StepSummary` in runs.py does not include `model` field -- verified runs.py lines 41-45; new `StepListItem` in steps.py can add it without conflict
- [x] InMemoryEventHandler is thread-safe (threading.Lock) -- verified handlers.py line 103; but NOT USED per CEO decision
- [x] Task 25 (WebSocket) depends on task 21 and handles live event streaming -- verified via get_task; clean scope boundary

## Open Items

- `_get_run_or_404` helper: shared between steps.py and runs.py (context endpoint). Decide during planning whether to extract to a shared module or duplicate in each route file. Runs.py currently inlines the check (lines 149-152).
- `List[T]` vs `list[T]`: runs.py uses `List[T]` from typing. Research recommends `list[T]` (Python 3.11+). Decide during planning which to use for new code (consistency vs modernization).
- Events `event_type` filter with pagination: when both `event_type` and `offset/limit` are provided, the count query must include the `event_type` WHERE clause. Same pattern as `_apply_filters` in runs.py.
- Events ordering: research says `ORDER BY timestamp`. PipelineEventRecord has `timestamp` column (datetime, default utc_now). No index on `(run_id, timestamp)` -- ordering uses `ix_pipeline_events_run_event(run_id, event_type)` prefix for run_id filter but needs filesort for timestamp ordering. Acceptable for 50-200 rows per run but worth noting.

## Recommendations for Planning

1. **Implement 4 endpoints across 2 files**: steps.py (step list, step detail), runs.py (context evolution), events.py (event list with pagination and event_type filter).
2. **Events endpoint is DB-only**: Query `PipelineEventRecord` table. No InMemoryEventHandler integration. No `source` field in response. No app.state changes.
3. **Context endpoint in runs.py**: Add `GET /{run_id}/context` alongside existing `get_run`. Path fits naturally under `/runs` prefix.
4. **Events pagination**: Add `offset`/`limit` query params with defaults (0, 100) and `total` count in response, matching runs.py `RunListResponse` pattern.
5. **Seed PipelineEventRecord rows**: Extend `seeded_app_client` in conftest.py with event rows for RUN_1 (multiple event types) and optionally RUN_2. Import `PipelineEventRecord` from `llm_pipeline.events.models`.
6. **Follow existing code style**: Use `List[T]` from typing (matching runs.py), sync `def` endpoints, plain `BaseModel` response models, manual model-to-response mapping, `HTTPException` for 404s.
7. **Step detail 404 strategy**: Use single-query approach (Option A from step-2 section 2) -- check step existence only, "Step not found" covers both missing run and missing step. Step list endpoint validates run separately.
8. **Test structure**: Class-based groups (`TestListSteps`, `TestGetStep`, `TestContextEvolution`, `TestListEvents`), reuse `RUN_1`/`RUN_2`/`RUN_3` constants from test_runs.py pattern.
9. **Performance**: All endpoints well within <100ms target. Step detail is single-row composite index lookup (~1-2ms). Events list is index scan on run_id (~10-30ms for 200 rows).
