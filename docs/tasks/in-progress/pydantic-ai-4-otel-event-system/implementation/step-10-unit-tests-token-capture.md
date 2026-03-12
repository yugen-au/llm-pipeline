# IMPLEMENTATION - STEP 10: UNIT TESTS TOKEN CAPTURE
**Status:** completed

## Summary
Created tests/test_token_tracking.py with 28 unit tests covering token capture, event enrichment, instrumentation settings threading, consensus token aggregation, and null/zero usage edge cases.

## Files
**Created:** tests/test_token_tracking.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/test_token_tracking.py`
New test file with 7 test classes covering all plan requirements:

- `TestLLMCallCompletedTokens` (4 tests): per-call input_tokens, output_tokens, total_tokens on LLMCallCompleted events; None when usage() returns None
- `TestStepCompletedTokens` (2 tests): step-aggregate tokens on StepCompleted; 0 when usage() returns None (accumulators start at 0, total_requests increments unconditionally)
- `TestPipelineStepStateTokens` (5 tests): DB record has input_tokens, output_tokens, total_tokens, total_requests; 0 when no usage data
- `TestConsensusTokenAggregation` (7 tests): consensus sums across attempts; total_requests = call count; per-call events have individual tokens; failed consensus still accumulates
- `TestNullAndZeroUsage` (4 tests): None usage no crash; zero usage stores 0; zero usage events carry 0; None usage consensus no crash
- `TestNoInstrumentationSettings` (2 tests): pipeline works without instrumentation; build_step_agent called with instrument=None
- `TestInstrumentationSettingsThreading` (4 tests): build_step_agent receives instrument; Agent constructor receives/omits instrument kwarg; stored on pipeline

## Decisions
### None-usage yields 0, not None
**Choice:** Tests assert 0 (not None) for StepCompleted/StepState tokens when usage() returns None
**Rationale:** `_step_total_requests += 1` runs unconditionally after run_sync, so the `_step_total_requests > 0` guard passes, yielding accumulator values of 0. This is correct behavior -- a call was made, it just didn't report usage.

### Patch path for build_step_agent
**Choice:** Patch `llm_pipeline.agent_builders.build_step_agent` not `llm_pipeline.pipeline.build_step_agent`
**Rationale:** build_step_agent is imported locally inside execute() via `from llm_pipeline.agent_builders import`, so the function lives on the agent_builders module at patch time.

### Agent constructor tests via pydantic_ai.Agent patch
**Choice:** Use `patch.object(pydantic_ai, "Agent")` for Agent constructor tests
**Rationale:** Agent is imported locally inside build_step_agent via `from pydantic_ai import Agent`, so patching at the pydantic_ai module level intercepts the local import.

## Verification
[x] All 28 new tests pass
[x] All 628 existing tests pass (excluding pre-existing test_ui.py failure)
[x] No hardcoded values
[x] Error handling present (null/zero usage edge cases covered)

## Review Fix Iteration 0
**Issues Source:** REVIEW.md
**Status:** fixed

### Issues Addressed
[x] (LOW) _mock_usage helper duplicated across test files -- consolidated into tests/conftest.py

### Changes Made
#### File: `tests/conftest.py`
Created root-level conftest with shared `_mock_usage(input_tokens=10, output_tokens=5)` helper.
```
# Before
(file did not exist)

# After
def _mock_usage(input_tokens=10, output_tokens=5):
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.requests = 1
    return usage
```

#### File: `tests/events/conftest.py`
Replaced inline `_mock_usage()` definition with import from root conftest.
```
# Before
def _mock_usage():
    usage = MagicMock()
    usage.input_tokens = 10
    usage.output_tokens = 5
    usage.requests = 1
    return usage

# After
from tests.conftest import _mock_usage
```

#### File: `tests/test_token_tracking.py`
Replaced inline `_mock_usage()` definition with import; updated `_make_run_result_zero_usage` to use shared helper.
```
# Before
def _mock_usage(input_tokens=10, output_tokens=5):
    ...

# After
from tests.conftest import _mock_usage
```

### Verification
[x] All 28 token tracking tests pass
[x] All 412 events + token tracking tests pass
[x] All 628 tests pass (excluding pre-existing test_ui.py failure)
