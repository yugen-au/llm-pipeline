# Research Summary

## Executive Summary

Both research documents are highly accurate. Step 1 (Codebase Architecture) was verified line-by-line against actual source -- all signatures, line references, algorithm descriptions, and behavioral semantics match the current code. Step 2 (Python Patterns) proposes design patterns that align with existing codebase conventions (ABC pattern from PipelineStrategy, Pydantic BaseModel for data containers, module-level pure functions).

The strategy pattern approach is sound. MajorityVoteStrategy can exactly reproduce current behavior. Four design questions were escalated to CEO; all resolved (see Q&A History).

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
| Per-step vs pipeline-level config interaction? | **STEP OVERRIDES ALL.** Step strategy activates regardless of pipeline enable flag. If no step strategy, fall back to pipeline-level. | StepDefinition.consensus_strategy is the primary config point. Pipeline-level is fallback only. Orchestrator checks step first, pipeline second. |
| Keep consensus_polling dict API? | **REMOVE ENTIRELY.** Breaking change accepted. | No backward compat conversion needed. Delete consensus_polling parameter from execute(). All consensus config via strategy objects only. |
| ConsensusResult.confidence semantics? | **NORMALIZED 0-1 SCALE.** Each strategy computes its natural trust metric, normalized to 0-1. strategy_name metadata enables strategy-specific interpretation by advanced callers. MajorityVote=agreement_ratio, ConfidenceWeighted=normalized weighted score, Adaptive=normalized combined metric, SoftVote=probability margin. | confidence field is always float 0-1 with ge=0.0 le=1.0 validation. No strategy-specific subfields needed. |
| Grouping logic ownership? | **SHARED ORCHESTRATOR.** All strategies share instructions_match() at orchestrator level. No ABC group() hook. | Grouping stays in pipeline.py (or consensus.py module-level function called by pipeline.py). Strategies receive pre-grouped result_groups. Simpler ABC interface. |

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

- `create_failure()` with required fields in consensus: if `output_type.create_failure(str(exc))` is called without `**safe_defaults` for required fields (like `count` on `SimpleInstructions`), Pydantic validation fails. Pre-existing gap, not introduced by refactor, but strategies should handle failure results the same way as current code.
- Orphaned event types (`LLMCallRetry`, `LLMCallFailed`, `LLMCallRateLimited`) remain defined but never emitted. Not Task 5 scope but noted for awareness.
- ConsensusStarted event has `threshold: int` field -- ConfidenceWeighted uses `threshold: float`. May need event field type change or new event variant.
- Removing `consensus_polling` dict API from `execute()` is a breaking change to the public API. Callers must migrate to `StepDefinition.consensus_strategy`.

## Recommendations for Planning

1. Accept research findings as accurate basis for planning -- no codebase discrepancies found
2. Use explicit `name` property on ConsensusStrategy ABC (not __init_subclass__ auto-naming) to avoid PipelineStrategy collision
3. Grouping logic stays at orchestrator level (CEO decision). Extract `instructions_match()`, `_smart_compare()`, `_get_mixin_fields()` as module-level functions in `consensus.py`. Orchestrator calls them and passes pre-grouped `result_groups` to strategies.
4. ConsensusResult as Pydantic BaseModel (frozen=True) with `confidence: float = Field(ge=0.0, le=1.0)` -- normalized 0-1 scale per CEO decision
5. Remove `consensus_polling` dict API entirely (CEO decision: breaking change accepted). All consensus config via `StepDefinition.consensus_strategy` only.
6. Step-level strategy overrides all (CEO decision). If `StepDefinition.consensus_strategy` is set, consensus activates for that step regardless of any pipeline-level flag. If not set, no consensus for that step.
7. Add `consensus_strategy` field to StepDefinition dataclass before any other changes (implementation ordering dependency)
8. ConsensusStarted event may need a `strategy_name: str` field addition -- plan for this in event type modifications
9. Test strategy: unit test each strategy with known inputs, integration test via existing `_run_consensus_pipeline` pattern, verify MajorityVoteStrategy produces identical event sequences to current code
