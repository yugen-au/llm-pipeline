# IMPLEMENTATION - STEP 3: INTEGRATION TESTS
**Status:** completed

## Summary
Created comprehensive integration tests for LLM call events (LLMCallPrepared, LLMCallStarting, LLMCallCompleted) covering happy path, error path, event pairing/ordering, and zero-overhead when no emitter configured. 32 tests across 7 test classes, all passing.

## Files
**Created:** tests/events/test_llm_call_events.py
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/events/test_llm_call_events.py`
New file with 7 test classes and 32 test methods:

- **TestLLMCallPrepared** (6 tests): verifies emission per step, call_count=1, system_key, user_key, run_id, step_name
- **TestLLMCallStarting** (5 tests): verifies emission per call, rendered_system_prompt is str (not key), rendered_user_prompt contains "Process: test", call_index=0, ordering before Completed
- **TestLLMCallCompleted** (7 tests): verifies emission per call, raw_response="mock response", parsed_result is dict, model_name="mock-model", attempt_count=1, empty validation_errors, call_index=0
- **TestLLMCallEventPairing** (5 tests): verifies Starting/Completed call_index match, timestamp ordering, total event count (6 = 2 steps * 3 events), per-step ordering (Prepared->Starting->Completed), consistent run_id
- **TestLLMCallErrorPath** (7 tests): verifies Completed emitted on exception, raw_response=None, parsed_result=None, validation_errors contains "Mock provider failure", Starting still emitted, Starting/Completed paired, model_name=None
- **TestNoEmitterZeroOverhead** (2 tests): verifies pipeline runs without emitter, monkeypatch spy confirms no event params injected into call_kwargs

## Decisions
### Test structure follows existing patterns
**Choice:** Mirrored test_step_lifecycle_events.py structure (class per event type, shared helper, conftest fixtures)
**Rationale:** Consistency with existing event test suite. Uses same MockProvider, SuccessPipeline, seeded_session, in_memory_handler fixtures.

### Monkeypatch spy for zero-overhead test
**Choice:** Used monkeypatch to spy on execute_llm_step kwargs rather than just verifying execution succeeds
**Rationale:** Actively verifies event_emitter is NOT injected into call_kwargs when no emitter configured, confirming zero overhead at the injection point.

## Verification
[x] All 32 new tests pass
[x] All 150 total tests pass (no regressions)
[x] TestLLMCallPrepared: call_count, system_key, user_key verified
[x] TestLLMCallStarting: rendered prompts are strings (not template keys), contain rendered content
[x] TestLLMCallCompleted: raw_response, parsed_result, model_name, attempt_count verified
[x] TestLLMCallEventPairing: call_index matching, timestamp ordering, total count correct
[x] TestLLMCallErrorPath: Completed emitted with error data on provider exception
[x] TestNoEmitterZeroOverhead: no event params injected without emitter
