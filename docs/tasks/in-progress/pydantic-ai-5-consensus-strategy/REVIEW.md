# Architecture Review

## Overall Assessment
**Status:** complete

Solid Strategy Pattern refactor. ConsensusStrategy ABC mirrors existing PipelineStrategy(ABC) conventions. ConsensusResult as frozen Pydantic model with bounded fields is well-designed. All four strategy implementations are correct and well-tested. The orchestrator integration in pipeline.py is clean -- strategy object replaces three positional params, grouping logic is properly extracted to module-level functions, and the consensus_polling dict API is fully removed with no orphan references.

## Project Guidelines Compliance
**CLAUDE.md:** `C:\Users\SamSG\Documents\claude_projects\llm-pipeline\CLAUDE.md`
| Guideline | Status | Notes |
| --- | --- | --- |
| Python 3.11+ | pass | Type unions use `X \| None` syntax throughout |
| Pydantic v2 | pass | ConfigDict, Field(ge/le), model_dump() used correctly |
| Architecture: Pipeline + Strategy + Step | pass | ConsensusStrategy ABC follows existing pattern; per-step field on StepDefinition |
| No hardcoded values | pass | All thresholds/limits are constructor params with defaults |
| Error handling present | pass | div-by-zero guard in ConfidenceWeighted, UnexpectedModelBehavior catch in orchestrator |
| Tests pass | pass | 86 new + 20 updated event tests pass per implementation docs |

## Issues Found
### Critical

None

### High

#### ConsensusReached.threshold type is int but receives float
**Step:** 5
**Details:** `ConsensusReached` dataclass declares `threshold: int` (types.py line 417) but the pipeline emission site (pipeline.py line 1320) passes `strategy.threshold` which returns `float` on all strategy implementations. This works at runtime because Python dataclasses don't enforce types, and the existing test passes because `2 == 2.0` in Python. However: (1) it is a type annotation lie -- static type checkers will flag callers passing float, (2) `ConsensusStarted.threshold` was updated to `float` but `ConsensusReached.threshold` was not, creating inconsistency between the two related events, (3) `to_dict()` via `asdict()` will serialize it as `2.0` (float) not `2` (int), which could break downstream consumers expecting int. Fix: change `ConsensusReached.threshold` from `int` to `float` to match `ConsensusStarted.threshold`.

### Medium

#### AdaptiveStrategy.select uses len(results) as attempt proxy for _effective_threshold
**Step:** 1
**Details:** In `AdaptiveStrategy.select()` (consensus.py line 357), `_effective_threshold(len(results), self._max_attempts)` uses `len(results)` as the attempt number. This is semantically correct (each result corresponds to one attempt), but the `should_continue()` method uses the orchestrator-provided `attempt` parameter which is `attempt + 1` (1-indexed). If the loop breaks early (should_continue returns False before exhausting max_attempts), `len(results)` will equal the attempt number that triggered the break. This is consistent. However, the two calling conventions (1-indexed attempt in should_continue vs len(results) in select) could diverge if error-handling changes cause results to be appended without incrementing the attempt counter. Low risk but worth a comment.

#### SoftVoteStrategy and ConfidenceWeightedStrategy return first group member, not best member
**Step:** 1
**Details:** `SoftVoteStrategy.select()` returns `best_group[0]` (first member) while `ConfidenceWeightedStrategy.select()` returns `max(best_group, key=self._score)` (highest-scored member). This behavioral difference is by design per the plan, but is undocumented -- users might expect consistent member selection across strategies. Not a bug, but the docstrings should clarify which member is returned from the winning group.

### Low

#### _smart_compare default fallthrough returns True for unhandled types
**Step:** 1
**Details:** `_smart_compare` (consensus.py line 67) returns `True` for any types not explicitly handled (not str, None, int/float/bool, list, dict). This means two Pydantic BaseModel instances compared directly (not via model_dump) would always match regardless of content. The current usage path (`instructions_match` always calls `model_dump()` first, producing dicts) makes this safe, but if `_smart_compare` is ever called directly with non-primitive types, the permissive fallthrough could silently produce false matches. Consider a comment or assertion.

#### test_consensus_events.py assertion on threshold type may be fragile
**Step:** 6
**Details:** `test_consensus_events.py` line 119 asserts `started[0]["threshold"] == 2` and line 128 asserts `reached[0]["threshold"] == 2`. Because `2 == 2.0` in Python, these pass regardless of whether the value is int or float. If a future change needs to distinguish types, these assertions would not catch regressions. Consider using `assert isinstance(started[0]["threshold"], float)` for ConsensusStarted (since it was explicitly changed to float).

## Review Checklist
[x] Architecture patterns followed -- Strategy Pattern with ABC, frozen result model, extracted utility functions
[x] Code quality and maintainability -- clean separation, consistent naming, docstrings present
[x] Error handling present -- div-by-zero guard, UnexpectedModelBehavior catch, Pydantic validation bounds
[x] No hardcoded values -- all thresholds/limits configurable via constructor params
[x] Project conventions followed -- naming (snake_case), imports (TYPE_CHECKING guard), ABC pattern matches PipelineStrategy
[x] Security considerations -- no security concerns (no user input parsing, no DB queries, no network calls in new code)
[x] Properly scoped (DRY, YAGNI, no over-engineering) -- four strategies provide meaningful variety without unused abstractions

## Files Reviewed
| File | Status | Notes |
| --- | --- | --- |
| llm_pipeline/consensus.py | pass | Clean ABC + 4 strategies + utility functions, well-structured |
| llm_pipeline/events/types.py | pass | ConsensusStarted updated correctly; ConsensusReached threshold type inconsistency (HIGH issue) |
| llm_pipeline/strategy.py | pass | consensus_strategy field added with TYPE_CHECKING guard, defaults None |
| llm_pipeline/__init__.py | pass | All 6 consensus symbols exported in import and __all__ |
| llm_pipeline/pipeline.py | pass | Clean refactor, old static methods removed, strategy object wired correctly |
| tests/test_consensus.py | pass | 86 tests, thorough coverage of all strategies, utility functions, validation, ABC |
| tests/events/test_consensus_events.py | pass | Updated to use MajorityVoteStrategy API, 20 tests cover event sequences |

## New Issues Introduced
- ConsensusReached.threshold type mismatch (int annotation receives float value) -- HIGH, fix before merge
- None other detected

## Recommendation
**Decision:** CONDITIONAL

Approve pending fix of the ConsensusReached.threshold type inconsistency (int -> float). This is a one-line change in events/types.py line 417 and a minor test fixture update in test_event_types.py line 100. The medium and low issues are documentation/style concerns that can be addressed later. The architecture is sound, the Strategy Pattern is well-implemented, and test coverage is comprehensive.
