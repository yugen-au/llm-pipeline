# IMPLEMENTATION - STEP 3: IMPLEMENT EVENTS.PY
**Status:** completed

## Summary
Replaced 4-line events.py stub with full events list endpoint. Changed router prefix from `/events` to `/runs/{run_id}/events`. Implemented paginated event listing with optional `event_type` filter, querying `PipelineEventRecord` table.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/events.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/events.py`
Replaced stub with full implementation: response models (EventItem, EventListResponse), query params model (EventListParams), `_get_run_or_404` helper, and `list_events` endpoint with count+data queries.

```
# Before
"""Pipeline events route module."""
from fastapi import APIRouter

router = APIRouter(prefix="/events", tags=["events"])

# After
Full implementation with:
- Router prefix changed to "/runs/{run_id}/events"
- EventItem model: event_type, pipeline_name, run_id, timestamp, event_data
- EventListResponse model: items, total, offset, limit
- EventListParams: event_type filter, offset (default 0, ge=0), limit (default 100, ge=1, le=500)
- _get_run_or_404 helper (local copy, same pattern as steps.py)
- GET "" (list_events): validates run, count query with optional event_type WHERE, data query ordered by timestamp with offset/limit
```

## Decisions
### Count query includes event_type filter
**Choice:** Apply event_type WHERE clause to both count and data queries
**Rationale:** `total` must reflect filtered count, not all events for the run. Matches runs.py pattern where count_stmt includes all applied filters.

### Pagination defaults
**Choice:** offset=0, limit=100, max 500
**Rationale:** Plan specifies these values. Higher default than runs.py (50) because events are lighter-weight records. Max 500 prevents oversized responses.

## Verification
[x] Import succeeds (`from llm_pipeline.ui.routes.events import router`)
[x] Router prefix is `/runs/{run_id}/events`
[x] All 27 existing UI tests pass (no regressions)
[x] No changes to app.py (router already registered)
[x] Uses sync def, DBSession dependency, plain BaseModel responses
[x] Uses `List[T]` style (consistent with runs.py)
[x] Count query includes event_type WHERE clause when filter provided
[x] Data query ordered by PipelineEventRecord.timestamp

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] LOW: `_get_run_or_404` missing docstring in events.py (steps.py has `"""Return run or raise 404."""`)

### Changes Made
#### File: `llm_pipeline/ui/routes/events.py`
Added docstring to `_get_run_or_404` for consistency with steps.py.
```
# Before
def _get_run_or_404(db: DBSession, run_id: str) -> PipelineRun:
    stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)

# After
def _get_run_or_404(db: DBSession, run_id: str) -> PipelineRun:
    """Return run or raise 404."""
    stmt = select(PipelineRun).where(PipelineRun.run_id == run_id)
```

### Verification
[x] Docstring matches steps.py exactly
[x] Import still succeeds
