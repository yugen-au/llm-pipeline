# IMPLEMENTATION - STEP 2: ADD EMISSION BLOCKS
**Status:** completed

## Summary
Inserted 6 guard+emit blocks in `llm_pipeline/pipeline.py` for 4 event types: InstructionsStored (2 paths), InstructionsLogged (2 paths), ContextUpdated (1 centralized), StateSaved (1 fresh-only).

## Files
**Created:** none
**Modified:** `llm_pipeline/pipeline.py`
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`
6 emission blocks added at validated locations, all following existing `if self._event_emitter:` guard pattern.

```
# 1. InstructionsStored (cached path) - after L582
self._instructions[step.step_name] = instructions
if self._event_emitter:
    self._emit(InstructionsStored(..., instruction_count=len(instructions)))

# 2. InstructionsStored (fresh path) - after L692
self._instructions[step.step_name] = instructions
if self._event_emitter:
    self._emit(InstructionsStored(..., instruction_count=len(instructions)))

# 3. InstructionsLogged (cached path) - after L619
step.log_instructions(instructions)
if self._event_emitter:
    self._emit(InstructionsLogged(..., logged_keys=[step.step_name]))

# 4. InstructionsLogged (fresh path) - after L737
step.log_instructions(instructions)
if self._event_emitter:
    self._emit(InstructionsLogged(..., logged_keys=[step.step_name]))

# 5. ContextUpdated - in _validate_and_merge_context after L373
self._context.update(new_context)
if self._event_emitter:
    self._emit(ContextUpdated(..., new_keys=list(new_context.keys()), context_snapshot=dict(self._context)))

# 6. StateSaved - in _save_step_state after L947
self._real_session.flush()
if self._event_emitter:
    self._emit(StateSaved(..., execution_time_ms=float(execution_time_ms) if execution_time_ms is not None else 0.0))
```

## Decisions
### No additional decisions required
All decisions were made in PLAN.md and VALIDATED_RESEARCH.md (CEO decisions on logged_keys semantics and ContextUpdated always-emit behavior).

## Verification
[x] Syntax valid (ast.parse passes)
[x] All 272 existing tests pass (0 failures)
[x] 6 emission blocks match plan exactly
[x] Guard pattern `if self._event_emitter:` consistent with all 18 existing emissions
[x] ContextUpdated emits unconditionally (no new_context guard) per CEO decision
[x] StateSaved uses `float()` cast with None guard per plan
[x] InstructionsLogged uses `logged_keys=[step.step_name]` per CEO decision
