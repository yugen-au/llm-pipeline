# IMPLEMENTATION - STEP 3: CREATE EVENT TESTS
**Status:** completed

## Summary
Created `tests/events/test_ctx_state_events.py` with 9 test classes covering all 4 new event types (InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved) across fresh and cached paths.

## Files
**Created:** `tests/events/test_ctx_state_events.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `tests/events/test_ctx_state_events.py`
New file. 9 test classes, ~380 lines.

Inline additions:
- `EmptyContextInstructions` / `EmptyContextStep` / `EmptyContextStrategy` / `EmptyContextRegistry` / `EmptyContextStrategies` / `EmptyContextPipeline` -- step that returns `None` from `process_instructions`, used for `TestContextUpdatedEmptyContext`

Helpers:
- `_run_fresh(seeded_session, handler)` -- SuccessPipeline, `use_cache=False`
- `_run_cached(seeded_session, handler)` -- SuccessPipeline x2, clears handler between runs
- `_run_empty_ctx_fresh(seeded_session, handler)` -- EmptyContextPipeline, `use_cache=False`
- `_ctx_state_events(events)` -- filter helper

Test classes:
1. `TestInstructionsStoredFreshPath` -- 6 tests
2. `TestInstructionsStoredCachedPath` -- 4 tests
3. `TestInstructionsLoggedFreshPath` -- 6 tests
4. `TestInstructionsLoggedCachedPath` -- 4 tests
5. `TestContextUpdatedFreshPath` -- 8 tests
6. `TestContextUpdatedEmptyContext` -- 4 tests (new_keys==[], CEO decision)
7. `TestStateSavedFreshPath` -- 9 tests
8. `TestStateSavedNotOnCachedPath` -- 2 tests
9. `TestCtxStateZeroOverhead` -- 3 tests

## Decisions
### EmptyContextStep inline vs conftest
**Choice:** Defined inline in test file
**Rationale:** PLAN.md says "add inline or to conftest". No structural change to conftest needed; single-use class only relevant to this test file.

### SuccessPipeline for main tests
**Choice:** Reuse existing `SuccessPipeline` (2x SimpleStep) from conftest
**Rationale:** Already has seeded prompts, 2 steps give richer assertion coverage (2 InstructionsStored events per run).

### StateSaved with use_cache=False
**Choice:** `_run_fresh` uses `use_cache=False`; StateSaved tests use `_run_fresh`
**Rationale:** `_save_step_state` called on fresh (non-cached) path regardless of `use_cache` flag. `input_hash` computed at L555 unconditionally.

## Verification
- [x] `EmptyContextInstructions` naming follows convention (`EmptyContext` prefix + `Instructions`)
- [x] `step_name` for EmptyContextStep = `empty_context` (CamelCase->snake_case, strip 'Step')
- [x] `input_hash` always computed (L555, before use_cache branch) -- non-empty on fresh path
- [x] `_save_step_state` called unconditionally on fresh branch (L734) -- StateSaved on use_cache=False confirmed
- [x] `logged_keys=[step.step_name]` assertion matches CEO decision (PLAN.md arch decision)
- [x] `ContextUpdated` always emits (no empty-context guard) -- matches CEO decision
- [x] Single test confirmed passing: `1 passed in 0.09s`
- [x] File follows exact patterns from `test_transformation_events.py` and `test_extraction_events.py`
