# PLANNING

## Summary
Add 5 step lifecycle event emissions (StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted) to Pipeline.execute() step loop (L459-584 in pipeline.py). Follow Task 8 pattern: conditional emission with `if self._event_emitter:`, extend L35 import, emit at validated points per VALIDATED_RESEARCH.md. Add integration tests mirroring test_pipeline_lifecycle_events.py structure.

## Plugin & Agents
**Plugin:** backend-development + python-development (combined)
**Subagents:** backend-core, test-engineer
**Skills:** none

## Phases
1. Implementation - Add 5 step event emissions + import
2. Testing - Integration tests verifying correct event sequence and data
3. Review - Verify emission points match validated research

## Architecture Decisions

### Decision 1: StepCompleted Placement
**Choice:** Emit BEFORE `_executed_steps.add(step_class)` (L579) and BEFORE `action_after` hook (L580-583)
**Rationale:** CEO decision, validated in research. Emit when step work done, then bookkeeping. Order: StepCompleted -> _executed_steps.add -> action_after
**Alternatives:** After _executed_steps.add (rejected - adds is bookkeeping not step work)

### Decision 2: step_start Timing
**Choice:** Keep `step_start = datetime.now(timezone.utc)` at L503, emit StepStarted just before it (L502-503 gap)
**Rationale:** CEO decision. Moving earlier would include logging overhead (L486-501) in existing _save_step_state execution_time_ms calculation (L570-571), changing existing behavior. Microsecond gap negligible
**Alternatives:** Move to L486 area (rejected - side-effect on _save_step_state timing)

### Decision 3: Import Strategy
**Choice:** Extend module-level import at L35 to include all 5 step event types in single line
**Rationale:** Consistent with Task 8 pattern which added 3 pipeline events to L35. Single import statement keeps imports clean
**Alternatives:** Separate import statements (rejected - less clean)

### Decision 4: Zero-Overhead Guard Pattern
**Choice:** All 5 emissions use `if self._event_emitter:` guard before `self._emit()`
**Rationale:** Established by Task 8 (L450, L585, L600). Conditional check avoids event object instantiation overhead when no emitter configured
**Alternatives:** Always construct events (rejected - unnecessary overhead)

## Implementation Steps

### Step 1: Add Step Event Imports
**Agent:** backend-development:backend-core
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Edit llm_pipeline/pipeline.py L35 to extend import with 5 step events: StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted

### Step 2: Emit StepSelecting
**Agent:** backend-development:backend-core
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add StepSelecting emission after L459 (for loop start), before L461 (increment step_num)
2. Use guard: `if self._event_emitter:`
3. Fields: step_index (L459 loop var), strategy_count=len(self._strategies), step_name=None (not yet known)

### Step 3: Emit StepSelected
**Agent:** backend-development:backend-core
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add StepSelected emission after L479 (current_step_name = step.step_name), before L481 (should_skip check)
2. Use guard: `if self._event_emitter:`
3. Fields: step_name=step.step_name, step_number=step_num, strategy_name=selected_strategy.name

### Step 4: Emit StepSkipped
**Agent:** backend-development:backend-core
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add StepSkipped emission inside should_skip branch (L481-484), after L482 logger.info, before L483 _executed_steps.add, before L484 continue
2. Use guard: `if self._event_emitter:`
3. Fields: step_name=step.step_name, step_number=step_num, reason="should_skip returned True" (hardcoded - no reason mechanism in should_skip)

### Step 5: Emit StepStarted
**Agent:** backend-development:backend-core
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add StepStarted emission between L502 (end of logging block) and L503 (step_start capture)
2. Use guard: `if self._event_emitter:`
3. Fields: step_name=step.step_name, step_number=step_num, system_key=step.system_instruction_key, user_key=step.user_prompt_key
4. Note: system_key and user_key can be None (strategy.py L116 validates at least one exists)

### Step 6: Emit StepCompleted
**Agent:** backend-development:backend-core
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add StepCompleted emission before L579 (_executed_steps.add), after both cached path (L526) and fresh path (L577) converge
2. Use guard: `if self._event_emitter:`
3. Fields: step_name=step.step_name, step_number=step_num, execution_time_ms=(datetime.now(timezone.utc) - step_start).total_seconds() * 1000 (as float)
4. Calculate fresh - step_start available from L503 for both cached and fresh paths

### Step 7: Add Step Lifecycle Integration Tests
**Agent:** python-development:test-engineer
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. Create tests/events/test_step_lifecycle_events.py mirroring test_pipeline_lifecycle_events.py structure
2. Reuse fixtures: engine, seeded_session, in_memory_handler, MockProvider, SimpleStep, SuccessStrategy, SuccessRegistry
3. Add SkippableStep (should_skip returns True) for StepSkipped test
4. Test classes: TestStepSelecting, TestStepSelected, TestStepSkipped, TestStepStarted, TestStepCompleted
5. Verify field values: step_index, step_number, step_name, strategy_name, system_key, user_key, reason, execution_time_ms
6. Test zero-overhead path: pipeline without event_emitter completes successfully, no test for emitted events (no handler to check)
7. Test correct event ordering: StepSelecting -> StepSelected -> StepStarted -> StepCompleted (for non-skipped step), StepSelecting -> StepSelected -> StepSkipped (for skipped step)

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Emission point off-by-one error causing incorrect event ordering | Medium | Validated line numbers against pipeline.py L459-584, cross-referenced research docs, validated by CEO |
| StepCompleted execution_time_ms calculation differs from _save_step_state timing on fresh path | Low | Use same formula from L570-571, emit before _save_step_state call |
| step_start not available on cached path for StepCompleted | Low | step_start set at L503 BEFORE cached/fresh branch, available for both |
| selected_strategy is None when emitting StepSelected (loop breaks at L472 if no step_def) | Low | StepSelected only emitted after L479, inside step_def truthy block |
| StepStarted system_key/user_key both None violates strategy validation | Low | strategy.py L116 validates at least one exists, StepStarted types as str \| None = None |

## Success Criteria

- [ ] All 5 step events imported at L35 in pipeline.py
- [ ] StepSelecting emitted after L459, guarded by if self._event_emitter
- [ ] StepSelected emitted after L479, before L481, guarded
- [ ] StepSkipped emitted after L482, before L483, guarded, reason="should_skip returned True"
- [ ] StepStarted emitted between L502-L503, guarded
- [ ] StepCompleted emitted before L579 (_executed_steps.add) and L580 (action_after), guarded, execution_time_ms as float
- [ ] Integration tests in tests/events/test_step_lifecycle_events.py verify all 5 events with correct field values
- [ ] Test verifies event ordering: StepSelecting -> StepSelected -> StepStarted -> StepCompleted
- [ ] Test verifies skip path: StepSelecting -> StepSelected -> StepSkipped (no StepStarted/Completed)
- [ ] Test verifies zero-overhead: pipeline without event_emitter executes successfully
- [ ] pytest passes for new test file

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Straightforward event emission additions following established Task 8 pattern. All emission points validated in research and confirmed by CEO. No architectural changes, no external API modifications. Emission logic is additive (guarded by if self._event_emitter). Tests mirror existing test_pipeline_lifecycle_events.py structure.
**Suggested Exclusions:** testing, review
