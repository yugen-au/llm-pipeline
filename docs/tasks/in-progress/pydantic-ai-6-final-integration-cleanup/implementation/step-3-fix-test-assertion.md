# IMPLEMENTATION - STEP 3: FIX TEST ASSERTION
**Status:** completed

## Summary
Fixed pre-existing test_events_router_prefix failure by updating expected prefix from "/events" to "/runs/{run_id}/events" to match actual router definition.

## Files
**Created:** none
**Modified:** tests/test_ui.py
**Deleted:** none

## Changes
### File: `tests/test_ui.py`
Updated assertion on line 143 and docstring on line 141 to match actual router prefix.
```
# Before
    def test_events_router_prefix(self):
        """events router has prefix /events."""
        from llm_pipeline.ui.routes.events import router as r
        assert r.prefix == "/events"

# After
    def test_events_router_prefix(self):
        """events router has prefix /runs/{run_id}/events."""
        from llm_pipeline.ui.routes.events import router as r
        assert r.prefix == "/runs/{run_id}/events"
```

## Decisions
None

## Verification
[x] Confirmed actual router prefix at llm_pipeline/ui/routes/events.py:14 is "/runs/{run_id}/events"
[x] Verified via `python -c "from llm_pipeline.ui.routes.events import router; print(repr(router.prefix))"` outputs '/runs/{run_id}/events'
[x] Graphiti memory confirms this was a known pre-existing failure (prefix mismatch)
