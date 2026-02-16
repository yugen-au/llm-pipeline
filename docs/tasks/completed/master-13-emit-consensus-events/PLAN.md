# PLANNING

## Summary
Add consensus event emissions to `_execute_with_consensus()` in `pipeline.py`. Modify method signature to accept `current_step_name`, emit 4 events (ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed) using established pipeline emission patterns, update call site, create comprehensive tests using MockProvider.

## Plugin & Agents
**Plugin:** python-development, backend-development
**Subagents:** python-pro (pipeline.py modifications), backend-architect (test creation)
**Skills:** none

## Phases
1. **Implementation**: Modify pipeline.py signature, add imports, add 4 emission points, update call site
2. **Testing**: Create test_consensus_events.py with MockProvider-based tests for both success/failure paths

## Architecture Decisions

### Decision 1: Parameter Name
**Choice:** `current_step_name` (not `step_name`)
**Rationale:** Matches variable name at call site (L492), maintains consistency with execute() scope naming, avoids ambiguity with other step-related params
**Alternatives:** `step_name` would be shorter but conflicts with local variable naming conventions in the surrounding code

### Decision 2: Event Emission Order (ConsensusAttempt + ConsensusReached)
**Choice:** ConsensusAttempt fires before threshold check, so winning attempt emits both ConsensusAttempt then ConsensusReached
**Rationale:** CEO validated this provides group_count progression data for all attempts including the successful one, valuable for debugging consensus behavior
**Alternatives:** Fire ConsensusAttempt only for failed attempts (rejected - loses visibility into successful attempt's group evolution)

### Decision 3: Test Strategy (MockProvider vs unittest.mock.patch)
**Choice:** Use MockProvider from conftest with response lists to control consensus outcomes
**Rationale:** Consistent with all existing event tests (test_cache_events.py, test_pipeline_lifecycle_events.py, test_retry_ratelimit_events.py), cleaner than unittest.mock, no import mocking needed
**Alternatives:** unittest.mock.patch('llm_pipeline.pipeline.execute_llm_step') - rejected as inconsistent with codebase patterns

### Decision 4: Emission Pattern
**Choice:** Follow pipeline.py pattern: `if self._event_emitter:` guard then `self._emit(EventType(...))`
**Rationale:** Matches all 13 existing emission sites in pipeline.py (PipelineStarted, StepSelecting, CacheLookup, etc.), NOT the task 12 provider-level pattern
**Alternatives:** Direct `self._event_emitter.emit()` - rejected, not the established pipeline.py convention

## Implementation Steps

### Step 1: Modify pipeline.py
**Agent:** python-development:python-pro
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add 4 consensus event imports to L35-40 import block: `ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed`
2. Modify `_execute_with_consensus` signature at L965: add `current_step_name` parameter after `maximum_step_calls`
3. Insert ConsensusStarted emission after L969 (after `result_groups = []`), before L970 (`for attempt in range(...)`):
   ```python
   if self._event_emitter:
       self._emit(ConsensusStarted(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=current_step_name,
           threshold=consensus_threshold,
           max_calls=maximum_step_calls,
       ))
   ```
4. Insert ConsensusAttempt emission after L981 (after `matched_group = result_groups[-1]`), before L982 (`if len(matched_group) >= consensus_threshold`):
   ```python
   if self._event_emitter:
       self._emit(ConsensusAttempt(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=current_step_name,
           attempt=attempt + 1,
           group_count=len(result_groups),
       ))
   ```
5. Insert ConsensusReached emission inside threshold check, after L983-985 (logger.info), before L986 (return):
   ```python
   if self._event_emitter:
       self._emit(ConsensusReached(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=current_step_name,
           attempt=attempt + 1,
           threshold=consensus_threshold,
       ))
   ```
6. Insert ConsensusFailed emission after L990 (logger.info), before L991 (return):
   ```python
   if self._event_emitter:
       self._emit(ConsensusFailed(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=current_step_name,
           max_calls=maximum_step_calls,
           largest_group_size=len(largest_group),
       ))
   ```
7. Update call site at L638-641: pass `current_step_name` as 4th argument

### Step 2: Create consensus event tests
**Agent:** backend-development:backend-architect
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create `tests/events/test_consensus_events.py`
2. Import MockProvider, InMemoryEventHandler, SuccessPipeline from conftest, and consensus event types
3. Create test_consensus_reached_path:
   - Create MockProvider with 3 identical responses (same dict -> same Pydantic model -> consensus)
   - Create pipeline with consensus_polling config (threshold=2, max_calls=5)
   - Execute pipeline with in_memory_handler
   - Assert ConsensusStarted(threshold=2, max_calls=5) fires once
   - Assert ConsensusAttempt fires twice (attempts 1 and 2)
   - Assert ConsensusReached(attempt=2, threshold=2) fires once
   - Assert no ConsensusFailed
   - Verify event_type strings: "consensus_started", "consensus_attempt", "consensus_reached"
4. Create test_consensus_failed_path:
   - Create MockProvider with 5 different responses (different dicts -> no consensus)
   - Create pipeline with consensus_polling config (threshold=3, max_calls=5)
   - Execute pipeline with in_memory_handler
   - Assert ConsensusStarted(threshold=3, max_calls=5) fires once
   - Assert ConsensusAttempt fires 5 times (attempts 1-5)
   - Assert ConsensusFailed(max_calls=5, largest_group_size=1) fires once
   - Assert no ConsensusReached
5. Create test_consensus_event_ordering:
   - Verify event sequence: ConsensusStarted first, ConsensusAttempts in order, ConsensusReached/ConsensusFailed last
   - Use event list indexes to verify ordering
6. Create test_consensus_event_fields:
   - Verify run_id, pipeline_name, step_name, timestamp populated correctly
   - Verify threshold/max_calls/attempt/group_count values match expected
7. Create test_consensus_zero_overhead:
   - Execute pipeline with no emitter (emitter=None)
   - Verify no crash, normal execution
8. Create test_consensus_multi_group:
   - MockProvider returns 2 groups of 2 identical responses (threshold=2, max_calls=4)
   - Verify ConsensusAttempt shows group_count evolution: 1 -> 2 -> 2 -> 2
   - Verify ConsensusReached fires on attempt 2 (when first group reaches threshold)

## Risks & Mitigations
| Risk | Impact | Mitigation |
| --- | --- | --- |
| Line numbers shifted since research (pipeline.py modified) | Medium | Verify actual line numbers match research before inserting emissions, search for exact code patterns |
| ConsensusAttempt/ConsensusReached both firing on same attempt not tested correctly | Medium | Explicit test assertion that winning attempt emits both events in correct order |
| MockProvider response matching logic differs from _instructions_match | Low | Use same dict -> same Pydantic model for consensus (established pattern in codebase) |
| Missing step_name param breaks downstream code | Low | Only one call site (L638-641), easily verified |

## Success Criteria
- [ ] pipeline.py imports 4 consensus events
- [ ] _execute_with_consensus signature includes current_step_name param
- [ ] All 4 emission points added with correct fields and guards
- [ ] Call site at L638-641 updated to pass current_step_name
- [ ] test_consensus_events.py created with 7 test cases
- [ ] All tests pass (pytest tests/events/test_consensus_events.py)
- [ ] No existing tests broken (pytest tests/)
- [ ] ConsensusAttempt + ConsensusReached both fire on winning attempt (verified in tests)
- [ ] Zero overhead verified (no emitter = no crash)
- [ ] Event ordering verified (Started -> Attempt*N -> Reached/Failed)

## Phase Recommendation
**Risk Level:** low
**Reasoning:** Simple, well-scoped changes to single file, all event types pre-defined, clear insertion points, established patterns to follow, no external API changes (private method), comprehensive research completed
**Suggested Exclusions:** testing, review
