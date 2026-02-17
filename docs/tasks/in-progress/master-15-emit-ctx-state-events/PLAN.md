# PLANNING

## Summary
Add 4 event emissions (InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved) to `llm_pipeline/pipeline.py` at 6 specific points (2 paths each for InstructionsStored and InstructionsLogged). All event types already defined in `events/types.py`. Implementation is: import additions + guard+emit blocks following the established `if self._event_emitter:` pattern used by all 18 existing emissions.

## Plugin & Agents
**Plugin:** python-development, backend-development
**Subagents:** [available agents]
**Skills:** none

## Phases
1. Import update: add 4 new event types to pipeline.py import block
2. Emission blocks: insert 6 `if self._event_emitter:` + `_emit()` blocks at validated locations
3. Tests: create `tests/events/test_ctx_state_events.py` covering fresh+cached paths

## Architecture Decisions

### logged_keys Value for InstructionsLogged
**Choice:** `logged_keys=[step.step_name]` at both emission points (cached L603, fresh L707)
**Rationale:** CEO decision. Storage key semantics - matches where instructions are stored in `_instructions` dict. Simpler than per-instruction key list. Consistent across both paths.
**Alternatives:** List of instruction field names (rejected: over-complex, inconsistent with storage semantics)

### ContextUpdated Emission Guard
**Choice:** `if self._event_emitter:` guard only -- no `new_context and` check
**Rationale:** CEO decision. Always emit even when `new_context` is empty (`{}`). Useful for tracing: signals that `_validate_and_merge_context` ran. Emit with `new_keys=[]` on empty merge.
**Alternatives:** Guard with `new_context and` check (rejected: hides validation trace on empty merges)

### ContextUpdated Emission Location
**Choice:** Emit inside `_validate_and_merge_context` after `self._context.update(new_context)` at L372
**Rationale:** Single emission point covers both cached (L575) and fresh (L671) call sites. `step` param available via method signature. `new_context` has been normalized to dict by L372.
**Alternatives:** Emit at each call site (rejected: duplication; method already centralises the merge logic)

### StateSaved Emission Location
**Choice:** Emit inside `_save_step_state` after `self._real_session.flush()` at L910
**Rationale:** All required fields (`step_number`, `input_hash`, `execution_time_ms`) are method params. `flush()` confirms state was written. Called only from fresh path (L704-706) -- matches StateSaved semantics.
**Alternatives:** Emit at call site L704-706 (rejected: would require threading params back out of method)

## Implementation Steps

### Step 1: Add event type imports to pipeline.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Open `llm_pipeline/pipeline.py`
2. In the import block at L35-42, add `InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved` to the `from llm_pipeline.events.types import (...)` block. Result:
   ```python
   from llm_pipeline.events.types import (
       PipelineStarted, PipelineCompleted, PipelineError,
       StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
       CacheLookup, CacheHit, CacheMiss, CacheReconstruction,
       LLMCallPrepared,
       ConsensusStarted, ConsensusAttempt, ConsensusReached, ConsensusFailed,
       TransformationStarting, TransformationCompleted,
       InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved,
   )
   ```

### Step 2: Emit InstructionsStored (cached path) after L573
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `pipeline.py` cached path, after `self._instructions[step.step_name] = instructions` (L573), insert:
   ```python
   if self._event_emitter:
       self._emit(InstructionsStored(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=step.step_name,
           instruction_count=len(instructions),
       ))
   ```

### Step 3: Emit InstructionsStored (fresh path) after L669
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `pipeline.py` fresh path, after `self._instructions[step.step_name] = instructions` (L669), insert:
   ```python
   if self._event_emitter:
       self._emit(InstructionsStored(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=step.step_name,
           instruction_count=len(instructions),
       ))
   ```

### Step 4: Emit InstructionsLogged (cached path) after L603
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `pipeline.py` cached path, after `step.log_instructions(instructions)` (L603), insert:
   ```python
   if self._event_emitter:
       self._emit(InstructionsLogged(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=step.step_name,
           logged_keys=[step.step_name],
       ))
   ```

### Step 5: Emit InstructionsLogged (fresh path) after L707
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `pipeline.py` fresh path, after `step.log_instructions(instructions)` (L707), insert:
   ```python
   if self._event_emitter:
       self._emit(InstructionsLogged(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=step.step_name,
           logged_keys=[step.step_name],
       ))
   ```

### Step 6: Emit ContextUpdated in _validate_and_merge_context after L372
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `_validate_and_merge_context` method, after `self._context.update(new_context)` (L372), insert:
   ```python
   if self._event_emitter:
       self._emit(ContextUpdated(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=step.step_name,
           new_keys=list(new_context.keys()),
           context_snapshot=dict(self._context),
       ))
   ```
   Note: `new_context` is guaranteed dict by this point (normalized above L372). `context_snapshot` is post-merge state (shallow copy).

### Step 7: Emit StateSaved in _save_step_state after L910 flush()
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** B

1. In `_save_step_state` method, after `self._real_session.flush()` (L910), insert:
   ```python
   if self._event_emitter:
       self._emit(StateSaved(
           run_id=self.run_id,
           pipeline_name=self.pipeline_name,
           step_name=step.step_name,
           step_number=step_number,
           input_hash=input_hash,
           execution_time_ms=float(execution_time_ms) if execution_time_ms is not None else 0.0,
       ))
   ```
   Note: `execution_time_ms` param is int; event field is float. Explicit cast handles the type annotation. None guard handles optional default.

### Step 8: Create tests/events/test_ctx_state_events.py
**Agent:** [available agents]
**Skills:** none
**Context7 Docs:** -
**Group:** C

1. Create `tests/events/test_ctx_state_events.py` following the same file structure as `tests/events/test_transformation_events.py`
2. Import from `conftest`: `MockProvider`, `SuccessPipeline`, `SimpleStep` (or reuse existing fixtures)
3. Add helper functions `_run_fresh(seeded_session, handler)` and `_run_cached(seeded_session, handler)` matching the pattern in `test_transformation_events.py`
4. Implement test classes:
   - `TestInstructionsStoredFreshPath`: verify event emitted, `instruction_count >= 1`, `step_name` correct
   - `TestInstructionsStoredCachedPath`: verify event emitted on second run (cache hit), `instruction_count >= 1`
   - `TestInstructionsLoggedFreshPath`: verify event emitted, `logged_keys == [step.step_name]`
   - `TestInstructionsLoggedCachedPath`: verify event emitted on cached path, `logged_keys == [step.step_name]`
   - `TestContextUpdatedFreshPath`: verify event emitted, `new_keys` matches keys in `process_instructions` return, `context_snapshot` contains merged keys
   - `TestContextUpdatedEmptyContext`: verify event emitted with `new_keys=[]` when step returns `None` or `{}` from `process_instructions` (needs a step that returns empty context -- add `EmptyContextStep` to conftest or inline)
   - `TestStateSavedFreshPath`: verify event emitted on fresh path, `step_number >= 0`, `input_hash` non-empty, `execution_time_ms >= 0.0`
   - `TestStateSavedNotOnCachedPath`: verify StateSaved NOT emitted on cache-hit path (only fresh path calls `_save_step_state`)
5. All test classes follow doc/class comment conventions from existing event test files

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| `_validate_and_merge_context` is called with `step` that may not always have `step_name` | Medium | Verified via research: `step` param is always `LLMStep` instance with `step_name` property (step.py L252-262). Both call sites pass `step`. |
| `execution_time_ms` is `None` at `_save_step_state` (default param) | Low | Explicit `float(x) if x is not None else 0.0` guard in emission block. |
| `context_snapshot` shallow copy reveals mutable inner values | Low | Matches existing convention (`dict(self._context)` used in prior steps). Downstream task 53 owns deeper test coverage. |
| Line number drift since research was done | Low | Implementation steps target code patterns (not line numbers) as primary anchor. Line numbers are reference only. |
| New test step class needed for empty-context test | Low | Add inline or to conftest. No structural change to conftest -- only addition. |

## Success Criteria
- [ ] `InstructionsStored` emitted on both fresh and cached paths with correct `instruction_count`
- [ ] `InstructionsLogged` emitted on both paths with `logged_keys=[step.step_name]`
- [ ] `ContextUpdated` emitted on both paths (via `_validate_and_merge_context`), always emits including when `new_keys=[]`
- [ ] `ContextUpdated.context_snapshot` reflects post-merge state
- [ ] `StateSaved` emitted only on fresh path with correct `step_number`, `input_hash`, `execution_time_ms`
- [ ] No emission when `_event_emitter` is `None` (guard pattern maintained)
- [ ] All 4 types added to import block in pipeline.py
- [ ] `pytest` passes with no new failures

## Phase Recommendation
**Risk Level:** low
**Reasoning:** All event types pre-defined, emission points validated, pattern is mechanical (guard+emit), no schema changes, no new dependencies. Only one method (`_validate_and_merge_context`) is shared between paths; single emission point is cleaner than duplicating at call sites.
**Suggested Exclusions:** testing, review
