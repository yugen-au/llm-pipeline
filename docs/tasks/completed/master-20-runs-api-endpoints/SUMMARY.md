# Task Summary

## Work Completed

Implemented REST API endpoints for pipeline run tracking in the llm-pipeline framework. Added a dedicated `PipelineRun` SQLModel table with composite indexes for <200ms pagination at 10k+ rows. Instrumented `PipelineConfig.execute()` to write run lifecycle records (running/completed/failed) on every execution. Enabled SQLite WAL mode via SQLAlchemy event listener for concurrent read safety during background writes. Implemented three FastAPI endpoints: `GET /runs` (paginated, filtered list), `GET /runs/{run_id}` (detail with steps), `POST /runs` (async trigger via BackgroundTasks). Added pipeline registry via `app.state` for POST resolution. Completed two review loops: initial review approved with 3 MEDIUM issues, all fixed in re-review loop. Final state: 31 new tests, 558 total passing, 0 regressions.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/ui/routes/runs.py` | All three /runs endpoints with Pydantic response models, filter helper, background task error handling |
| `tests/ui/__init__.py` | Package init for UI test module |
| `tests/ui/conftest.py` | Shared fixtures: app_client (empty), seeded_app_client (3 runs + steps), StaticPool for in-memory SQLite thread safety |
| `tests/ui/test_runs.py` | 23 endpoint tests covering GET /runs (filters, pagination, ordering, validation), GET /runs/{run_id} (happy path, 404, steps ordering), POST /runs (202, 404 registry miss) |
| `tests/ui/test_wal.py` | 4 WAL mode tests: file-based engine enables WAL, in-memory engine does not raise |
| `tests/test_pipeline_run_tracking.py` | 4 integration tests: PipelineRun written on success/failure, run_id preserved, pipeline_name stored |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/state.py` | Added `PipelineRun` SQLModel table with all fields, two composite indexes, docstring; removed redundant `index=True` from `PipelineStepState.run_id` and `PipelineRunInstance.run_id`; added `PipelineRun` to `__all__` |
| `llm_pipeline/db/__init__.py` | Imported `PipelineRun`; added `PipelineRun.__table__` to `create_all` tables list; added WAL event listener with `_wal_registered_engines` dedup guard; imported `event` from sqlalchemy |
| `llm_pipeline/pipeline.py` | Added `run_id: Optional[str] = None` param to `__init__`; changed `self.run_id` assignment to use injected value or generate UUID; added `PipelineRun` lazy import and lifecycle writes in `execute()` (create on start, update on success, update on failure with None-guard) |
| `llm_pipeline/ui/app.py` | Added `pipeline_registry: Optional[dict] = None` param to `create_app()`; stored on `app.state.pipeline_registry`; documented factory contract in docstring |
| `llm_pipeline/__init__.py` | Added `PipelineRun` to import line alongside `PipelineStepState`, `PipelineRunInstance`; added `"PipelineRun"` to `__all__` in State section |
| `pyproject.toml` | Added `httpx>=0.24` to `[project.optional-dependencies].dev` (required by FastAPI TestClient) |

## Commits Made

| Hash | Message |
| --- | --- |
| `f93a42b` | docs(implementation-A): master-20-runs-api-endpoints |
| `068b72c` | docs(implementation-B): master-20-runs-api-endpoints |
| `7affd8e` | docs(implementation-B): master-20-runs-api-endpoints |
| `758dd94` | docs(implementation-C): master-20-runs-api-endpoints |
| `f8aa5e4` | docs(implementation-C): master-20-runs-api-endpoints |
| `fff9f38` | docs(implementation-D): master-20-runs-api-endpoints |
| `f424ffa` | docs(fixing-review-A): master-20-runs-api-endpoints |
| `5ed16fd` | docs(fixing-review-C): master-20-runs-api-endpoints |

## Deviations from Plan

- `PipelineRun` variable scope: Plan noted declaring `pipeline_run = None` before try block with None-check in except. Implementation followed this exactly.
- WAL deduplication: Plan noted SQLAlchemy "deduplicates identical listeners on same target" as mitigation for repeated `init_pipeline_db()` calls. Review found this was incorrect (each call creates a new function object). Fix used a module-level `_wal_registered_engines: set` with `id(engine)` guard instead.
- Background task error handling: Plan described `run_pipeline()` closure calling `execute()` and `save()` with no explicit error wrapper. Review flagged this as a MEDIUM issue; fix added try/except with `logger.exception`, status-update recovery session, and inner guard against double-fault.
- `PipelineRun` top-level export: Plan did not include adding `PipelineRun` to `llm_pipeline/__init__.py`. Review flagged as MEDIUM for API consistency; fix added it alongside existing state exports.

## Issues Encountered

### WAL Listener Deduplication Incorrect in Plan
Plan stated SQLAlchemy deduplicates identical event listeners. Review found that each `init_pipeline_db()` call creates a new function object (`set_sqlite_wal`), so SQLAlchemy cannot deduplicate by identity. WAL pragma would execute N times per new connection if called N times with the same engine.

**Resolution:** Added module-level `_wal_registered_engines: set = set()` in `db/__init__.py`. Guard checks `id(engine) not in _wal_registered_engines` before registering listener. Functionally safe since engines are long-lived singletons held by `_engine` global or `app.state`.

### Background Task Silent Failure
POST /runs `run_pipeline()` closure had no error handling. If the factory callable raised, or `execute()`/`save()` raised, FastAPI BackgroundTasks would log at ERROR level but `PipelineRun.status` would remain `"running"` permanently.

**Resolution:** Wrapped `run_pipeline()` body in try/except. On exception: logs with `logger.exception` including `run_id`; opens fresh `Session(engine)` to update `PipelineRun.status="failed"` and `completed_at`; inner try/except on recovery path prevents double-fault. Handles both cases: factory raises before PipelineRun row exists (None-guard skips update) and execute/save raises after row created (status updated).

### StaticPool Required for In-Memory SQLite with TestClient
FastAPI TestClient runs in a thread pool; SQLite in-memory databases are connection-local by default. Standard `create_engine("sqlite:///:memory:")` creates an empty DB for each thread.

**Resolution:** `conftest.py` uses `StaticPool` from `sqlalchemy.pool` with `connect_args={"check_same_thread": False}` so all connections share the same in-memory database across threads.

## Success Criteria

- [x] `PipelineRun` table exists in database after `init_pipeline_db()` with all specified columns and indexes - verified by test_wal.py and seeded_app_client fixture
- [x] WAL mode is active on SQLite file-based engines after `init_pipeline_db()` - verified by test_wal.py::TestWALMode
- [x] Every `PipelineConfig.execute()` call (success or failure) writes a `PipelineRun` row - verified by tests/test_pipeline_run_tracking.py
- [x] `run_id` passed to `PipelineConfig.__init__()` is preserved in `self.run_id` and in the `PipelineRun` row - verified by test_pipeline_run_tracking.py::test_run_id_injection_preserved
- [x] `GET /api/runs` returns 200 with paginated `RunListResponse` (items, total, offset, limit) - verified by tests/ui/test_runs.py::TestListRuns
- [x] `GET /api/runs` filters by `pipeline_name`, `status`, `started_after`, `started_before` - verified by TestListRuns filter tests
- [x] `GET /api/runs/{run_id}` returns 200 with `RunDetail` including steps list ordered by `step_number` - verified by TestGetRun::test_get_run_with_steps
- [x] `GET /api/runs/{run_id}` returns 404 for unknown run_id - verified by TestGetRun::test_get_run_not_found
- [x] `POST /api/runs` returns 202 with `run_id` and `status="accepted"` for registered pipeline - verified by TestTriggerRun::test_trigger_run_accepted
- [x] `POST /api/runs` returns 404 for unregistered pipeline name - verified by TestTriggerRun::test_trigger_run_not_in_registry
- [x] All existing 484+ pytest tests continue to pass - 527 pre-existing + 31 new = 558 total, 0 regressions
- [x] New test suite passes - 31 new tests all passing
- [x] `GET /runs` query uses composite index - verified via SQLModel index definitions on `pipeline_name`+`started_at`

## Recommendations for Follow-up

1. Add UUID format validation to `GET /runs/{run_id}` path parameter via `Path(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")` to fail-fast with 422 on malformed IDs rather than processing to 404.
2. Type the `pipeline_registry` parameter as `Optional[Dict[str, Callable[..., Any]]]` or define a `PipelineFactory` Protocol with explicit `(run_id: str, engine: Engine)` signature to make the factory contract enforceable at type-check time.
3. Add a comment to `tests/test_pipeline_run_tracking.py` `tracking_engine` fixture explaining why `SQLModel.metadata.create_all(engine)` is used instead of the `init_pipeline_db()` pattern with explicit `tables=[]`, to prevent copy-paste of the global create_all pattern into production code.
4. Consider adding a `GET /runs/{run_id}/steps` endpoint as a dedicated paginated step listing endpoint for pipelines with large step counts (current RunDetail embeds all steps inline).
5. Consider a cleanup/retention policy for `PipelineRun` rows - at very high execution volumes (thousands of runs/day) the table will grow unbounded; a background pruning job or TTL-based deletion endpoint would be needed.
6. The `POST /runs` factory contract (callable taking `run_id` and `engine` kwargs) is documented only in the `create_app()` docstring. A dedicated section in the framework README or docs would help consuming applications implement the pattern correctly.
