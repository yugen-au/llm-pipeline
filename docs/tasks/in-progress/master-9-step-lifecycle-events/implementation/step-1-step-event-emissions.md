# IMPLEMENTATION - STEP 1: STEP EVENT EMISSIONS
**Status:** completed

## Summary
Added 5 step lifecycle event emissions (StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted) to the execute() step loop in pipeline.py. Extended the import at L35 to include all 5 step event types. All emissions use the `if self._event_emitter:` guard pattern established by Task 8.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

**Import extension (L35-38):** Added 5 step event types to existing import.
```python
# Before
from llm_pipeline.events.types import PipelineStarted, PipelineCompleted, PipelineError

# After
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
)
```

**StepSelecting (L462-469):** Emitted at for loop start, before step_num increment. Fields: step_index, strategy_count.

**StepSelected (L492-499):** Emitted after current_step_name set, before should_skip check. Fields: step_name, step_number, strategy_name.

**StepSkipped (L503-510):** Emitted inside should_skip branch, after logger.info, before _executed_steps.add. Fields: step_name, step_number, reason="should_skip returned True".

**StepStarted (L531-539):** Emitted between end of logging block and step_start capture. Fields: step_name, step_number, system_key, user_key.

**StepCompleted (L617-624):** Emitted before _executed_steps.add, after both cached and fresh paths converge. Fields: step_name, step_number, execution_time_ms (float).

## Decisions
### execution_time_ms as float
**Choice:** Used `(datetime.now(timezone.utc) - step_start).total_seconds() * 1000` without int() cast
**Rationale:** Plan specifies float, StepCompleted dataclass types it as float. Differs from _save_step_state which uses int().

### StepCompleted timing separate from _save_step_state
**Choice:** StepCompleted computes its own execution_time_ms at emission point
**Rationale:** StepCompleted emits for both cached and fresh paths; _save_step_state only runs on fresh path. Cannot reuse its variable.

## Verification
[x] All 5 step events imported at L35-38
[x] StepSelecting emitted at L462-469, guarded
[x] StepSelected emitted at L492-499, guarded
[x] StepSkipped emitted at L503-510, guarded, reason="should_skip returned True"
[x] StepStarted emitted at L531-539, guarded
[x] StepCompleted emitted at L617-624, guarded, execution_time_ms as float
[x] All 110 existing tests pass (pytest -x -q)

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] MEDIUM - StepCompleted execution_time_ms on cached path: added inline comment near emission explaining timing includes cache-lookup or LLM-call depending on path, CEO-approved design
[x] LOW - StepSelecting without StepSelected: added docstring note to StepSelecting class explaining consumers should handle receiving StepSelecting without subsequent StepSelected

### Changes Made
#### File: `llm_pipeline/pipeline.py`
Added inline comment above StepCompleted emission.
```python
# Before
                if self._event_emitter:
                    self._emit(StepCompleted(

# After
                if self._event_emitter:
                    # Timing includes cache-lookup or LLM-call depending on path;
                    # CEO-approved: step_start stays after logging block (L541).
                    self._emit(StepCompleted(
```

#### File: `llm_pipeline/events/types.py`
Extended StepSelecting docstring with consumer guidance.
```python
# Before
    """Emitted when step selection begins. step_name defaults to None."""

# After
    """Emitted when step selection begins. step_name defaults to None.

    Note: Consumers should handle receiving StepSelecting without a subsequent
    StepSelected -- this occurs when no strategy provides a step at the given
    step_index, causing the loop to break before selection completes.
    """
```

### Verification
[x] All 118 tests pass (pytest -x -q)
[x] Comment is brief and references CEO decision
[x] Docstring note explains the edge case for consumers
