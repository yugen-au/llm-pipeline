# Step 2: Step Lifecycle Event Models & Emission Patterns

## Event Model Definitions (llm_pipeline/events/types.py)

### Inheritance Hierarchy

```
PipelineEvent (frozen=True, slots=True)
  |-- run_id: str (required)
  |-- pipeline_name: str (required)
  |-- timestamp: datetime (default=utc_now())
  |-- event_type: str (init=False, derived via __post_init__)
  |
  +-- StepScopedEvent (frozen=True, slots=True, _skip_registry=True)
        |-- step_name: str | None = None
        |
        +-- StepSelecting (kw_only=True)
        +-- StepSelected (kw_only=True)
        +-- StepSkipped (kw_only=True)
        +-- StepStarted (kw_only=True)
        +-- StepCompleted (kw_only=True)
```

All step lifecycle events use `kw_only=True`, meaning all fields must be passed as keyword arguments.

### StepSelecting (types.py:203-210)

- **Inherits:** StepScopedEvent -> PipelineEvent
- **EVENT_CATEGORY:** `CATEGORY_STEP_LIFECYCLE`
- **Docstring:** "Emitted when step selection begins. step_name defaults to None."
- **Fields (beyond base):**
  - `step_index: int` (required) -- 0-based loop index
  - `strategy_count: int` (required)
- **step_name:** Intentionally None -- fires BEFORE a step is chosen
- **Derived event_type:** `"step_selecting"`

```python
StepSelecting(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_index=step_index,
    strategy_count=len(self._strategies),
    # step_name defaults to None
)
```

### StepSelected (types.py:213-220)

- **Inherits:** StepScopedEvent -> PipelineEvent
- **EVENT_CATEGORY:** `CATEGORY_STEP_LIFECYCLE`
- **Docstring:** "Emitted when a step is selected for execution."
- **Fields (beyond base):**
  - `step_number: int` (required) -- 1-based (step_index + 1)
  - `strategy_name: str` (required)
- **step_name:** Should be populated (step instance exists)
- **Derived event_type:** `"step_selected"`

```python
StepSelected(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    step_number=step_num,
    strategy_name=selected_strategy.name,
)
```

### StepSkipped (types.py:223-231)

- **Inherits:** StepScopedEvent -> PipelineEvent
- **EVENT_CATEGORY:** `CATEGORY_STEP_LIFECYCLE`
- **Docstring:** "Emitted when a step is skipped."
- **Fields (beyond base):**
  - `step_number: int` (required)
  - `reason: str` (required)
- **step_name:** Should be populated
- **Derived event_type:** `"step_skipped"`

```python
StepSkipped(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    step_number=step_num,
    reason="should_skip returned true",
)
```

### StepStarted (types.py:233-242)

- **Inherits:** StepScopedEvent -> PipelineEvent
- **EVENT_CATEGORY:** `CATEGORY_STEP_LIFECYCLE`
- **Docstring:** "Emitted when a step begins execution."
- **Fields (beyond base):**
  - `step_number: int` (required)
  - `system_key: str | None = None` (optional)
  - `user_key: str | None = None` (optional)
- **step_name:** Should be populated
- **Derived event_type:** `"step_started"`

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

### StepCompleted (types.py:244-256)

- **Inherits:** StepScopedEvent -> PipelineEvent
- **EVENT_CATEGORY:** `CATEGORY_STEP_LIFECYCLE`
- **Docstring:** "Emitted when a step completes execution. execution_time_ms is float for sub-ms precision."
- **Fields (beyond base):**
  - `step_number: int` (required)
  - `execution_time_ms: float` (required)
- **step_name:** Should be populated
- **Derived event_type:** `"step_completed"`

```python
StepCompleted(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    step_name=step.step_name,
    step_number=step_num,
    execution_time_ms=(datetime.now(timezone.utc) - step_start).total_seconds() * 1000,
)
```

## _emit() Mechanism (pipeline.py:208-215)

```python
def _emit(self, event: "PipelineEvent") -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

- `self._event_emitter` set at `__init__` (line 156), type `Optional[PipelineEventEmitter]`, defaults to None
- Guards internally; call-site pattern adds OUTER guard to avoid event object construction:

```python
if self._event_emitter:
    self._emit(SomeEvent(...))  # object only constructed when emitter present
```

Double-guard (call-site + _emit internal) is intentional safety net. Established by task 8.

## Zero-Overhead Pattern (from Task 8)

```python
# CORRECT: event object not constructed when no emitter
if self._event_emitter:
    self._emit(PipelineStarted(run_id=self.run_id, pipeline_name=self.pipeline_name))

# INCORRECT: event object always constructed (wasteful)
self._emit(PipelineStarted(run_id=self.run_id, pipeline_name=self.pipeline_name))
```

## Task 8 Reference Implementation (pipeline.py:447-611)

### PipelineStarted (line 450-454)
```python
start_time = datetime.now(timezone.utc)
current_step_name: str | None = None

if self._event_emitter:
    self._emit(PipelineStarted(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
    ))
```

### PipelineCompleted (line 585-594)
```python
if self._event_emitter:
    pipeline_execution_time_ms = (
        datetime.now(timezone.utc) - start_time
    ).total_seconds() * 1000
    self._emit(PipelineCompleted(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        execution_time_ms=pipeline_execution_time_ms,
        steps_executed=len(self._executed_steps),
    ))
```

### PipelineError (line 599-611)
```python
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
    self._current_step = None
    raise
```

### Import (line 35)
```python
from llm_pipeline.events.types import PipelineStarted, PipelineCompleted, PipelineError
```

## execute() Step Loop Structure (pipeline.py:457-581)

Annotated with emission points:

```
Line 447:  start_time = datetime.now(timezone.utc)
Line 448:  current_step_name: str | None = None
Line 450:  [PipelineStarted emission]
Line 456:  try:
Line 457:      max_steps = max(len(s.get_steps()) for s in self._strategies)
Line 459:      for step_index in range(max_steps):
Line 460:          step_num = step_index + 1
                   >>> EMIT StepSelecting (step_index, strategy_count) <<<
Line 462:          selected_strategy = None
Line 463:          step_def = None
Line 464-469:     for strategy in self._strategies: [strategy selection]
Line 472:          if not step_def: break
                   (StepSelecting with no StepSelected = no strategy handled this index)
Line 475:          self._current_strategy = selected_strategy
Line 476:          step = step_def.create_step(pipeline=self)
Line 477:          step_class = type(step)
Line 478:          self._current_step = step_class
Line 479:          current_step_name = step.step_name
                   >>> EMIT StepSelected (step_name, step_number, strategy_name) <<<
Line 481:          if step.should_skip():
Line 482-484:         [log + add to executed_steps + continue]
                       >>> EMIT StepSkipped (step_name, step_number, reason) <<<
                       (before continue, after logging)
Line 486:          [non-skip logging]
                   >>> EMIT StepStarted (step_name, step_number, system_key, user_key) <<<
Line 503:          step_start = datetime.now(timezone.utc)
                   NOTE: step_start MUST be captured before StepStarted OR timing adjusted
                         Currently step_start is AFTER logging. For accurate StepCompleted timing,
                         step_start should be captured before or at StepStarted emission.
Line 507-577:     [cached vs fresh execution paths]
Line 579:          self._executed_steps.add(step_class)
                   >>> EMIT StepCompleted (step_name, step_number, execution_time_ms) <<<
                   (after adding to executed_steps, timing from step_start)
Line 580-583:     [action_after handling]
Line 585:      [PipelineCompleted emission]
```

## Emission Point Details

### 1. StepSelecting
- **Location:** Top of `for step_index in range(max_steps)` loop body, BEFORE strategy selection
- **Data available:** `step_index` (loop var), `len(self._strategies)` (always available)
- **step_name:** None (no step instance yet)
- **Note:** Emitted even when no step_def found (break at line 472). Useful signal for debugging.

### 2. StepSelected
- **Location:** After `step = step_def.create_step(pipeline=self)` and `current_step_name = step.step_name`
- **Data available:** `step.step_name`, `step_num`, `selected_strategy.name`
- **step_name:** `step.step_name` (snake_case, e.g. "widget_detection")
- **strategy_name:** `selected_strategy.name` (snake_case from PipelineStrategy.name property)

### 3. StepSkipped
- **Location:** Inside `if step.should_skip():` block, before `continue`
- **Data available:** `step.step_name`, `step_num`
- **reason:** `"should_skip returned true"` (should_skip() returns bool, no custom reason)
- **Note:** `self._executed_steps.add(step_class)` at line 483 happens BEFORE continue. Emit after that add.

### 4. StepStarted
- **Location:** After skip check, before execution (fresh or cached)
- **Data available:** `step.step_name`, `step_num`, `step.system_instruction_key`, `step.user_prompt_key`
- **system_key / user_key:** These are str (or None if auto-discovery partially failed)
- **Note:** Move `step_start` capture to just before or at StepStarted for accurate timing

### 5. StepCompleted
- **Location:** After `self._executed_steps.add(step_class)` at line 579
- **Data available:** `step.step_name`, `step_num`, timing from `step_start`
- **execution_time_ms:** `float` -- `(datetime.now(timezone.utc) - step_start).total_seconds() * 1000`
- **Applies to both cached and fresh paths:** step_start is set at line 503 before cache/fresh branch

## Event Sequences Per Step Iteration

### Normal execution (no skip, no error):
```
StepSelecting -> StepSelected -> StepStarted -> StepCompleted
```

### Skipped step:
```
StepSelecting -> StepSelected -> StepSkipped
```
(No StepStarted or StepCompleted)

### No strategy handles step index:
```
StepSelecting
```
(Loop breaks, no further events for this index)

### Error during step execution:
```
StepSelecting -> StepSelected -> StepStarted -> PipelineError
```
(No StepCompleted; PipelineError from outer try/except catches it)

## Import Requirements

Current pipeline.py line 35:
```python
from llm_pipeline.events.types import PipelineStarted, PipelineCompleted, PipelineError
```

Must add:
```python
from llm_pipeline.events.types import (
    PipelineStarted, PipelineCompleted, PipelineError,
    StepSelecting, StepSelected, StepSkipped, StepStarted, StepCompleted,
)
```

Module-level import follows established task 8 pattern. Zero-overhead achieved via call-site `if self._event_emitter:` guard (skips construction, not import).

## InMemoryEventHandler (events/handlers.py:84-136)

Test utility. Key methods:
- `emit(event)` -- stores `event.to_dict()` in thread-safe list
- `get_events(run_id=None)` -- returns list of dicts, optionally filtered
- `get_events_by_type(event_type, run_id=None)` -- filters by event_type string
- `clear()` -- removes all events

Test pattern from task 8 (test_pipeline_lifecycle_events.py):
```python
handler = InMemoryEventHandler()
pipeline = SomePipeline(session=session, provider=provider, event_emitter=handler)
pipeline.execute(data="test", initial_context={})
events = handler.get_events()
started_events = [e for e in events if e["event_type"] == "step_started"]
```

## Timing Considerations

`step_start` (line 503) is captured AFTER the skip check and AFTER non-skip logging (lines 486-501). This means:
- StepStarted is emitted ~line 486, but step_start is set at ~line 503
- For StepCompleted timing to be accurate, either:
  a) Move step_start capture to just before/at StepStarted emission (before line 486), OR
  b) Accept that timing includes data preview logging overhead

Recommendation: Move `step_start = datetime.now(timezone.utc)` to just before StepStarted emission for clean semantics (timing = execution, not logging).

## Scope Boundaries (Out of Scope)

Per downstream tasks 10-15, the following are NOT part of task 9:
- Cache events (CacheLookup, CacheHit, CacheMiss, CacheReconstruction) -- task 10
- LLM call events (LLMCallPrepared, LLMCallStarting, LLMCallCompleted) -- task 11
- Consensus events (ConsensusStarted, etc.) -- task 13
- Extraction/transformation events -- task 14
- Context/state events (InstructionsStored, ContextUpdated, StateSaved) -- task 15

## Summary for Implementation

1. Add 5 step event types to pipeline.py import
2. Emit StepSelecting at top of loop body (step_name=None)
3. Emit StepSelected after step creation and step_name capture
4. Emit StepSkipped inside should_skip() true branch (before continue)
5. Move step_start capture before StepStarted emission
6. Emit StepStarted after skip check, before execution
7. Emit StepCompleted after executed_steps.add(), with float timing from step_start
8. All emissions guarded by `if self._event_emitter:` for zero overhead
9. No new fields or model changes needed -- all 5 events already defined in types.py
