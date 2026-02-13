# PLANNING

## Summary
Modify execute() in llm_pipeline/pipeline.py to emit 3 lifecycle events: PipelineStarted after validation/state init, PipelineCompleted before return, PipelineError via try/except wrapping step loop. Track start_time and current_step_name locals. Use zero-overhead guard pattern. Integration test with InMemoryEventHandler.

## Plugin & Agents
**Plugin:** python-development
**Subagents:** code, test
**Skills:** none

## Phases
1. Implementation - add event emissions to execute()
2. Testing - integration test for 3 lifecycle events

## Architecture Decisions

### Exception Scope
**Choice:** Wrap from `max_steps = ...` (line 445) through `return self` (line 573) in try/except
**Rationale:** Validation errors (lines 416-439) fire before pipeline logically "starts" and should not emit PipelineError. Wrapping after state init (line 443) preserves existing error semantics while allowing PipelineStarted emission.
**Alternatives:** Could wrap entire method but would emit PipelineError for validation failures (misleading), or wrap narrower scope but miss errors in action_after hooks

### step_name Tracking
**Choice:** Local variable `current_step_name: str | None = None`, updated from `step.step_name` each iteration
**Rationale:** `self._current_step` stores step CLASS (Type), not instance. `step.step_name` is instance property returning snake_case. Avoids duplicating CamelCase->snake_case conversion logic.
**Alternatives:** `self._current_step.__name__` gives "ConstraintExtractionStep" not "constraint_extraction", or call private _to_snake_case() helper (tight coupling)

### Traceback Inclusion
**Choice:** Include `traceback.format_exc()` in PipelineError
**Rationale:** Valuable debugging context on rare error path. CEO decision. Minimal overhead since error path is exceptional.
**Alternatives:** Leave traceback=None (doc 1 suggestion) loses stack trace info

### Import Strategy
**Choice:** Module-level imports for PipelineStarted/PipelineCompleted/PipelineError, inline `import traceback` inside except block
**Rationale:** Event types always imported if _emit() method exists. traceback only needed on error path. Balances zero-overhead with readability.
**Alternatives:** All inline (cluttered guards), all module-level (traceback import unused 99.9% of time)

## Implementation Steps

### Step 1: Add lifecycle event emissions to execute()
**Agent:** python-development:code
**Skills:** none
**Context7 Docs:** -
**Group:** A

1. Add module-level imports after line 42 TYPE_CHECKING block: `from llm_pipeline.events.types import PipelineStarted, PipelineCompleted, PipelineError`
2. After line 443 (`self.extractions = {}`), add local vars: `start_time = datetime.now(timezone.utc)` and `current_step_name: str | None = None`
3. Emit PipelineStarted after start_time capture: `if self._event_emitter: self._emit(PipelineStarted(run_id=self.run_id, pipeline_name=self.pipeline_name))`
4. Wrap lines 445-573 in try/except, structure:
   ```python
   try:
       max_steps = max(...)
       for step_index in range(max_steps):
           ...
           # After line 466 (self._current_step = step_class), add:
           current_step_name = step.step_name
           ...
       # Before line 572 (self._current_step = None):
       if self._event_emitter:
           execution_time_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
           # steps_executed includes skipped steps
           self._emit(PipelineCompleted(
               run_id=self.run_id,
               pipeline_name=self.pipeline_name,
               execution_time_ms=execution_time_ms,
               steps_executed=len(self._executed_steps)
           ))
   except Exception as e:
       if self._event_emitter:
           import traceback
           self._emit(PipelineError(
               run_id=self.run_id,
               pipeline_name=self.pipeline_name,
               step_name=current_step_name,
               error_type=type(e).__name__,
               error_message=str(e),
               traceback=traceback.format_exc()
           ))
       raise
   ```
5. Add inline comment on steps_executed line: `# includes skipped steps`

### Step 2: Integration test for pipeline lifecycle events
**Agent:** python-development:test
**Skills:** none
**Context7 Docs:** /pytest-dev/pytest, /pydantic/pydantic
**Group:** B

1. Create `tests/events/test_pipeline_lifecycle_events.py`
2. Test fixture: simple pipeline with 2 steps, InMemoryEventHandler attached
3. Test case `test_pipeline_lifecycle_success`: execute pipeline, assert 3 events emitted (PipelineStarted, PipelineCompleted with steps_executed=2, no PipelineError)
4. Test case `test_pipeline_lifecycle_error`: inject step that raises ValueError, assert PipelineStarted emitted, PipelineError emitted with error_type="ValueError", traceback not None, step_name populated, PipelineCompleted not emitted
5. Test case `test_pipeline_lifecycle_no_emitter`: execute without event_emitter, assert runs successfully with zero overhead (no events)
6. Verify execution_time_ms > 0 and is float type
7. Verify steps_executed count matches len(executed_steps) including skipped steps

## Risks & Mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Exception handling breaks existing error propagation | High | Preserve `raise` as final statement in except block. Existing tests verify behavior unchanged. |
| Event construction overhead when no emitter | Medium | Guard ALL event constructions with `if self._event_emitter:` before dataclass instantiation. |
| current_step_name out of sync if step loop changes | Low | Place assignment immediately after step instance creation (line ~467). Task 9 adds events inside loop but doesn't change structure. |
| traceback.format_exc() fails or returns empty | Low | Import in except block (always has exception context). traceback field allows None fallback. |

## Success Criteria

- [ ] PipelineStarted emitted after validation, before step loop
- [ ] PipelineCompleted emitted with correct execution_time_ms (float) and steps_executed (int)
- [ ] PipelineError emitted on exception with traceback, error_type, error_message, step_name
- [ ] Exception re-raised after PipelineError emission
- [ ] All event constructions guarded with `if self._event_emitter:`
- [ ] current_step_name tracked locally, updated each iteration from step.step_name
- [ ] Integration tests pass for success, error, and no-emitter cases
- [ ] Existing pipeline tests still pass (error propagation unchanged)

## Phase Recommendation

**Risk Level:** low
**Reasoning:** Narrow scope (3 event emissions + try/except wrapper), no schema changes, no external dependencies. Well-researched with validated line numbers. Event system already proven in task 6/7. Exception handling preserves existing behavior via re-raise.
**Suggested Exclusions:** testing, review
