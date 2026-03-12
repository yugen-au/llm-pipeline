# Research Summary

## Executive Summary

Both research documents are highly accurate. Step 1 (Codebase Architecture) was verified line-by-line against actual source -- all signatures, line references, algorithm descriptions, and behavioral semantics match the current code. Step 2 (Python Patterns) proposes design patterns that align with existing codebase conventions (ABC pattern from PipelineStrategy, Pydantic BaseModel for data containers, module-level pure functions).

The strategy pattern approach is sound. MajorityVoteStrategy can exactly reproduce current behavior. Four questions require CEO input before planning: per-step vs pipeline-level interaction model, backward compatibility of consensus_polling dict API, ConsensusResult.confidence semantics, and grouping logic ownership.

## Domain Findings

### Current Consensus Algorithm
**Source:** step-1-codebase-architecture.md, pipeline.py:1265-1386

Verified exact algorithm: loop up to maximum_step_calls, group each result via `_instructions_match()` -> `_smart_compare()` (structural comparison skipping strings, None, mixin fields), check if any group hits threshold, return first member of winning/largest group. Token accumulation with `_has_any_usage` guard for None propagation. Four events emitted (ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed), all frozen dataclasses extending StepScopedEvent.

### Comparison Functions
**Source:** step-1-codebase-architecture.md, pipeline.py:1225-1263

`_smart_compare()` is intentionally lenient: strings always match, None always matches, mixin fields (confidence_score, notes) always match. Only numerics (int, float, bool), list lengths, and dict key-sets provide discrimination. This means consensus groups on STRUCTURAL values only. All three functions are @staticmethod on PipelineConfig with no instance state -- pure functions suitable for module-level extraction.

### Strategy Pattern Design
**Source:** step-2-python-patterns.md, strategy.py

ConsensusStrategy ABC recommended with explicit `name` property (not `__init_subclass__` auto-naming). This is a deliberate departure from PipelineStrategy's auto-naming to avoid `__init_subclass__` collision. PipelineStrategy's guard (`cls.__bases__[0] is not PipelineStrategy`) means non-direct subclasses skip validation, so ConsensusStrategy subclasses wouldn't collide at runtime -- but using a separate naming mechanism is cleaner.

### ConsensusResult Model
**Source:** step-2-python-patterns.md

Pydantic BaseModel (frozen=True) recommended over dataclass. Provides validation for confidence/agreement_ratio bounds, model_dump() for event serialization, immutability matching event pattern. Return shape changes from `(result, input_tokens, output_tokens, total_requests)` to `(ConsensusResult, input_tokens, output_tokens, total_requests)`. Token tracking stays separate.

### Per-Step Configuration
**Source:** step-2-python-patterns.md, strategy.py:22-40

StepDefinition dataclass gets new optional field `consensus_strategy: ConsensusStrategy | None = None`. The `step_definition` decorator's `create_definition()` already uses `**kwargs` which passes through to StepDefinition(), so no decorator signature change needed -- the field just needs to exist on the dataclass.

### File Location
**Source:** step-1-codebase-architecture.md, step-2-python-patterns.md

Both docs agree: `llm_pipeline/consensus.py` (flat module alongside strategy.py, step.py). Task 5 description references `logistics_intelligence/core/schemas/pipeline/consensus.py` which is stale monorepo path. Confirmed no `schemas/pipeline/` package exists.

### Upstream Task 2 Deviations
**Source:** step-1-codebase-architecture.md, pydantic-ai-2 SUMMARY.md

Task 2 rewrote `_execute_with_consensus` from `execute_llm_step()` to `agent.run_sync()`. Known deviations: `LLMCallCompleted.raw_response` permanently None, `LLMCallCompleted.attempt_count` always 1, orphaned event types remain defined. None of these affect Task 5 consensus refactoring.

## Q&A History
| Question | Answer | Impact |
| --- | --- | --- |
| Per-step vs pipeline-level config interaction? | PENDING | Determines whether step-level strategy activates independently or only when pipeline consensus is enabled |
| Keep consensus_polling dict API? | PENDING | Determines backward compatibility approach and whether internal conversion to MajorityVoteStrategy is needed |
| ConsensusResult.confidence semantics? | PENDING | Determines whether confidence is strategy-specific or standardized across all strategies |
| Grouping logic ownership? | PENDING | Determines whether strategies can customize grouping or all share instructions_match |

## Assumptions Validated

- [x] No `schemas/pipeline/` package exists; new file goes in `llm_pipeline/consensus.py`
- [x] `_smart_compare`, `_instructions_match`, `_get_mixin_fields` are @staticmethod with no instance state -- safe to extract as module-level functions
- [x] `_instructions_match` only called from `_execute_with_consensus` -- no external callers to break
- [x] MajorityVoteStrategy algorithm maps 1:1 to current `_execute_with_consensus` behavior (verified: matched_group[0] on success, max(result_groups, key=len)[0] on failure)
- [x] PipelineStrategy `__init_subclass__` guards against non-direct subclasses (`cls.__bases__[0] is not PipelineStrategy`) -- ConsensusStrategy subclasses won't trigger PipelineStrategy validation
- [x] `step_definition` decorator's `create_definition(**kwargs)` passes through to `StepDefinition()` init -- adding field to dataclass is sufficient
- [x] Token tracking is separate from consensus selection logic -- clean separation in current code
- [x] Event emission is in pipeline.py orchestrator, not in comparison/selection logic -- strategies can be pure
- [x] LLMResultMixin.confidence_score exists on all instruction models (default 0.95) -- available for ConfidenceWeighted/Adaptive strategies
- [x] Existing test infrastructure (test_consensus_events.py, conftest.py) provides adequate patterns for strategy unit tests

## Open Items

- Per-step vs pipeline-level config interaction model (options a/b/c) -- needs CEO decision
- Backward compatibility of `consensus_polling` dict API -- needs CEO decision
- `ConsensusResult.confidence` field semantics (strategy-specific vs standardized) -- needs CEO decision
- Grouping logic ownership: fixed at orchestrator (all strategies share `instructions_match`) vs pluggable via optional `group()` hook on ABC -- needs CEO decision
- `create_failure()` with required fields in consensus: if `output_type.create_failure(str(exc))` is called without `**safe_defaults` for required fields (like `count` on `SimpleInstructions`), Pydantic validation fails. Pre-existing gap, not introduced by refactor, but strategies should handle failure results the same way as current code.
- Orphaned event types (`LLMCallRetry`, `LLMCallFailed`, `LLMCallRateLimited`) remain defined but never emitted. Not Task 5 scope but noted for awareness.
- ConsensusStarted event has `threshold: int` field -- ConfidenceWeighted uses `threshold: float`. May need event field type change or new event variant.

## Recommendations for Planning

1. Accept research findings as accurate basis for planning -- no codebase discrepancies found
2. Use explicit `name` property on ConsensusStrategy ABC (not __init_subclass__ auto-naming) to avoid PipelineStrategy collision
3. Keep grouping logic at orchestrator level with `instructions_match()` as module-level function in consensus.py; defer pluggable grouping to future task if needed
4. ConsensusResult as Pydantic BaseModel (frozen=True) -- matches codebase conventions and provides validation
5. Maintain backward compatibility of `consensus_polling` dict API by internally converting to `MajorityVoteStrategy(threshold=threshold)` when no step-level strategy is set
6. Add `consensus_strategy` field to StepDefinition dataclass before any other changes (implementation ordering dependency)
7. ConsensusStarted event may need a `strategy_name: str` field addition -- plan for this in event type modifications
8. Test strategy: unit test each strategy with known inputs, integration test via existing `_run_consensus_pipeline` pattern, verify MajorityVoteStrategy produces identical event sequences to current code
