# Step 2: Event System Models & Emission Patterns

## Event Model Definitions (llm_pipeline/events/types.py)

### PipelineStarted (line 168-172)
- **Inherits:** `PipelineEvent` (direct)
- **NOT kw_only** -- positional args allowed
- **Fields (all from base):**
  - `run_id: str` (required)
  - `pipeline_name: str` (required)
  - `timestamp: datetime` (default=`utc_now()`)
  - `event_type: str` (init=False, derived="pipeline_started")
- **EVENT_CATEGORY:** `CATEGORY_PIPELINE_LIFECYCLE`
- **No additional fields**

```python
PipelineStarted(run_id=self.run_id, pipeline_name=self.pipeline_name)
```

### PipelineCompleted (line 175-182)
- **Inherits:** `PipelineEvent` (direct)
- **kw_only=True** -- all fields keyword-only
- **Fields from base:** run_id, pipeline_name, timestamp, event_type
- **Additional fields:**
  - `execution_time_ms: float` (required)
  - `steps_executed: int` (required)
- **EVENT_CATEGORY:** `CATEGORY_PIPELINE_LIFECYCLE`

```python
PipelineCompleted(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    execution_time_ms=elapsed_ms,
    steps_executed=len(self._executed_steps),
)
```

### PipelineError (line 185-197)
- **Inherits:** `StepScopedEvent` -> `PipelineEvent`
- **kw_only=True** -- all fields keyword-only
- **Fields from base:** run_id, pipeline_name, timestamp, event_type
- **Fields from StepScopedEvent:** `step_name: str | None = None`
- **Additional fields:**
  - `error_type: str` (required)
  - `error_message: str` (required)
  - `traceback: str | None = None` (optional)
- **EVENT_CATEGORY:** `CATEGORY_PIPELINE_LIFECYCLE`

```python
PipelineError(
    run_id=self.run_id,
    pipeline_name=self.pipeline_name,
    error_type=type(exc).__name__,
    error_message=str(exc),
    step_name=current_step_name,  # str | None
    traceback=tb_str,             # str | None
)
```

## Emitter Interface (llm_pipeline/events/emitter.py)

### PipelineEventEmitter Protocol
- `@runtime_checkable` Protocol
- Single method: `emit(self, event: PipelineEvent) -> None`

### CompositeEmitter
- Dispatches to multiple handlers sequentially
- Per-handler error isolation via try/except + logger.exception
- Handlers stored as immutable tuple

### PipelineConfig._emit() (pipeline.py line 206-213)
```python
def _emit(self, event: "PipelineEvent") -> None:
    if self._event_emitter is not None:
        self._event_emitter.emit(event)
```

## Zero-Overhead Call-Site Pattern

Per Task 7 validated research, event objects must NOT be constructed when no emitter configured. Guard at call site:

```python
if self._event_emitter:
    self._emit(PipelineStarted(run_id=self.run_id, pipeline_name=self.pipeline_name))
```

When `self._event_emitter is None`: skips event construction entirely. Double-check in `_emit()` is intentional safety net.

## Available Timing Utilities

| Utility | Location | Usage |
|---------|----------|-------|
| `utc_now()` | `llm_pipeline.state` | Returns `datetime.now(timezone.utc)` -- used as default_factory for event timestamps |
| `datetime.now(timezone.utc)` | `pipeline.py` line 490 | Already used for per-step timing in execute() |
| Execution time calc | `pipeline.py` line 557-558 | `int((datetime.now(timezone.utc) - step_start).total_seconds() * 1000)` |

**Pipeline-level timing:** Need `pipeline_start = datetime.now(timezone.utc)` at top of execute(), then `(datetime.now(timezone.utc) - pipeline_start).total_seconds() * 1000` for PipelineCompleted.execution_time_ms (float, not int -- per type annotation).

## Data Availability in execute()

| Field | Source | Available at |
|-------|--------|-------------|
| `self.run_id` | `__init__` line 190 | Always |
| `self.pipeline_name` | Property (line 226) | Always |
| `self._event_emitter` | `__init__` line 154 | Always |
| `self._executed_steps` | Set, populated in loop (line 566) | After loop for count |
| `self._current_step` | Set per iteration (line 466), cleared to None after loop (line 572) | During loop for PipelineError.step_name |
| step.step_name | Step instance attribute | During loop iteration only |

## PipelineError step_name Resolution

During loop: `step.step_name` (str) available on the step instance.
Outside loop / before step creation: `self._current_step` is the step Type class.
After loop: `self._current_step` is set to None (line 572).

For PipelineError emitted in except block:
- Track `current_step_name: str | None = None` variable, updated each iteration
- Or derive from `self._current_step` class name if set (less reliable since step_name comes from instance)

## Handler Implementations (llm_pipeline/events/handlers.py)

All handlers implement `PipelineEventEmitter` protocol:

| Handler | emit() behavior | Category level for pipeline_lifecycle |
|---------|----------------|--------------------------------------|
| LoggingEventHandler | Logs via Python logger; level from EVENT_CATEGORY map | INFO |
| InMemoryEventHandler | Stores event.to_dict() in thread-safe list | N/A (stores all) |
| SQLiteEventHandler | Persists PipelineEventRecord row with event_data=event.to_dict() | N/A (persists all) |

## Existing Test Pattern (tests/test_pipeline.py line 484-531)

MockEmitter class captures events in list. Tests verify:
- `_emit()` no-ops when emitter is None
- `_emit()` forwards to emitter.emit()
- MockEmitter satisfies PipelineEventEmitter protocol

## Summary for Implementation

1. **PipelineStarted**: Emit after validation, before step loop. No extra fields.
2. **PipelineCompleted**: Emit after loop, before `return self`. Needs pipeline_start timer + len(self._executed_steps).
3. **PipelineError**: Emit in except block wrapping execute body. Needs traceback import. Re-raise after emit.
4. **All emissions**: Guard with `if self._event_emitter:` before constructing event.
5. **execution_time_ms**: Use `float` (matches PipelineCompleted type annotation), not `int`.
6. **traceback**: Use `traceback.format_exc()` for full traceback string.
