# IMPLEMENTATION - STEP 5: REFACTOR PIPELINE.PY
**Status:** completed

## Summary
Refactored pipeline.py to use the new ConsensusStrategy pattern. Removed inline consensus logic (3 static methods), removed consensus_polling dict API from execute(), rewired _execute_with_consensus to accept a strategy object, and updated the call site to use step_def.consensus_strategy. Also added threshold property to ConsensusStrategy ABC and all concrete strategies for event reporting. Updated all test files that used consensus_polling.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py, llm_pipeline/consensus.py, tests/events/test_consensus_events.py, tests/test_token_tracking.py, tests/events/test_event_types.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
- Added imports: `from llm_pipeline.consensus import instructions_match, ConsensusResult` and TYPE_CHECKING import for `ConsensusStrategy`
- Removed `consensus_polling: Optional[Dict[str, Any]] = None` from execute() signature
- Removed "Parse consensus config" block (use_consensus, consensus_threshold, maximum_step_calls variables)
- Removed 3 static methods: `_get_mixin_fields()`, `_smart_compare()`, `_instructions_match()` (now in consensus.py)
- Rewrote `_execute_with_consensus()` signature: replaced `consensus_threshold, maximum_step_calls` with `strategy: ConsensusStrategy`
- Loop uses `strategy.max_attempts`, `strategy.should_continue()` for early exit, `strategy.select()` for final result
- ConsensusStarted emission uses `strategy.threshold`, `strategy.max_attempts`, `strategy.name`
- ConsensusReached/ConsensusFailed emission uses `consensus_result` fields
- Return extracts `consensus_result.result` for downstream use
- Replaced `if use_consensus:` with `if step_def.consensus_strategy is not None:`
- Replaced inline logger message with strategy-aware message

### File: `llm_pipeline/consensus.py`
- Added `threshold` abstract property to `ConsensusStrategy` ABC
- Added `threshold` property to all 4 concrete strategies: MajorityVote (float of _threshold), ConfidenceWeighted (_threshold), Adaptive (float of _initial_threshold), SoftVote (_confidence_floor)

### File: `tests/events/test_consensus_events.py`
- Replaced consensus_polling dict API with per-step MajorityVoteStrategy via strategies= constructor injection
- Created `_consensus_strategies()` helper that builds strategy instances with consensus_strategy on step definitions
- Updated `_run_consensus_pipeline()` and `TestConsensusZeroOverhead` to use new pattern

### File: `tests/test_token_tracking.py`
- Added MajorityVoteStrategy import
- Created `_consensus_token_strategies()` helper for consensus-enabled token pipeline
- Updated `_run_consensus()` and `test_none_usage_consensus_no_crash` to use strategies= injection

### File: `tests/events/test_event_types.py`
- Updated ConsensusStarted fixture to include `strategy_name` field and float threshold

## Decisions
### threshold property on ConsensusStrategy ABC
**Choice:** Added `threshold` abstract property returning float to ABC and all concrete strategies
**Rationale:** The orchestrator needs a strategy-agnostic way to report threshold in ConsensusStarted and ConsensusReached events. Without this, the emitted threshold would be meaningless (plan used max_attempts as placeholder). Each strategy exposes its own meaningful threshold metric.

### Test strategy injection via strategies= constructor param
**Choice:** Used PipelineConfig constructor's `strategies=` parameter to inject consensus-aware strategy instances instead of creating new Pipeline subclasses
**Rationale:** PipelineConfig enforces naming conventions on subclass creation (XPipeline requires XRegistry, XStrategies). Creating dynamic classes per test call would violate these. The `strategies=` param bypasses class-level config cleanly.

## Verification
[x] python -c "import llm_pipeline" -- no circular imports
[x] 48/48 consensus + token tests pass
[x] 865/866 full suite pass (1 pre-existing test_ui failure)
[x] No consensus_polling references remain in llm_pipeline/ or tests/
[x] No _instructions_match/_smart_compare/_get_mixin_fields remain in pipeline.py
[x] ConsensusStarted emits strategy_name and float threshold
[x] MajorityVoteStrategy produces identical event sequence to pre-refactor behavior
