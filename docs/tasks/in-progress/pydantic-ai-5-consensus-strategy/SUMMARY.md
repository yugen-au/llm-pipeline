# Task Summary

## Work Completed

Refactored the consensus mechanism in `llm_pipeline` from an inline majority-vote algorithm hardcoded in `PipelineConfig._execute_with_consensus()` to a pluggable Strategy Pattern. A new `llm_pipeline/consensus.py` module provides the `ConsensusStrategy` ABC, the `ConsensusResult` frozen Pydantic model, three module-level utility functions extracted from `PipelineConfig`, and four concrete strategy implementations: `MajorityVoteStrategy`, `ConfidenceWeightedStrategy`, `AdaptiveStrategy`, and `SoftVoteStrategy`. `StepDefinition` gained a `consensus_strategy` field enabling per-step strategy configuration. `PipelineConfig._execute_with_consensus()` was rewritten to accept a strategy object, and the `consensus_polling` dict API was removed entirely as a breaking change. Event types `ConsensusStarted`, `ConsensusReached`, and `ConsensusFailed` were updated: `threshold` changed from `int` to `float` across all three, and `ConsensusStarted` gained a `strategy_name: str` field. 86 new unit and integration tests were added in `tests/test_consensus.py`, and 20 existing event tests in `tests/events/test_consensus_events.py` were updated to use the new strategy API. A review-cycle fix corrected a `ConsensusReached`/`ConsensusFailed` threshold type inconsistency (int annotation receiving float value). All 297 consensus-related tests pass; the full suite has 951/952 passing with one pre-existing unrelated failure in `test_ui.py`.

## Files Changed

### Created

| File | Purpose |
| --- | --- |
| `llm_pipeline/consensus.py` | ConsensusStrategy ABC, ConsensusResult model, utility functions (_get_mixin_fields, _smart_compare, instructions_match), and 4 strategy implementations |
| `tests/test_consensus.py` | 86 unit and integration tests covering all 4 strategies, utility functions, ConsensusResult validation, ABC enforcement, and package exports |

### Modified

| File | Changes |
| --- | --- |
| `llm_pipeline/events/types.py` | `ConsensusStarted.threshold` int->float; added `ConsensusStarted.strategy_name: str`; `ConsensusReached.threshold` int->float (review fix); `ConsensusFailed.threshold` int->float (review fix) |
| `llm_pipeline/strategy.py` | Added `consensus_strategy: ConsensusStrategy | None = None` field to `StepDefinition` dataclass with TYPE_CHECKING guard import |
| `llm_pipeline/__init__.py` | Added imports and `__all__` entries for all 6 consensus public symbols: `ConsensusStrategy`, `ConsensusResult`, `MajorityVoteStrategy`, `ConfidenceWeightedStrategy`, `AdaptiveStrategy`, `SoftVoteStrategy` |
| `llm_pipeline/pipeline.py` | Rewrote `_execute_with_consensus()` signature to accept `strategy: ConsensusStrategy`; removed `_smart_compare`, `_instructions_match`, `_get_mixin_fields` static methods (moved to consensus.py); removed `consensus_polling` parameter from `execute()`; updated consensus call site to use `step_def.consensus_strategy` |
| `tests/events/test_consensus_events.py` | Updated `_run_consensus_pipeline()` to use `MajorityVoteStrategy` on step definitions instead of `consensus_polling` dict; updated event field assertions for `strategy_name` and float `threshold` |
| `tests/events/test_event_types.py` | Updated consensus event fixtures and assertions for float threshold and strategy_name field |
| `tests/test_token_tracking.py` | Updated consensus-related test setup to remove `consensus_polling` parameter usage |

## Commits Made

| Hash | Message |
| --- | --- |
| `efc546d2` | docs(implementation-A): pydantic-ai-5-consensus-strategy (step 1: create consensus.py) |
| `4b9eb075` | docs(implementation-A): pydantic-ai-5-consensus-strategy (step 2: update event types) |
| `0b9ca76c` | docs(implementation-B): pydantic-ai-5-consensus-strategy (steps 3+4: strategy.py, __init__.py) |
| `044fd86b` | docs(implementation-C): pydantic-ai-5-consensus-strategy (step 5: refactor pipeline.py) |
| `7665a2d2` | docs(implementation-D): pydantic-ai-5-consensus-strategy (step 6: write tests) |
| `77c62334` | docs(fixing-review-A): pydantic-ai-5-consensus-strategy (review fix: ConsensusReached/ConsensusFailed threshold int->float) |

## Deviations from Plan

- `ConsensusFailed.threshold` was also changed int->float (not mentioned in plan, only `ConsensusReached` was called out in the review). Caught and fixed during the review cycle as the same inconsistency applied to both terminal events.
- `tests/test_token_tracking.py` required updating to remove `consensus_polling` usage; this file was not listed in plan step 6 but was a necessary consequence of the breaking API change.
- Plan step 5 noted a placeholder for `ConsensusStarted.threshold` emission (`strategy.max_attempts` as placeholder). Implementation resolved this: `MajorityVoteStrategy` and `AdaptiveStrategy` expose an integer `threshold` property; `ConfidenceWeightedStrategy` and `SoftVoteStrategy` expose a float threshold/confidence_floor. The strategy ABC does not define a `threshold` property; each concrete class defines its own. Pipeline emission uses `strategy.threshold` which is dynamically resolved per strategy type.

## Issues Encountered

### ConsensusReached and ConsensusFailed threshold type inconsistency

During architecture review, the reviewer identified that `ConsensusReached.threshold` and `ConsensusFailed.threshold` were annotated `int` but received `float` values from `strategy.threshold` at the pipeline emission site. The plan only identified `ConsensusStarted.threshold` as needing the int->float change. At runtime this passed because Python dataclasses do not enforce types and `2 == 2.0`, but it created a type annotation lie and a serialization inconsistency (`asdict()` would emit `2.0` not `2`).

**Resolution:** Changed `ConsensusReached.threshold` and `ConsensusFailed.threshold` from `int` to `float` in `llm_pipeline/events/types.py`. Full test suite re-run confirmed no new failures.

### AdaptiveStrategy attempt proxy semantics

`AdaptiveStrategy.select()` uses `len(results)` as the attempt number when calling `_effective_threshold()`, while `should_continue()` uses the orchestrator-provided `attempt` parameter (1-indexed). These are semantically equivalent -- each result corresponds to one attempt -- but the dual calling convention is implicit.

**Resolution:** Identified as medium risk during review, accepted as documentation concern only. No code change made.

## Success Criteria

- [x] `llm_pipeline/consensus.py` created with ConsensusStrategy ABC, ConsensusResult, 4 strategy classes, and 3 utility functions -- verified by 86 tests passing
- [x] `MajorityVoteStrategy` produces identical event sequence and result selection to pre-refactor `_execute_with_consensus` -- verified by all 20 `test_consensus_events.py` tests passing
- [x] `StepDefinition.consensus_strategy` field accepted and passed through `step_definition` decorator without decorator signature change -- verified by `test_step_definition_accepts_consensus_strategy` and `test_step_definition_consensus_strategy_defaults_none`
- [x] `execute()` no longer accepts `consensus_polling` parameter -- verified by `test_consensus_events.py` using new API exclusively; callers in `test_token_tracking.py` also migrated
- [x] `ConsensusStarted` event emitted with `strategy_name` field populated -- verified by `TestConsensusEventFields::test_started_fields`
- [x] `ConsensusResult.confidence` is always in [0.0, 1.0] for all four strategies -- verified by `TestConsensusResultValidation` tests and `test_confidence_clamps_at_0/1` (Pydantic ge/le validation)
- [x] All new consensus classes exported from `llm_pipeline.__init__` -- verified by `test_strategies_exported_from_package`
- [x] `tests/test_consensus.py` passes with unit coverage for all 4 strategies and utility functions -- 86/86 passed
- [x] Updated `tests/events/test_consensus_events.py` passes -- 20/20 passed
- [x] No circular imports introduced -- verified by `python -c "import llm_pipeline"` and `TestIntegration::test_import_no_circular`
- [x] `pytest` passes with no new failures -- 951/952 full suite; 1 pre-existing `test_ui.py` failure unrelated to this task

## Recommendations for Follow-up

1. Fix the pre-existing `test_ui.py::TestRoutersIncluded::test_events_router_prefix` failure: the events router prefix was changed to `/runs/{run_id}/events` in a prior task but the test still asserts `/events`.
2. Add docstring clarification to `SoftVoteStrategy.select()` and `ConfidenceWeightedStrategy.select()` noting which member of the winning group is returned (`best_group[0]` vs `max(best_group, key=self._score)` respectively) -- reviewer noted this behavioral difference is undocumented.
3. Add a comment or assertion in `_smart_compare()` for the default fallthrough case (returns `True` for unhandled types) to prevent silent false-matches if the function is ever called directly with non-primitive types outside the `instructions_match()` path.
4. Consider adding `isinstance(started[0]["threshold"], float)` type assertions to `test_consensus_events.py` (currently `== 2` passes for both int and float); would catch regressions if the type reverts.
5. Consider removing the orphaned event types (`LLMCallRetry`, `LLMCallFailed`, `LLMCallRateLimited`) from `events/types.py` -- they are defined but never emitted since task 2 rewrote the LLM call layer.
6. `AdaptiveStrategy.select()` uses `len(results)` as the attempt proxy for `_effective_threshold()`. A future refactor could pass the actual attempt count explicitly to `select()` for precision if the loop semantics change.
