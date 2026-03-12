# IMPLEMENTATION - STEP 1: CREATE CONSENSUS.PY
**Status:** completed

## Summary
Created `llm_pipeline/consensus.py` with ConsensusStrategy ABC, ConsensusResult frozen Pydantic model, 4 concrete strategy implementations, and 3 utility functions extracted from `PipelineConfig` in `pipeline.py`.

## Files
**Created:** `llm_pipeline/consensus.py`
**Modified:** none
**Deleted:** none

## Changes
### File: `llm_pipeline/consensus.py`
New module containing:

1. **Utility functions** (extracted from `pipeline.py` lines 1225-1263):
   - `_get_mixin_fields(model_class)` - lazy-imports `LLMResultMixin` to avoid circular import
   - `_smart_compare(value1, value2, field_name, mixin_fields)` - exact same logic as `PipelineConfig._smart_compare()`
   - `instructions_match(instr1, instr2)` - public (no underscore), wraps `_smart_compare`

2. **ConsensusResult(BaseModel)** - `ConfigDict(frozen=True)`, fields: `result: Any`, `confidence: float [0-1]`, `strategy_name: str`, `agreement_ratio: float [0-1]`, `total_attempts: int`, `group_count: int`, `consensus_reached: bool`

3. **ConsensusStrategy(ABC)** - abstract: `name` property, `max_attempts` property, `should_continue()`, `select()`

4. **MajorityVoteStrategy** - threshold/max_attempts params, reproduces original `_execute_with_consensus` early-exit and selection logic exactly

5. **ConfidenceWeightedStrategy** - weights groups by `confidence_score`, div-by-zero guard (falls back to agreement_ratio when total_score==0), picks highest-scored member from best group

6. **AdaptiveStrategy** - lowers threshold from `initial_threshold` to `min_threshold` when progress > 70%

7. **SoftVoteStrategy** - picks group with highest average `confidence_score`, confidence = avg score of winning group

## Decisions
### `instructions_match` is public (no underscore)
**Choice:** Named `instructions_match` instead of `_instructions_match`
**Rationale:** Per plan spec -- will be used by orchestrator and tests externally

### `_smart_compare` recursion references module function
**Choice:** Recursive calls reference `_smart_compare` (module-level) instead of `PipelineConfig._smart_compare`
**Rationale:** Function is no longer a staticmethod; self-reference via module name is the natural pattern

### Frozen model validation via Pydantic Field(ge/le)
**Choice:** Used `Field(ge=0.0, le=1.0)` for confidence and agreement_ratio
**Rationale:** Pydantic enforces bounds at construction time, preventing strategy math errors from producing out-of-range values

## Verification
[x] Module imports without errors: `from llm_pipeline.consensus import ...`
[x] Full package import works: `import llm_pipeline` (no circular imports)
[x] MajorityVoteStrategy smoke tests pass (threshold detection, unanimous/split results)
[x] ConfidenceWeightedStrategy div-by-zero guard returns valid confidence (0.5)
[x] AdaptiveStrategy threshold lowering works (3->2 after 70% progress)
[x] SoftVoteStrategy avg confidence calculation correct
[x] `instructions_match` matches strings leniently, mismatches on different ints
[x] ConsensusResult is frozen (raises on mutation)
[x] All 28 test failures are pre-existing (confirmed identical without the new file)
[x] 838 tests pass, 6 skipped -- no regressions
