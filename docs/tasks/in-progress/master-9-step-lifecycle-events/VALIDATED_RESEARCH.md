# Research Summary

## Executive Summary

Cross-referenced both research documents (step-1-step-execution-flow.md, step-2-event-models-emission-patterns.md) against actual source code in pipeline.py (L407-611), events/types.py, step.py, and strategy.py. All 5 event model field signatures verified correct against types.py. Line numbers accurate. Data availability confirmed at every emission point. No conflicts with Task 8 pipeline-level events. One inconsistency found between the two research docs (StepCompleted placement relative to _executed_steps.add). Two gaps identified: step_start timing side-effect and action_after hook interaction. Two questions require CEO input before planning.

## Domain Findings

### Step Loop Structure and Emission Points
**Source:** research/step-1-step-execution-flow.md, pipeline.py L459-583

- Step loop at L459: `for step_index in range(max_steps)` -- verified
- Strategy selection inner loop L464-470 -- verified
- Break at L472 if no step_def -- verified
- Step creation L475-479 (create_step, set _current_step, current_step_name) -- verified
- should_skip check L481-484 -- verified, _executed_steps.add at L483 BEFORE continue at L484
- Logging block L486-501 -- verified
- step_start capture at L503 -- verified
- Cached path L506-532, Fresh path L533-577 -- verified
- _executed_steps.add at L579 -- verified
- action_after hook L580-583 -- verified

All 5 emission points map cleanly to described locations. No ambiguity in placement except the StepCompleted position inconsistency noted below.

### Event Model Field Signatures
**Source:** research/step-2-event-models-emission-patterns.md, events/types.py

All verified against types.py:

| Event | Line | Fields (beyond base) | kw_only | Verified |
|-------|------|---------------------|---------|----------|
| StepSelecting | 203-210 | step_index: int, strategy_count: int | Yes | Yes |
| StepSelected | 213-220 | step_number: int, strategy_name: str | Yes | Yes |
| StepSkipped | 223-230 | step_number: int, reason: str | Yes | Yes |
| StepStarted | 233-241 | step_number: int, system_key: str\|None, user_key: str\|None | Yes | Yes |
| StepCompleted | 244-255 | step_number: int, execution_time_ms: float | Yes | Yes |

All inherit StepScopedEvent -> PipelineEvent. step_name: str | None from StepScopedEvent. EVENT_CATEGORY = CATEGORY_STEP_LIFECYCLE for all 5.

### Data Availability at Emission Points
**Source:** both research docs, verified against pipeline.py and step.py

| Emission Point | Data Needed | Source | Verified |
|---------------|-------------|--------|----------|
| StepSelecting | step_index, len(self._strategies) | Loop var L459, self._strategies | Yes |
| StepSelected | step.step_name, step_num, selected_strategy.name | L476-479, L460, L468 | Yes |
| StepSkipped | step.step_name, step_num, reason (hardcoded) | L476-479, L460, should_skip returns bool | Yes |
| StepStarted | step.step_name, step_num, system_instruction_key, user_prompt_key | L476-479, L460, step.py L241-242 | Yes |
| StepCompleted | step.step_name, step_num, step_start for timing | L476-479, L460, L503 | Yes |

system_instruction_key and user_prompt_key can be None (strategy.py L116 validates at least one exists, not both). StepStarted correctly types these as `str | None = None`.

### Task 8 Compatibility
**Source:** pipeline.py L450-611, Task 8 VALIDATED_RESEARCH.md

No conflicts. Step events are strictly nested within pipeline lifecycle:
```
L450: PipelineStarted
L456: try:
L459:   for step_index...:
          [StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted]
L585: PipelineCompleted
L599: except: PipelineError
```

Error path: StepStarted -> exception -> PipelineError (no StepCompleted). Correctly documented in research step-2 lines 305-309.

### Scope Boundaries
**Source:** both research docs, downstream tasks 10-15

Verified all downstream task scopes are correctly excluded:
- Task 10: Cache events (CacheLookup, CacheHit, CacheMiss, CacheReconstruction)
- Task 11: LLM call events (LLMCallPrepared, LLMCallStarting, LLMCallCompleted)
- Task 13: Consensus events (ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed)
- Task 14: Extraction/transformation events
- Task 15: Context/state events (InstructionsStored, ContextUpdated, StateSaved)

### Research Inconsistency: StepCompleted Placement
**Source:** step-1 vs step-2

- step-1 (line 129): "Just before `self._executed_steps.add(step_class)` (L579)" -- i.e., BEFORE the add
- step-2 (line 248-281): "After `self._executed_steps.add(step_class)` at line 579" -- i.e., AFTER the add

These contradict each other. Both are valid positions (negligible timing difference). The semantic question is whether StepCompleted should fire before or after bookkeeping. See Q&A below.

### Gap: step_start Timing Side-Effect
**Source:** step-1 lines 104-108, step-2 lines 346-353

Both research docs recommend moving `step_start = datetime.now(timezone.utc)` from L503 to before StepStarted emission (~L486 area) for "clean semantics."

Hidden side-effect: The existing fresh path at L570-571 calculates `execution_time_ms = int((datetime.now(timezone.utc) - step_start).total_seconds() * 1000)` for `_save_step_state`. Moving step_start earlier would include logging overhead (L486-501) in _save_step_state's execution_time_ms, changing existing behavior. Neither research doc acknowledges this.

### Gap: action_after Hook Interaction
**Source:** pipeline.py L580-583

Neither research doc discusses whether StepCompleted fires before or after the action_after hook. action_after (L580-583) calls a pipeline method based on step_def.action_after string. This is pipeline-level post-step cleanup, not step execution work. StepCompleted should fire before it.

## Q&A History

| Question | Answer | Impact |
| --- | --- | --- |
| StepCompleted placement: before or after _executed_steps.add (L579)? Research docs disagree. Recommendation: BEFORE (L579), since add is bookkeeping not step work. Also before action_after (L580-583). | Pending | Determines exact insertion line for StepCompleted emission |
| step_start timing: move earlier (changes _save_step_state timing on fresh path) or keep at L503? Recommendation: keep at L503, emit StepStarted just before it. Microsecond gap is negligible, avoids changing existing _save_step_state behavior. | Pending | Determines whether existing _save_step_state timing changes |

## Assumptions Validated

- [x] All 5 event types exist in types.py with correct field signatures (types.py:203-255)
- [x] All 5 inherit StepScopedEvent -> PipelineEvent with step_name: str | None = None
- [x] All 5 use kw_only=True (keyword arguments only)
- [x] All 5 have EVENT_CATEGORY = CATEGORY_STEP_LIFECYCLE
- [x] step.step_name is a property returning snake_case (step.py:246-256), available after L476
- [x] selected_strategy.name returns snake_case string (strategy.py:199-209, via __init_subclass__ L188-191)
- [x] should_skip() returns bool with no reason mechanism (step.py:307-309)
- [x] system_instruction_key and user_prompt_key can be None (strategy.py:116 validates at least one)
- [x] step_start at L503 is set BEFORE cached/fresh branch -- available for both paths
- [x] _executed_steps.add at L483 (skip path) and L579 (normal path) -- both paths add to set
- [x] No import conflicts: 5 new names distinct from Task 8's 3 existing imports at L35
- [x] Zero-overhead guard pattern (if self._event_emitter:) established by Task 8 and verified at L450, L585, L600
- [x] StepSelecting fires even when no strategy provides a step (loop breaks at L472 after emission)
- [x] Error during step: StepStarted emitted, no StepCompleted, PipelineError catches (L599-611)
- [x] Downstream tasks 10-15 correctly excluded from scope

## Open Items

- Minor line number discrepancies between the two research docs (off-by-one on end lines for event definitions). Non-blocking, all start lines correct.
- Import strategy (module-level vs inline) not decided. Task 8 used module-level import at L35 for PipelineStarted/Completed/Error. Research correctly proposes extending that same import. Consistent approach.

## Recommendations for Planning

1. Emit StepSelecting at top of for loop body (after L459, before L461), guarded by `if self._event_emitter:`
2. Emit StepSelected after L479 (current_step_name = step.step_name), before L481 (should_skip check)
3. Emit StepSkipped inside should_skip branch, after L482 logger.info, before L483 _executed_steps.add, before L484 continue
4. Emit StepStarted between L502 and L503 (after logging block, before step_start capture) -- keep step_start at L503 to avoid changing _save_step_state timing (pending CEO confirmation)
5. Emit StepCompleted before L579 _executed_steps.add (pending CEO confirmation on placement)
6. Extend module-level import at L35 to include all 5 step event types
7. All emissions follow `if self._event_emitter:` zero-overhead guard pattern
8. StepCompleted.execution_time_ms calculated as float: `(datetime.now(timezone.utc) - step_start).total_seconds() * 1000`
