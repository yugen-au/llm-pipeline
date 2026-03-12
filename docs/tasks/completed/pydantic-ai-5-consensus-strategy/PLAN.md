# PLANNING

## Summary

Refactor the consensus mechanism in `llm_pipeline` from an inline majority-vote algorithm to a pluggable Strategy Pattern. A new `llm_pipeline/consensus.py` module introduces `ConsensusStrategy` ABC, `ConsensusResult` Pydantic model, and four concrete strategy classes. `StepDefinition` gains a `consensus_strategy` field enabling per-step override. `PipelineConfig._execute_with_consensus()` is updated to accept a strategy object, and the `consensus_polling` dict API is removed entirely from `execute()`.

## Plugin & Agents

**Plugin:** python-development
**Subagents:** [available agents]
**Skills:** [available skills]

## Phases

1. **Create consensus module**: New `llm_pipeline/consensus.py` with ABC, ConsensusResult, utility functions, and 4 strategies
2. **Update event types**: Modify `ConsensusStarted` to support float threshold and add strategy_name field
3. **Update strategy.py**: Add `consensus_strategy` field to `StepDefinition`
4. **Update __init__.py**: Export new consensus public API
5. **Refactor pipeline.py**: Replace `_execute_with_consensus()` signature and `execute()` consensus_polling removal
6. **Write tests**: Unit tests for all strategies + update existing consensus event tests

## Architecture Decisions

### ConsensusStrategy ABC Interface
**Choice:** ABC with `name` (abstract property), `max_attempts` (abstract property), `should_continue(results, result_groups, attempt, max_attempts) -> bool`, `select(results, result_groups) -> ConsensusResult`
**Rationale:** Matches existing `PipelineStrategy(ABC)` pattern. `max_attempts` as property lets the orchestrator read it once for the loop bound and `ConsensusStarted.max_calls` field without needing a separate parameter. `should_continue` receives `max_attempts` for strategies that need progress ratio (AdaptiveStrategy). Explicit `name` property avoids `__init_subclass__` collision with `PipelineStrategy`'s naming hook.
**Alternatives:** Protocol (structural typing, no fail-fast enforcement); `__init_subclass__` auto-naming (risk of collision with PipelineStrategy's hook which checks Strategy suffix)

### ConsensusResult as Pydantic BaseModel
**Choice:** `ConsensusResult(BaseModel, frozen=True)` with fields: `result: Any`, `confidence: float = Field(ge=0.0, le=1.0)`, `strategy_name: str`, `agreement_ratio: float = Field(ge=0.0, le=1.0)`, `total_attempts: int`, `group_count: int`, `consensus_reached: bool`
**Rationale:** Pydantic provides bounds validation for confidence/agreement_ratio (prevents bugs from strategy math errors), `model_dump()` for event serialization compatibility, `frozen=True` for immutability consistent with event dataclasses. Return shape becomes `(consensus_result.result, tokens...)` - orchestrator extracts `.result` for downstream use.
**Alternatives:** Frozen dataclass (lighter weight, matches event pattern, but no bounds validation)

### Grouping Logic Stays in Orchestrator
**Choice:** Extract `_smart_compare()`, `_get_mixin_fields()`, `instructions_match()` as module-level functions in `consensus.py`. Orchestrator calls `instructions_match()` to build `result_groups`, then passes `result_groups` to strategy. No `group()` hook on the ABC.
**Rationale:** CEO decision: shared orchestrator-level grouping, no ABC group() hook. All four strategies use identical structural grouping; only selection/continuation logic differs. `instructions_match()` becomes public (no underscore) for use by orchestrator and tests.
**Alternatives:** group() hook on ABC (would allow custom grouping per strategy; ruled out by CEO)

### Remove consensus_polling Dict API
**Choice:** Remove `consensus_polling: Optional[Dict[str, Any]] = None` parameter from `execute()`. Consensus is configured exclusively via `StepDefinition.consensus_strategy`. No backward compat shim.
**Rationale:** CEO decision: breaking change accepted. Eliminates implicit pipeline-level config that applied uniformly to all steps. Per-step strategy is more expressive and explicit. Old callers must migrate: replace `consensus_polling={"enable": True, "consensus_threshold": 3, "maximum_step_calls": 5}` with `consensus_strategy=MajorityVoteStrategy(threshold=3, max_attempts=5)` on each StepDefinition.
**Alternatives:** Keep consensus_polling as fallback default strategy (adds complexity, CEO rejected)

### ConsensusStarted Event Field Changes
**Choice:** Change `threshold: int` to `threshold: float` (int is valid float, backward-compatible for existing callers). Add `strategy_name: str` field. Keep `max_calls: int`.
**Rationale:** ConfidenceWeighted and SoftVote use float thresholds; using float accommodates all strategies. Adding `strategy_name` enables event consumers to interpret threshold semantics correctly. `max_calls` stays int because `max_attempts` is always a positive integer on all strategies.
**Alternatives:** New event subclasses per strategy (over-engineering); omit threshold from event (loses observability)

### _execute_with_consensus Signature Change
**Choice:** New signature: `_execute_with_consensus(self, agent, user_prompt, step_deps, output_type, strategy: ConsensusStrategy, current_step_name) -> tuple[Any, int | None, int | None, int]`. Return value unchanged: `(instruction, input_tokens, output_tokens, total_requests)`. Orchestrator extracts `consensus_result.result` as instruction.
**Rationale:** Keeps external return contract identical so call site in `execute()` changes minimally. Strategy object carries `max_attempts` and threshold internally, simplifying signature. Internally: loop `for attempt in range(strategy.max_attempts)`, call `strategy.should_continue()` for early exit, call `strategy.select()` once after loop or on early exit.
**Alternatives:** Return ConsensusResult directly (would require call site changes to extract .result)

## Implementation Steps

### Step 1: Create llm_pipeline/consensus.py
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /pydantic/pydantic
**Group:** A

1. Create `llm_pipeline/consensus.py` with module docstring and `__all__` export list
2. Add module-level utility functions extracted from `PipelineConfig`:
   - `_get_mixin_fields(model_class: type[BaseModel]) -> set[str]` - imports `LLMResultMixin` lazily to avoid circular import
   - `_smart_compare(value1, value2, field_name="", mixin_fields=None) -> bool` - exact same logic as `PipelineConfig._smart_compare()` at `pipeline.py:1232-1256`
   - `instructions_match(instr1: BaseModel, instr2: BaseModel) -> bool` - public, wraps `_smart_compare`
3. Define `ConsensusResult(BaseModel)` with `model_config = ConfigDict(frozen=True)` and fields: `result: Any`, `confidence: float = Field(ge=0.0, le=1.0)`, `strategy_name: str`, `agreement_ratio: float = Field(ge=0.0, le=1.0)`, `total_attempts: int`, `group_count: int`, `consensus_reached: bool`
4. Define `ConsensusStrategy(ABC)` with abstract methods:
   - `name` abstract property returning `str`
   - `max_attempts` abstract property returning `int`
   - `should_continue(results: list, result_groups: list[list], attempt: int, max_attempts: int) -> bool`
   - `select(results: list, result_groups: list[list]) -> ConsensusResult`
5. Implement `MajorityVoteStrategy(ConsensusStrategy)` with `__init__(self, threshold: int = 3, max_attempts: int = 5)`:
   - `should_continue`: return False if any group reaches threshold or attempt >= max_attempts, else True
   - `select`: find largest group, compute `confidence = agreement_ratio = len(largest) / len(results)`, set `consensus_reached = len(largest) >= self._threshold`
   - Returns first element of largest group as `result`
6. Implement `ConfidenceWeightedStrategy(ConsensusStrategy)` with `__init__(self, threshold: float = 0.8, min_samples: int = 3, max_attempts: int = 5)`:
   - `should_continue`: if len(results) < min_samples, continue; else stop if best weighted confidence >= threshold or exhausted
   - `select`: weight groups by sum of `getattr(r, 'confidence_score', 0.5)`, pick highest-weighted group, select member with highest individual score; `confidence = weighted_score / total_score`, normalized 0-1; `consensus_reached = confidence >= threshold`
7. Implement `AdaptiveStrategy(ConsensusStrategy)` with `__init__(self, initial_threshold: int = 3, min_threshold: int = 2, max_attempts: int = 5)`:
   - Internal `_effective_threshold(attempt, max_attempts)`: returns `min_threshold` if progress > 0.7 else `initial_threshold`
   - `should_continue`: compute effective_threshold, stop if any group reaches it or exhausted
   - `select`: find largest group; `confidence = len(largest_group) / max(len(results), 1)`; `consensus_reached = len(largest) >= self._effective_threshold(len(results), max_attempts)`
8. Implement `SoftVoteStrategy(ConsensusStrategy)` with `__init__(self, min_samples: int = 3, confidence_floor: float = 0.7, max_attempts: int = 5)`:
   - `should_continue`: if len(results) < min_samples, continue; else stop if best avg group confidence >= floor or exhausted
   - `select`: pick group with highest average `getattr(r, 'confidence_score', 0.5)`; `confidence = avg_confidence` (already 0-1); `consensus_reached = avg_confidence >= confidence_floor`
   - Returns first element of best group as `result`

### Step 2: Update events/types.py for ConsensusStarted
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** -
**Group:** A

1. In `llm_pipeline/events/types.py` at the `ConsensusStarted` dataclass (line 390-396):
   - Change `threshold: int` to `threshold: float`
   - Add field `strategy_name: str` after `max_calls: int`
2. No other event types require changes (ConsensusAttempt, ConsensusReached, ConsensusFailed fields are unaffected)

### Step 3: Update strategy.py - add consensus_strategy field to StepDefinition
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** -
**Group:** B

1. In `llm_pipeline/strategy.py`, add `TYPE_CHECKING` import block:
   ```python
   if TYPE_CHECKING:
       from llm_pipeline.consensus import ConsensusStrategy
   ```
   (TYPE_CHECKING already imported in the file at line 12)
2. Add field to `StepDefinition` dataclass after `not_found_indicators`: `consensus_strategy: 'ConsensusStrategy | None' = None`
3. No changes to `step_definition` decorator or `create_definition()` - existing `**kwargs` pass-through handles the new field automatically (verified in research)

### Step 4: Update llm_pipeline/__init__.py - add consensus exports
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** -
**Group:** B

1. Add import line after `from llm_pipeline.strategy import ...`:
   ```python
   from llm_pipeline.consensus import (
       ConsensusStrategy,
       ConsensusResult,
       MajorityVoteStrategy,
       ConfidenceWeightedStrategy,
       AdaptiveStrategy,
       SoftVoteStrategy,
   )
   ```
2. Add to `__all__` list under a new `# Consensus` comment section:
   `"ConsensusStrategy"`, `"ConsensusResult"`, `"MajorityVoteStrategy"`, `"ConfidenceWeightedStrategy"`, `"AdaptiveStrategy"`, `"SoftVoteStrategy"`

### Step 5: Refactor pipeline.py - _execute_with_consensus and execute()
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** /pydantic/pydantic
**Group:** C

1. Add import at top of `pipeline.py` (inside the function or at module level as appropriate): `from llm_pipeline.consensus import instructions_match, ConsensusResult` and `TYPE_CHECKING` import for `ConsensusStrategy`
2. Remove `PipelineConfig._smart_compare()` staticmethod (lines 1232-1256) - replaced by `consensus.py` module function
3. Remove `PipelineConfig._instructions_match()` staticmethod (lines 1258-1263) - replaced by `instructions_match()` in consensus module
4. Remove `PipelineConfig._get_mixin_fields()` staticmethod (lines 1225-1230) - replaced by `_get_mixin_fields()` in consensus module
5. Rewrite `_execute_with_consensus()` with new signature: `(self, agent, user_prompt, step_deps, output_type, strategy: 'ConsensusStrategy', current_step_name)`:
   - Remove `consensus_threshold` and `maximum_step_calls` params; read `strategy.max_attempts` and threshold from strategy object
   - Update `ConsensusStarted` emission: `threshold=strategy.max_attempts` (placeholder - use appropriate float metric from strategy), `max_calls=strategy.max_attempts`, `strategy_name=strategy.name` (new field)
   - Loop body: call `instructions_match()` (module-level) instead of `self._instructions_match()`
   - Replace early-exit condition `if len(matched_group) >= consensus_threshold:` with `if not strategy.should_continue(results, result_groups, attempt + 1, strategy.max_attempts):`
   - After loop (or on early exit): call `consensus_result = strategy.select(results, result_groups)`
   - Emit `ConsensusReached` if `consensus_result.consensus_reached`, else `ConsensusFailed`
   - Return `(consensus_result.result, tokens...)`
6. In `execute()` method (lines 453-494):
   - Remove `consensus_polling: Optional[Dict[str, Any]] = None` parameter
   - Remove entire "Parse consensus config" block (lines 482-494) that sets `use_consensus`, `consensus_threshold`, `maximum_step_calls`
   - Remove `use_consensus` bool variable
7. At the call site (around line 817-830): replace `if use_consensus:` with `if step_def.consensus_strategy is not None:` (where `step_def` is the current step's `StepDefinition` - verify the variable name in context around line 817)
8. Update `_execute_with_consensus` call: replace positional args `consensus_threshold, maximum_step_calls` with `strategy=step_def.consensus_strategy`
9. Remove logger.info line that references `[CONSENSUS POLLING] threshold=...` and replace with strategy-aware message using `strategy.name`

### Step 6: Write tests/test_consensus.py
**Agent:** [available agents]
**Skills:** [available skills]
**Context7 Docs:** -
**Group:** D

1. Create `tests/test_consensus.py` with imports from `llm_pipeline.consensus` and test fixtures mirroring `tests/events/conftest.py` patterns
2. Unit tests for `instructions_match()` and `_smart_compare()` module-level functions:
   - Same-value numeric fields match
   - Different numeric fields don't match
   - String fields always match (lenient comparison)
   - LLMResultMixin fields (confidence_score, notes) always match
3. Unit tests for `MajorityVoteStrategy`:
   - `should_continue` returns False when threshold reached
   - `should_continue` returns False when attempts exhausted
   - `select` with unanimous result: `confidence=1.0`, `consensus_reached=True`
   - `select` with split result: `confidence` is fraction of largest group, `consensus_reached=False` if below threshold
4. Unit tests for `ConfidenceWeightedStrategy`:
   - `select` uses `confidence_score` from LLMResultMixin instances
   - `getattr` fallback to 0.5 when model doesn't have `confidence_score`
   - `confidence` normalized to 0-1
5. Unit tests for `AdaptiveStrategy`:
   - Threshold lowers after 70% of attempts
   - `select` returns first member of largest group
6. Unit tests for `SoftVoteStrategy`:
   - `select` picks group with highest average confidence
   - `confidence` equals average confidence of winning group
7. Update `tests/events/test_consensus_events.py`:
   - Change `_run_consensus_pipeline()` to set `consensus_strategy=MajorityVoteStrategy(threshold=threshold, max_attempts=max_calls)` on `SuccessPipeline`'s step definitions instead of passing `consensus_polling` dict to `execute()`
   - Update `ConsensusStarted` event assertions to check `strategy_name="majority_vote"` and `threshold` type (now float)
   - All other event field assertions (`attempt`, `threshold`, `group_count`, etc.) should pass unchanged
8. Integration test in `test_consensus.py`: run `SuccessPipeline` with `MajorityVoteStrategy` and verify event sequence matches previous behavior (ConsensusStarted -> ConsensusAttempt*N -> ConsensusReached/Failed)

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `_execute_with_consensus` loop refactor changes early-exit semantics from MajorityVote | High | Verify `should_continue` + `select` combination exactly reproduces `len(matched_group) >= threshold` check; add regression test that event sequences are identical |
| `ConsensusStarted.threshold` float change breaks existing test assertions expecting `int` | Medium | `threshold` is now a float on the dataclass; int literals still satisfy float comparison; update test assertions in `test_consensus_events.py` explicitly |
| `step_def` variable name in execute() may not be accessible at consensus call site | Medium | Read lines 817-830 context carefully; variable may be `step`, `step_def`, or `current_step` - verify in Step 5 action 7 |
| Circular import: consensus.py imports from step.py (LLMResultMixin), strategy.py imports from consensus.py | Low | Use lazy import inside `_get_mixin_fields` function (already pattern in existing code); TYPE_CHECKING guard in strategy.py |
| ConfidenceWeighted division-by-zero if all instructions have confidence_score=0.0 | Medium | Add guard in `select()`: if total_score == 0, fall back to agreement_ratio as confidence |
| test_consensus_events.py uses `SuccessPipeline` from conftest.py which defines steps without consensus_strategy | High | Update `SuccessPipeline`'s `get_steps()` in conftest.py or create a new pipeline variant in tests with consensus_strategy on steps; prefer new helper to avoid breaking non-consensus tests |
| execute() callers in tests other than test_consensus_events.py may pass consensus_polling | Medium | Grep for all `consensus_polling` usages in tests before removing; update all callers |

## Success Criteria

- [ ] `llm_pipeline/consensus.py` created with ConsensusStrategy ABC, ConsensusResult, 4 strategy classes, and 3 utility functions
- [ ] `MajorityVoteStrategy` produces identical event sequence and result selection to pre-refactor `_execute_with_consensus` (verified by test)
- [ ] `StepDefinition.consensus_strategy` field accepted and passed through `step_definition` decorator without decorator signature change
- [ ] `execute()` no longer accepts `consensus_polling` parameter; raises TypeError if called with it
- [ ] `ConsensusStarted` event emitted with `strategy_name` field populated
- [ ] `ConsensusResult.confidence` is always in [0.0, 1.0] for all four strategies (Pydantic validation enforces this)
- [ ] All new consensus classes exported from `llm_pipeline.__init__`
- [ ] `tests/test_consensus.py` passes with unit coverage for all 4 strategies and utility functions
- [ ] Updated `tests/events/test_consensus_events.py` passes (existing event sequence assertions hold)
- [ ] No circular imports introduced (verified by running `python -c "import llm_pipeline"`)
- [ ] `pytest` passes with no new failures

## Phase Recommendation

**Risk Level:** medium
**Reasoning:** The orchestrator loop refactor in pipeline.py is complex (early-exit semantics must be preserved exactly for MajorityVote). The breaking API change to `execute()` requires updating all test callers. The `ConsensusStarted` event field type change affects existing test assertions. These risks are contained and verifiable, but require careful implementation ordering and cross-file coordination.
**Suggested Exclusions:** review
