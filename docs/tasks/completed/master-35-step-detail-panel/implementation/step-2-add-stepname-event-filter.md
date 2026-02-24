# IMPLEMENTATION - STEP 2: ADD STEP_NAME EVENT FILTER
**Status:** completed

## Summary
Added `step_name` optional query parameter to the events API endpoint, enabling frontend to fetch events filtered by pipeline step name.

## Files
**Created:** none
**Modified:** llm_pipeline/ui/routes/events.py
**Deleted:** none

## Changes
### File: `llm_pipeline/ui/routes/events.py`
Added `step_name: Optional[str] = None` to `EventListParams` and conditional WHERE clauses on both count and data queries.

```python
# Before (EventListParams)
class EventListParams(BaseModel):
    event_type: Optional[str] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)

# After (EventListParams)
class EventListParams(BaseModel):
    event_type: Optional[str] = None
    step_name: Optional[str] = None
    offset: int = Query(default=0, ge=0)
    limit: int = Query(default=100, ge=1, le=500)
```

```python
# Before (count query - only event_type filter)
if params.event_type is not None:
    count_stmt = count_stmt.where(...)

# After (count query - event_type + step_name filters)
if params.event_type is not None:
    count_stmt = count_stmt.where(...)
if params.step_name is not None:
    count_stmt = count_stmt.where(
        PipelineEventRecord.step_name == params.step_name
    )
```

Same pattern applied to the data query.

## Decisions
None - implementation followed plan exactly.

## Verification
[x] `step_name` param added to `EventListParams`
[x] Count query applies step_name WHERE clause when param is not None
[x] Data query applies step_name WHERE clause when param is not None
[x] No change to `EventItem` response model
[x] `PipelineEventRecord` already imported (no new imports needed)
[x] Tests pass (1 pre-existing failure in `test_events_router_prefix` unrelated to this change)
