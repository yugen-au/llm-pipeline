# IMPLEMENTATION - STEP 4: EXTEND CONFTEST.PY WITH EVENT SEEDS
**Status:** completed

## Summary
Added PipelineEventRecord import and 4 event seed rows for RUN_1 in seeded_app_client fixture. RUN_2 and RUN_3 intentionally have no events for empty-result test cases.

## Files
**Created:** none
**Modified:** tests/ui/conftest.py
**Deleted:** none

## Changes
### File: `tests/ui/conftest.py`
Added import for PipelineEventRecord and a new Session block after step seeds with 4 event rows.

```
# Before
from llm_pipeline.state import PipelineRun, PipelineStepState
# ... steps commit, then directly TestClient

# After
from llm_pipeline.state import PipelineRun, PipelineStepState
from llm_pipeline.events.models import PipelineEventRecord
# ... steps commit, then new Session block with 4 events, then TestClient
```

Events seeded (all for RUN_1 / alpha_pipeline):
- evt1: pipeline_started, timestamp=_utc(-298)
- evt2: step_started, timestamp=_utc(-297), step_name=step_a
- evt3: step_completed, timestamp=_utc(-294), step_name=step_a
- evt4: pipeline_completed, timestamp=_utc(-291)

## Decisions
### Separate Session block for events
**Choice:** New `with Session(engine) as session:` block after steps commit
**Rationale:** Plan specified "after session.commit() for steps, add a new with Session block". Keeps concerns separated and avoids modifying existing seed data block.

## Verification
[x] Import resolves correctly (verified with python -c)
[x] All 23 existing test_runs.py tests pass (no regressions)
[x] Event timestamps are chronologically ordered (-298, -297, -294, -291)
[x] Event timestamps fit within RUN_1's started_at(-300) to completed_at(-290) window
[x] RUN_2 and RUN_3 have no events (confirmed by not adding any)
[x] event_data dicts contain at minimum event_type and run_id fields
