# Task Summary

## Work Completed

Implemented 4 read-only REST endpoints across 3 route files to expose step execution details, context evolution, and pipeline events via the existing FastAPI UI. All endpoints follow established `runs.py` patterns: sync `def`, `DBSession` (ReadOnlySession wrapper), plain `pydantic.BaseModel` responses, `List[T]` typing style. No changes to `app.py` (routers were already registered). A fix round resolved 3 review issues before final approval.

## Files Changed

### Created
| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/routes/steps.py` | Step list + step detail endpoints; was a 4-line stub |
| `tests/ui/test_steps.py` | 14 tests: TestListSteps (5), TestGetStep (4), TestContextEvolution (5) |
| `tests/ui/test_events.py` | 13 tests: TestListEvents covering pagination, filtering, 404, and validation |

### Modified
| File | Changes |
| --- | --- |
| `llm_pipeline/ui/routes/runs.py` | Added `ContextSnapshot` + `ContextEvolutionResponse` models; added `GET /{run_id}/context` endpoint |
| `llm_pipeline/ui/routes/events.py` | Full rewrite of stub: changed router prefix from `/events` to `/runs/{run_id}/events`; added `EventItem`, `EventListResponse`, `EventListParams` models; implemented paginated `GET ""` with optional `event_type` filter and count query |
| `tests/ui/conftest.py` | Added `PipelineEventRecord` import; added 4 seeded event rows for RUN_1 in a new session block |

## Commits Made

| Hash | Message |
| --- | --- |
| `486680c` | docs(implementation-A): master-21-steps-events-api |
| `d599ac8` | docs(implementation-A): master-21-steps-events-api |
| `be13488` | docs(implementation-B): master-21-steps-events-api |
| `f2e9f24` | docs(implementation-B): master-21-steps-events-api |
| `19310e8` | docs(fixing-review-A): master-21-steps-events-api |
| `e7cf419` | docs(fixing-review-B): master-21-steps-events-api |

## Deviations from Plan

- `get_step` endpoint in `steps.py` was initially implemented with a single query on `(run_id, step_number)` per the plan's performance rationale. After review raised this as a medium issue (missing run returned "Step not found" instead of "Run not found"), a pre-query call to `_get_run_or_404` was added, making the 404 messages distinct. This is a minor scope addition beyond the original plan.
- `test_steps.py` initially included an unused `import pytest` (not specified in the plan). Removed during the fix round.

## Issues Encountered

### Medium: `get_step` returned generic "Step not found" for nonexistent run
**Resolution:** Added `_get_run_or_404(db, run_id)` call at the top of `get_step` before the step query. Missing run now returns "Run not found"; missing step number returns "Step not found". Test `test_returns_404_for_nonexistent_run` in `TestGetStep` updated to assert `detail == "Run not found"`.

### Low: Unused `import pytest` in test_steps.py
**Resolution:** Removed the import. No pytest fixtures or marks were used in that file.

### Low: `_get_run_or_404` docstring missing in events.py
**Resolution:** Added `"""Return run or raise 404."""` docstring to match the identical helper in `steps.py`.

## Success Criteria

- [x] `GET /api/runs/{run_id}/steps` returns steps ordered by `step_number` asc, 404 for unknown run -- verified by TestListSteps (5 tests)
- [x] `GET /api/runs/{run_id}/steps/{step_number}` returns full detail with `result_data`, `context_snapshot`, 404 for missing step and missing run -- verified by TestGetStep (4 tests)
- [x] `GET /api/runs/{run_id}/context` returns ordered snapshots with `step_name`, `step_number`, `context_snapshot` -- verified by TestContextEvolution (5 tests)
- [x] `GET /api/runs/{run_id}/events` returns paginated events with `total`, supports `event_type` filter, 404 for unknown run -- verified by TestListEvents (13 tests)
- [x] All endpoints use sync `def`, `DBSession` dependency, plain `BaseModel` responses matching `runs.py` conventions
- [x] `pytest tests/ui/test_steps.py tests/ui/test_events.py` passes -- 27/27 green
- [x] `pytest tests/ui/` passes with no regressions -- 54/54 green (27 new + 27 existing)
- [x] No changes to `app.py` (routers already registered)

## Recommendations for Follow-up

1. Extract `_get_run_or_404` to a shared `llm_pipeline/ui/routes/helpers.py` module -- currently duplicated identically in `steps.py` and `events.py`; acceptable at current scale but will drift if the helper evolves.
2. Add a covering index on `(run_id, timestamp)` for `PipelineEventRecord` if event volume per run grows beyond a few hundred rows -- current filesort is <1ms at low cardinality but degrades linearly.
3. Task 25 (WebSocket live streaming) should wire `InMemoryEventHandler` for in-flight events; the DB-only REST endpoints implemented here serve durable historical queries and complement rather than replace live streaming.
4. Consider `Optional[dict]` for `context_snapshot` in `StepDetail` and `ContextSnapshot` if `PipelineStepState.context_snapshot` can be NULL in production runs -- current seed data uses `{}` so this was not encountered in testing.
