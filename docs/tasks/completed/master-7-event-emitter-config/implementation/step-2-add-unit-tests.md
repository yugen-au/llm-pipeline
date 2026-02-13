# IMPLEMENTATION - STEP 2: ADD UNIT TESTS
**Status:** completed

## Summary
Added 5 unit tests for event_emitter parameter and _emit() method on PipelineConfig. Created MockEmitter stub class that captures events. All 37 tests pass (32 existing + 5 new).

## Files
**Created:** none
**Modified:** tests/test_pipeline.py
**Deleted:** none

## Changes
### File: `tests/test_pipeline.py`
Added import for PipelineEventEmitter, PipelineEvent, PipelineStarted from llm_pipeline.events. Added MockEmitter class and TestEventEmitter test class with 5 test cases.

```
# Before (imports)
from llm_pipeline.types import StepCallParams

# After (imports)
from llm_pipeline.types import StepCallParams
from llm_pipeline.events import PipelineEventEmitter, PipelineEvent, PipelineStarted
```

```
# After (end of file) - new test infrastructure and tests
class MockEmitter:
    def __init__(self):
        self.events: List[PipelineEvent] = []
    def emit(self, event: PipelineEvent) -> None:
        self.events.append(event)

class TestEventEmitter:
    - test_no_emitter_defaults_to_none: verifies _event_emitter is None when omitted
    - test_emitter_stored: verifies _event_emitter is the passed mock instance
    - test_emit_noop_when_none: _emit() with None emitter does not raise
    - test_emit_forwards_to_emitter: _emit() forwards event to mock's emit()
    - test_mock_emitter_satisfies_protocol: isinstance(mock, PipelineEventEmitter) is True
```

## Decisions
### Test event type choice
**Choice:** Used PipelineStarted as concrete event for _emit() tests
**Rationale:** Simplest event type (only run_id + pipeline_name required), no step_name or extra fields needed

### MockEmitter as plain class (not unittest.mock)
**Choice:** Plain class with events list instead of unittest.mock.Mock
**Rationale:** Matches plan's specification for "mock/stub emitter class that captures emitted events in a list". More readable and explicit for protocol satisfaction test.

## Verification
[x] All 37 tests pass (pytest -v)
[x] 5 new tests cover all specified cases from plan step 2
[x] MockEmitter satisfies PipelineEventEmitter protocol (runtime isinstance check)
[x] Backwards compatibility: all 32 existing tests unchanged and passing
