# IMPLEMENTATION - STEP 3: API ENDPOINTS + REGISTRY
**Status:** completed

## Summary
Implemented three /runs endpoints (GET list, GET detail, POST trigger) in runs.py and added pipeline_registry support to create_app().

## Files
**Created:** none (runs.py existed as stub)
**Modified:** llm_pipeline/ui/routes/runs.py, llm_pipeline/ui/app.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/runs.py`
Replaced empty stub with full endpoint implementation including:
- 6 Pydantic response/request models (RunListItem, RunListResponse, StepSummary, RunDetail, TriggerRunRequest, TriggerRunResponse)
- RunListParams query param model with validation (offset ge=0, limit ge=1 le=200)
- GET /runs: paginated list with filters (pipeline_name, status, started_after, started_before), count query for total, ordered by started_at desc
- GET /runs/{run_id}: detail with steps from PipelineStepState, 404 if not found
- POST /runs: status_code=202, registry lookup, pre-generated run_id, BackgroundTasks execution
- All sync def (not async) per plan decision
- Helper _apply_filters() to DRY filter logic between count and data queries

```
# Before
router = APIRouter(prefix="/runs", tags=["runs"])

# After
router = APIRouter(prefix="/runs", tags=["runs"])
# + 6 response models, RunListParams, _apply_filters helper
# + list_runs, get_run, trigger_run endpoints
```

### File: `llm_pipeline/ui/app.py`
Added pipeline_registry parameter and app.state assignment.

```
# Before
def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
) -> FastAPI:

# After
def create_app(
    db_path: Optional[str] = None,
    cors_origins: Optional[list] = None,
    pipeline_registry: Optional[dict] = None,
) -> FastAPI:
    # ...
    app.state.pipeline_registry = pipeline_registry or {}
```

## Decisions
### ReadOnlySession for GET endpoints
**Choice:** Use existing DBSession (ReadOnlySession) for GET endpoints; POST /runs does not need a DB session since the factory creates its own pipeline with the engine
**Rationale:** GET endpoints only read; POST delegates writes to the background task's pipeline.execute()/save() which uses its own session internally

### getattr with fallback for registry access
**Choice:** `getattr(request.app.state, "pipeline_registry", {})` in POST endpoint
**Rationale:** Defensive against apps that don't set pipeline_registry; returns empty dict so .get() returns None and raises 404

## Verification
[x] Routes register correctly (3 paths: /api/runs, /api/runs/{run_id}, /api/runs)
[x] pipeline_registry defaults to {} when not provided
[x] pipeline_registry stores provided dict when given
[x] 347 existing tests pass (1 pre-existing failure in test_retry_ratelimit_events.py due to missing google module)
[x] All endpoints are sync def (not async)
[x] Router uses prefix="/runs" with tags=["runs"], included with prefix="/api" in app

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] POST /runs background task has no error handling -- run_pipeline() closure now wrapped in try/except

### Changes Made
#### File: `llm_pipeline/ui/routes/runs.py`
Added logging import, timezone import, logger instance, and try/except in run_pipeline() closure. On failure: logs exception, attempts to mark PipelineRun as "failed" with completed_at timestamp using a fresh session from the engine.

```
# Before
def run_pipeline() -> None:
    pipeline = factory(run_id=run_id, engine=engine)
    pipeline.execute()
    pipeline.save()

# After
def run_pipeline() -> None:
    try:
        pipeline = factory(run_id=run_id, engine=engine)
        pipeline.execute()
        pipeline.save()
    except Exception:
        logger.exception("Background pipeline execution failed for run_id=%s", run_id)
        try:
            with Session(engine) as err_session:
                run = err_session.exec(
                    select(PipelineRun).where(PipelineRun.run_id == run_id)
                ).first()
                if run:
                    run.status = "failed"
                    run.completed_at = datetime.now(timezone.utc)
                    err_session.add(run)
                    err_session.commit()
        except Exception:
            logger.exception(
                "Failed to update PipelineRun status for run_id=%s", run_id
            )
```

### Verification
[x] Module imports cleanly
[x] 558 tests pass (0 failures)
[x] Error handler uses fresh Session from engine (not pipeline's possibly-broken session)
[x] Double try/except prevents status-update failure from masking original error log
