# Research Summary

## Executive Summary

Both research agents produced accurate, well-sourced findings. All claims verified against actual source code (pipeline.py L965-991, events/types.py L383-421, events/__init__.py, handlers.py). Event types exist, exports confirmed, handler mapping confirmed, emission points correctly located. One minor inconsistency between docs (param naming), one test strategy improvement identified (use MockProvider over unittest.mock.patch). No hidden architectural assumptions, no blocking gaps. Implementation is straightforward: 1 file modified (pipeline.py), 1 new test file.

## Domain Findings

### Event Type Definitions (Fully Complete)
**Source:** step-1 (section 1), step-2 (section on Already Defined Consensus Events)

All 4 consensus event dataclasses verified in types.py L383-421:
- `ConsensusStarted(StepScopedEvent)` -- threshold: int, max_calls: int (L383-391)
- `ConsensusAttempt(StepScopedEvent)` -- attempt: int, group_count: int (L393-401)
- `ConsensusReached(StepScopedEvent)` -- attempt: int, threshold: int (L403-411)
- `ConsensusFailed(StepScopedEvent)` -- max_calls: int, largest_group_size: int (L413-421)

All use frozen=True, slots=True, kw_only=True, CATEGORY_CONSENSUS. Exported in types.py __all__ (L579-582) and events/__init__.py (L55-58, L123-126). CATEGORY_CONSENSUS mapped to logging.INFO in handlers.py L39. Auto-registered via __init_subclass__. Already tested in test_handlers.py (ConsensusReached at L77-87).

### _execute_with_consensus() Method Analysis
**Source:** step-1 (section 2), step-2 (section on _execute_with_consensus)

Method at pipeline.py L965-991 verified. Current signature: `(self, call_kwargs, consensus_threshold, maximum_step_calls)` -- no step_name param. Method is private (underscore prefix). Called at L638-641 inside execute(). `current_step_name` is set at L492 (`current_step_name = step.step_name`) BEFORE the consensus call site, so it's always available.

Note: _execute_with_consensus is called inside `for idx, params in enumerate(call_params):` loop (L625), so it runs once per call_params entry. Same step_name for all invocations within a step. This is correct behavior.

### Emission Point Mapping
**Source:** step-1 (section 3), step-2 (section on Emission Point Mapping)

All 4 emission points verified against source code line numbers:

| Point | Event | Insert After | Insert Before | Fields Available |
|-------|-------|-------------|---------------|-----------------|
| 1 | ConsensusStarted | L969 (result_groups=[]) | L970 (for loop) | consensus_threshold, maximum_step_calls |
| 2 | ConsensusAttempt | L981 (matched_group assignment) | L982 (threshold check) | attempt+1, len(result_groups) |
| 3 | ConsensusReached | L983-985 (logger.info) | L986 (return) | attempt+1, consensus_threshold |
| 4 | ConsensusFailed | L990 (logger.info) | L991 (return) | maximum_step_calls, len(largest_group) |

Design decision: ConsensusAttempt fires BEFORE threshold check, so the successful attempt emits both ConsensusAttempt and ConsensusReached. Step-2 explicitly documents this as intentional for group_count progression data.

### Emission Pattern
**Source:** step-1 (section 4), step-2 (section on _emit() Mechanism)

Follows established pipeline.py pattern: `if self._event_emitter:` guard then `self._emit(EventType(...))`. _emit() at L213-220 has internal `if self._event_emitter is not None:` check. Double-check is the established codebase convention. NOT the task 12 provider-level pattern (which uses `if event_emitter:` local param). Correct because consensus logic lives in PipelineConfig.

### Import Requirements
**Source:** step-1 (section 5), step-2 (section on Required Changes)

Current pipeline.py imports at L35-40 include 13 event types. Need to add 4 consensus event types. Top-level import (not lazy) matching existing pattern.

### Test Strategy
**Source:** step-1 (section 9), step-2 (section on Testing Patterns)

Both agents correctly identify: InMemoryEventHandler for capture, filter by event_type string, assert counts/fields/ordering, test zero-overhead. Existing conftest.py provides MockProvider, seeded_session, in_memory_handler, SuccessPipeline, etc.

**Correction applied:** Step-1 proposes `unittest.mock.patch('llm_pipeline.pipeline.execute_llm_step')`. This is inconsistent with established test patterns. Existing tests (test_cache_events.py, test_pipeline_lifecycle_events.py, etc.) use MockProvider directly -- no mocking needed. MockProvider._call_count tracks calls, responses consumed in order. For consensus:
- ConsensusReached: provide N identical responses (same dict -> same Pydantic model -> _instructions_match returns True)
- ConsensusFailed: provide N different responses (different dicts -> different groups -> no group hits threshold)

Using MockProvider is cleaner, requires no unittest.mock, and is consistent with all existing event test modules.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| Should ConsensusAttempt fire on the attempt that reaches consensus (before ConsensusReached)? | CEO: Yes, both fire. ConsensusAttempt always fires; ConsensusReached fires additionally when threshold met on same attempt. | Confirmed: emission point 2 stays before threshold check. Winning attempt emits ConsensusAttempt then ConsensusReached. Tests must assert both events on the successful attempt. |
| Parameter name: `step_name` vs `current_step_name` for the new param? | CEO: `current_step_name` -- matches call site variable at L492. | Decided: use `current_step_name` everywhere. Resolves naming inconsistency between research docs. |
| Mock approach: unittest.mock.patch vs MockProvider? | CEO: MockProvider from conftest -- consistent with all other event tests. | Decided: no unittest.mock.patch. Use MockProvider response lists to control consensus outcomes. |

## Assumptions Validated

- [x] All 4 event types defined in types.py L383-421 with correct fields and inheritance -- verified line by line
- [x] All 4 exported in types.py __all__ (L579-582) and events/__init__.py (L55-58) -- verified
- [x] CATEGORY_CONSENSUS mapped to logging.INFO in handlers.py L39 -- verified
- [x] _emit() method at pipeline.py L213-220 with is-not-None guard -- verified
- [x] All pipeline.py emission sites use `if self._event_emitter:` then `self._emit()` pattern -- verified across 13 existing emission sites
- [x] _execute_with_consensus at L965-991, signature lacks step_name -- verified
- [x] Call site at L638-641 has current_step_name in scope (set at L492) -- verified
- [x] Private method (underscore prefix), no external API impact -- verified
- [x] execute_llm_step imported lazily inside method body at L966 -- verified
- [x] StepScopedEvent provides run_id, pipeline_name, step_name (str | None), timestamp -- verified types.py L73-75, L150-162
- [x] No other source files need modification (events/, llm/, etc.) -- verified, all infrastructure exists
- [x] No task 12 file conflicts (task 12 modified provider.py, executor.py, gemini.py; task 13 modifies pipeline.py only) -- verified
- [x] consensus_polling config parsed at L434-446 before step loop -- verified, threshold/max_calls available throughout execute()
- [x] current_step_name always populated when consensus path executes (set at L492, consensus at L638) -- verified

## Open Items

- None. All claims validated, no ambiguities remaining.

## Recommendations for Planning

1. Single file modification: pipeline.py only. Add 4 imports to L35-40, add `current_step_name` param to `_execute_with_consensus` signature, update call site at L638-641, insert 4 emission blocks.
2. Use `current_step_name` as the parameter name (matches call site variable).
3. Follow exact emission pattern: `if self._event_emitter:` guard then `self._emit(EventType(run_id=self.run_id, pipeline_name=self.pipeline_name, step_name=current_step_name, ...))`.
4. Test file: `tests/events/test_consensus_events.py`. Use MockProvider from conftest (not unittest.mock.patch). Control consensus outcomes via response identity/diversity.
5. Test cases: ConsensusReached path (identical responses), ConsensusFailed path (diverse responses), event field verification, event ordering (Started -> Attempt*N -> Reached/Failed), zero-overhead (no emitter), multi-group scenarios.
6. ConsensusAttempt fires before threshold check (intentional) -- tests should verify both ConsensusAttempt and ConsensusReached fire on the successful attempt.
7. Existing conftest fixtures (seeded_session, in_memory_handler, MockProvider, SuccessPipeline) can be reused, but consensus tests need `consensus_polling` config passed to `pipeline.execute()`.
