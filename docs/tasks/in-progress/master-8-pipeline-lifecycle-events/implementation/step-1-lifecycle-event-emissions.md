# IMPLEMENTATION - STEP 1: LIFECYCLE EVENT EMISSIONS
**Status:** completed

## Summary
Added PipelineStarted, PipelineCompleted, PipelineError lifecycle event emissions to execute() in pipeline.py. All emissions guarded with zero-overhead `if self._event_emitter:` pattern. Step loop wrapped in try/except with re-raise for PipelineError. Local vars track start_time and current_step_name.

## Files
**Created:** none
**Modified:** llm_pipeline/pipeline.py
**Deleted:** none

## Changes
### File: `llm_pipeline/pipeline.py`

**1. Module-level import added (line 35)**
```python
# Before
if TYPE_CHECKING:
    ...
    from llm_pipeline.events.types import PipelineEvent

# After
from llm_pipeline.events.types import PipelineStarted, PipelineCompleted, PipelineError

if TYPE_CHECKING:
    ...
    from llm_pipeline.events.types import PipelineEvent
```

**2. Local vars + PipelineStarted emission (after state init, lines 447-454)**
```python
# Before
self.extractions = {}

max_steps = max(len(s.get_steps()) for s in self._strategies)

# After
self.extractions = {}

start_time = datetime.now(timezone.utc)
current_step_name: str | None = None

if self._event_emitter:
    self._emit(PipelineStarted(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
    ))
```

**3. current_step_name tracking (line 479)**
```python
# Before
self._current_step = step_class

if step.should_skip():

# After
self._current_step = step_class
current_step_name = step.step_name

if step.should_skip():
```

**4. try/except wrapper + PipelineCompleted + PipelineError (lines 456-610)**
```python
# Before
max_steps = max(...)
for step_index in range(max_steps):
    ...
self._current_step = None
return self

# After
try:
    max_steps = max(...)
    for step_index in range(max_steps):
        ...
    if self._event_emitter:
        pipeline_execution_time_ms = (
            datetime.now(timezone.utc) - start_time
        ).total_seconds() * 1000
        self._emit(PipelineCompleted(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            execution_time_ms=pipeline_execution_time_ms,
            steps_executed=len(self._executed_steps),  # includes skipped steps
        ))
    self._current_step = None
    return self
except Exception as e:
    if self._event_emitter:
        import traceback
        self._emit(PipelineError(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            step_name=current_step_name,
            error_type=type(e).__name__,
            error_message=str(e),
            traceback=traceback.format_exc(),
        ))
    raise
```

## Decisions
### Traceback import placement
**Choice:** Inline `import traceback` inside except block, guarded by `if self._event_emitter:`
**Rationale:** Zero-overhead on happy path. traceback module only loaded on error path when emitter is configured. CEO decision to include traceback.

### PipelineCompleted placement
**Choice:** Inside try block, after step loop, before `self._current_step = None`
**Rationale:** PipelineCompleted only emits on success. If any exception occurs, except block handles PipelineError instead. `self._current_step = None` and `return self` stay inside try for clean success path.

### execution_time_ms variable naming
**Choice:** Named `pipeline_execution_time_ms` to avoid shadowing per-step `execution_time_ms` at line 570
**Rationale:** Both vars exist in the same scope (try block). Distinct names prevent confusion.

## Verification
[x] PipelineStarted emitted after state init, before step loop
[x] PipelineCompleted emitted with execution_time_ms (float) and steps_executed (int)
[x] PipelineError emitted with traceback, error_type, error_message, step_name
[x] Exception re-raised after PipelineError emission
[x] All event constructions guarded with `if self._event_emitter:`
[x] current_step_name tracked locally, updated each iteration from step.step_name
[x] Existing 107 tests pass (no regressions)
[x] Validation errors (lines 418-441) NOT wrapped by try/except (fire before PipelineStarted)
