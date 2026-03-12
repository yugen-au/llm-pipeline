# IMPLEMENTATION - STEP 7: TESTS
**Status:** completed

## Summary
Created tests/test_validators.py (29 tests covering not_found_validator and array_length_validator factories). Added TestBuildStepAgentValidators class (5 tests) to tests/test_agent_registry_core.py covering validators param and validation_context wiring.

## Files
**Created:** tests/test_validators.py
**Modified:** tests/test_agent_registry_core.py
**Deleted:** none

## Changes
### File: `tests/test_validators.py`
New file. 29 tests across two classes.

TestNotFoundValidator (17 tests):
- default indicators match (not found, no data, n/a, none, unknown, case-insensitive)
- custom indicators match; custom replaces defaults
- non-matching passes through; empty string passes
- non-string returns unchanged (int, None, BaseModel)
- ModelRetry raised on match; message contains output
- DEFAULT_NOT_FOUND_INDICATORS constant not mutated

TestArrayLengthValidator (12 tests):
- no-op when ctx.deps.array_validation is None
- correct length passes through
- length mismatch raises ModelRetry with counts in message
- no reorder when allow_reordering=False
- reordering with allow_reordering=True; returns model_copy (not same instance)
- strip_number_prefix matches stripped keys against input_array
- filter_empty_inputs reduces effective count; mismatch still raises
- empty array_field_name raises ValueError at runtime

### File: `tests/test_agent_registry_core.py`
Added TestBuildStepAgentValidators class (5 tests):
- test_validators_param_accepted: empty list, no error
- test_validators_none_accepted: None default, no error
- test_validators_registered: dummy validator in agent._output_validators
- test_multiple_validators_registered_in_order: two validators, index order preserved
- test_validation_context_wired: agent._validation_context is not None and callable

## Decisions
### RunContext construction
**Choice:** Construct real RunContext(deps=..., model=MagicMock(), usage=RunUsage()) rather than MagicMocking RunContext entirely.
**Rationale:** Validators access ctx.deps directly; real RunContext ensures attribute access works correctly without patching internals.

### asyncio event loop
**Choice:** asyncio.new_event_loop().run_until_complete() per call.
**Rationale:** asyncio.get_event_loop() triggers DeprecationWarning on Python 3.10+; new_event_loop() is clean per test.

### validator internals inspection
**Choice:** Check agent._output_validators and v.function to find registered callables.
**Rationale:** pydantic-ai wraps validators in an internal object with .function attribute; this is the stable inspection path for tests.

## Verification
[x] 29 tests in test_validators.py all pass
[x] 5 new tests in test_agent_registry_core.py all pass (82 total in those two files)
[x] Full suite: 837 passed, 1 pre-existing failure (test_events_router_prefix unrelated), 6 skipped
[x] No new failures introduced
[x] Commit: 73860020
