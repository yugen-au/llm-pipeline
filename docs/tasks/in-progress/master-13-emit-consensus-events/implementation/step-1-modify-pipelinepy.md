# IMPLEMENTATION - STEP 1: MODIFY PIPELINE.PY
**Status:** completed

## Summary
Added 4 consensus event emissions (ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed) to `_execute_with_consensus()` in pipeline.py. Modified method signature to accept `current_step_name`, updated call site, added all event imports.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

**Import block (L35-41):** Added 4 consensus event imports.
```python
# Before
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
    CacheLookup, CacheHit, CacheMiss, CacheReconstruction,
    LLMCallPrepared,
)

# After
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
    CacheLookup, CacheHit, CacheMiss, CacheReconstruction,
    LLMCallPrepared,
    ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed,
)
```

**Method signature (L967):** Added `current_step_name` parameter.
```python
# Before
def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls):

# After
def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls, current_step_name):
```

**ConsensusStarted (L972-979):** Emitted after `result_groups = []`, before for loop.
```python
if self._event_emitter:
    self._emit(ConsensusStarted(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=current_step_name,
        threshold=consensus_threshold,
        max_calls=maximum_step_calls,
    ))
```

**ConsensusAttempt (L992-999):** Emitted after group assignment, before threshold check.
```python
if self._event_emitter:
    self._emit(ConsensusAttempt(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=current_step_name,
        attempt=attempt + 1,
        group_count=len(result_groups),
    ))
```

**ConsensusReached (L1004-1011):** Emitted inside threshold check, before return.
```python
if self._event_emitter:
    self._emit(ConsensusReached(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=current_step_name,
        attempt=attempt + 1,
        threshold=consensus_threshold,
    ))
```

**ConsensusFailed (L1017-1023):** Emitted after loop exhausted, before return.
```python
if self._event_emitter:
    self._emit(ConsensusFailed(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=current_step_name,
        max_calls=maximum_step_calls,
        largest_group_size=len(largest_group),
    ))
```

**Call site (L639-643):** Updated to pass `current_step_name`.
```python
# Before
instruction = self._execute_with_consensus(
    call_kwargs, consensus_threshold, maximum_step_calls
)

# After
instruction = self._execute_with_consensus(
    call_kwargs, consensus_threshold, maximum_step_calls,
    current_step_name,
)
```

## Decisions
### Event emission order
**Choice:** ConsensusAttempt fires before threshold check; winning attempt emits both ConsensusAttempt then ConsensusReached
**Rationale:** CEO-validated; provides group_count progression data for all attempts including the successful one

### Guard pattern
**Choice:** `if self._event_emitter:` guard before each `self._emit()` call
**Rationale:** Matches all 13 existing emission sites in pipeline.py; established codebase convention

## Verification
[x] All 4 consensus event imports added to import block
[x] _execute_with_consensus signature includes current_step_name param
[x] ConsensusStarted emitted after result_groups init, before loop
[x] ConsensusAttempt emitted after group assignment, before threshold check
[x] ConsensusReached emitted inside threshold check, before return
[x] ConsensusFailed emitted after loop exhaustion, before return
[x] Call site updated to pass current_step_name
[x] All 205 existing tests pass (0 failures, 0 errors)
