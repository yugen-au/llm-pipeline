# Research: Step Execution Flow in pipeline.py execute()

## Overview

Task 9 adds 5 step lifecycle events to the step iteration loop in `PipelineConfig.execute()` (pipeline.py L459-583). Task 8 established the emission pattern: module-level imports, `if self._event_emitter:` guard before constructing events, `self._emit()` helper.

## Step Iteration Loop Structure

The execute() method (L407-611) processes steps via a positional loop:

```
L447  start_time = datetime.now(timezone.utc)
L448  current_step_name: str | None = None
L450  if self._event_emitter: _emit(PipelineStarted(...))   # Task 8
L456  try:
L457      max_steps = max(len(s.get_steps()) for s in self._strategies)
L459      for step_index in range(max_steps):       # MAIN LOOP
L460          step_num = step_index + 1
L461          selected_strategy = None
L462          step_def = None
L464-470    # Strategy selection inner loop
L472-473    # break if no step_def found
L475-479    # Step setup: create_step, set _current_step, current_step_name
L481-484    # should_skip() check -> continue
L486-502    # Logging and data preview
L503-504    # step_start = now(), input_hash = hash(...)
L506-532    # CACHED PATH: load cache, process_instructions, transform, extract
L533-577    # FRESH PATH: LLM calls, process_instructions, transform, extract, save state
L579        # self._executed_steps.add(step_class)
L580-583    # action_after hook
L585-594    # _emit(PipelineCompleted(...))          # Task 8
L599-611    # except: _emit(PipelineError(...))       # Task 8
```

## Event Emission Points

### 1. StepSelecting -- L459 (top of for loop, before strategy selection)

**Location**: Immediately inside `for step_index in range(max_steps):`, before the strategy selection inner loop (L464).

**Available data at this point**:
- `step_index` -- from loop variable
- `strategy_count` -- `len(self._strategies)`
- `step_name` -- None (not yet known, step not yet selected)
- `run_id`, `pipeline_name` -- from `self`

**Event fields** (from events/types.py L203-210):
```python
StepSelecting(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_index=step_index,
    strategy_count=len(self._strategies),
    # step_name defaults to None via StepScopedEvent
)
```

**Notes**: This fires even if no strategy provides a step at this index (loop breaks at L472). The absence of a subsequent StepSelected signals loop termination.

### 2. StepSelected -- after L479 (step created, name known)

**Location**: After `current_step_name = step.step_name` (L479), before the should_skip() check (L481).

**Available data at this point**:
- `step.step_name` -- derived from step class name (snake_case, "Step" suffix removed)
- `step_num` -- step_index + 1
- `selected_strategy.name` -- strategy name (snake_case)
- All base fields from `self`

**Event fields** (from events/types.py L213-221):
```python
StepSelected(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    step_number=step_num,
    strategy_name=selected_strategy.name,
)
```

### 3. StepSkipped -- inside should_skip() branch (L481-484)

**Location**: Inside `if step.should_skip():` block, after logger.info (L482), before `self._executed_steps.add()` (L483) and `continue` (L484).

**Available data**:
- `step.step_name`, `step_num` -- from prior setup
- `reason` -- static string `"should_skip returned true"` (should_skip() returns bool, no reason mechanism)

**Event fields** (from events/types.py L224-230):
```python
StepSkipped(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    step_number=step_num,
    reason="should_skip returned true",
)
```

**Notes**: After StepSkipped, the step is still added to `_executed_steps` (L483). No StepStarted/StepCompleted follow. Sequence: StepSelecting -> StepSelected -> StepSkipped.

### 4. StepStarted -- after skip check, before execution (between L486 and L503)

**Location**: After the should_skip() check passes (no skip), before actual work begins. Best placement: after the logging block (L486-501), before `step_start` capture (L503). This way step_start timing aligns with StepStarted emission.

Alternatively, emit StepStarted right before step_start to keep timing accurate. The step_start should capture time AFTER the event is emitted so execution_time_ms in StepCompleted reflects actual step work, not event emission overhead.

**Recommended placement**: Between L502 and L503 (after data preview logging, before step_start).

**Available data**:
- `step.step_name`, `step_num` -- from setup
- `step.system_instruction_key` -- may be None
- `step.user_prompt_key` -- may be None

**Event fields** (from events/types.py L233-241):
```python
StepStarted(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    step_number=step_num,
    system_key=step.system_instruction_key,
    user_key=step.user_prompt_key,
)
```

**Notes**: StepStarted fires for BOTH cached and fresh paths. The distinction between cached/fresh is a cache-level concern (Task 10).

### 5. StepCompleted -- after all step work, before _executed_steps.add (before L579)

**Location**: Just before `self._executed_steps.add(step_class)` (L579). This position is AFTER both the cached path (L510-532) and fresh path (L533-577) converge.

**Available data**:
- `step.step_name`, `step_num` -- from setup
- `execution_time_ms` -- calculated from `step_start` (L503). For fresh path, this is already calculated at L570-571. For cached path, it needs to be calculated here.

**Timing approach**: Calculate `execution_time_ms` uniformly for both paths at emission point:
```python
step_execution_time_ms = (datetime.now(timezone.utc) - step_start).total_seconds() * 1000
```

**Event fields** (from events/types.py L244-255):
```python
StepCompleted(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    step_number=step_num,
    execution_time_ms=step_execution_time_ms,
)
```

**Notes**: For cached steps, execution_time_ms reflects DB lookup + reconstruction time. For fresh steps, it includes LLM calls + extraction + state save. This is correct -- it measures wall-clock step time regardless of execution path.

## Event Sequence Diagrams

### Normal execution (no skip, no cache):
```
StepSelecting(step_index=0, strategy_count=N)
  StepSelected(step_name="foo", step_number=1, strategy_name="bar")
    StepStarted(step_name="foo", step_number=1, system_key=..., user_key=...)
      [... LLM calls, extraction, state save ...]  # Tasks 10-15
    StepCompleted(step_name="foo", step_number=1, execution_time_ms=...)
```

### Skipped step:
```
StepSelecting(step_index=0, strategy_count=N)
  StepSelected(step_name="foo", step_number=1, strategy_name="bar")
  StepSkipped(step_name="foo", step_number=1, reason="should_skip returned true")
```

### Loop termination (no step_def found):
```
StepSelecting(step_index=K, strategy_count=N)
  [no StepSelected -- loop breaks]
```

### Multi-step pipeline:
```
PipelineStarted
  StepSelecting -> StepSelected -> StepStarted -> StepCompleted    # Step 1
  StepSelecting -> StepSelected -> StepStarted -> StepCompleted    # Step 2
  StepSelecting -> [break, no step_def]                            # Loop end
PipelineCompleted
```

## Import Changes

Add to module-level import at L35:
```python
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
)
```

## Guard Pattern

Follow Task 8 pattern -- guard each emission with `if self._event_emitter:` to avoid constructing frozen dataclass objects when no emitter is configured:
```python
if self._event_emitter:
    self._emit(StepSelecting(...))
```

This provides zero-overhead when events are disabled, consistent with existing PipelineStarted/Completed/Error guards.

## Scope Boundaries (OUT OF SCOPE)

The following are handled by downstream tasks and must NOT be emitted in Task 9:
- **Task 10**: CacheLookup, CacheHit, CacheMiss, CacheReconstruction (cache blocks L506-532)
- **Task 11**: LLMCallPrepared, LLMCallStarting, LLMCallCompleted (LLM call blocks L542-557)
- **Task 13**: ConsensusStarted/Attempt/Reached/Failed (_execute_with_consensus L867-893)
- **Task 14**: ExtractionStarting/Completed/Error, TransformationStarting/Completed (step.py, transformation blocks)
- **Task 15**: InstructionsStored/Logged, ContextUpdated, StateSaved (context merge, state save methods)

## Deviation from Task Description

The task description references line numbers from a previous version of pipeline.py. Actual line numbers after Task 8 modifications:
- "line ~433" for step loop start -> actual L459
- "line ~444" for after strategy selection -> actual L475-479
- "line ~454" for should_skip -> actual L481
- "line ~551" for after executed_steps -> actual L579

No functional deviations from the task description's intent. All 5 events map cleanly to the described locations.
