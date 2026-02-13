# Research: Pipeline execute() Architecture for Lifecycle Events

## execute() Method Overview

**File**: `llm_pipeline/pipeline.py`, lines 405-573
**Signature**: `execute(self, data, initial_context, use_cache=False, consensus_polling=None) -> PipelineConfig`

### Flow (line-by-line)

| Phase | Lines | Description |
|-------|-------|-------------|
| Validation | 416-422 | Provider + strategies checks (raises ValueError) |
| Setup | 424-434 | PromptService creation, consensus config parsing (raises ValueError for bad config) |
| State init | 441-443 | Context copy, data/extractions reset |
| Max steps | 445 | `max_steps = max(len(s.get_steps()) for s in self._strategies)` |
| Step loop | 447-571 | `for step_index in range(max_steps):` main execution |
| Cleanup | 572-573 | `self._current_step = None; return self` |

### Error Handling

**No existing try/except in execute()**. All exceptions propagate uncaught. Exceptions can originate from:
- Validation: ValueError (lines 416-422, 436-439)
- Step loop: Any exception from LLM calls, extractions, transformations, process_instructions

---

## Event Emitter Wiring (from task 7)

- `self._event_emitter`: stored in `__init__` (line 154), Optional[PipelineEventEmitter], defaults to None
- `self._emit(event)`: helper method (lines 206-213), guards with `if self._event_emitter is not None`
- Zero-overhead convention: guard `if self._event_emitter:` before constructing event dataclass, to skip frozen dataclass allocation when no emitter configured

---

## Event Type Signatures (from task 6, source of truth)

All events are frozen dataclasses with `slots=True`.

### PipelineStarted (types.py:168-172)
```python
@dataclass(frozen=True, slots=True)
class PipelineStarted(PipelineEvent):
    # Inherited: run_id (str), pipeline_name (str), timestamp (datetime, default=utc_now)
    # No additional fields
```

### PipelineCompleted (types.py:175-182)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineCompleted(PipelineEvent):
    execution_time_ms: float  # note: float, not int
    steps_executed: int
```

### PipelineError (types.py:185-198)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class PipelineError(StepScopedEvent):
    # Inherited: run_id, pipeline_name, timestamp, step_name (str|None)
    error_type: str
    error_message: str
    traceback: str | None = None
```

---

## Task Spec vs Actual Types (Deviations)

Task 8 spec was written before task 6 implemented the event types. Key differences:

| Spec Field | Actual Field | Notes |
|-----------|-------------|-------|
| PipelineStarted.strategy_count | does not exist | PipelineStarted has no extra fields beyond base |
| PipelineStarted.use_cache | does not exist | same |
| PipelineStarted.use_consensus | does not exist | same |
| PipelineCompleted.total_time_ms (int) | execution_time_ms (float) | field renamed, type changed |
| PipelineError.step_name | step_name (str\|None) | inherited from StepScopedEvent, matches |
| PipelineError.traceback | traceback (str\|None) | exists in types, not mentioned in task spec |

**Resolution**: Use actual types.py definitions as source of truth.

---

## Injection Points

### 1. PipelineStarted - Line 443 (after state init, before max_steps)

Insert between line 443 and line 445:
```python
# line 443: self.extractions = {}
# --- INSERT HERE ---
start_time = datetime.now(timezone.utc)
if self._event_emitter:
    self._emit(PipelineStarted(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
    ))
# line 445: max_steps = max(...)
```

**Rationale**: All validation passed, state initialized. Event signals "execution is beginning". `start_time` captured here for PipelineCompleted.execution_time_ms.

### 2. PipelineCompleted - Line 572 (before return self)

Insert between line 571 (end of step loop) and line 572:
```python
# line 571: (end of for loop body)
# --- INSERT HERE ---
if self._event_emitter:
    self._emit(PipelineCompleted(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        execution_time_ms=(datetime.now(timezone.utc) - start_time).total_seconds() * 1000,
        steps_executed=len(self._executed_steps),
    ))
# line 572: self._current_step = None
```

**Rationale**: All steps complete. `steps_executed` uses `len(self._executed_steps)` which includes both executed and skipped steps (matching existing semantics where `_executed_steps.add()` is called for both paths).

### 3. PipelineError - Wrap step loop in try/except

Wrap from after PipelineStarted through to return:
```python
start_time = datetime.now(timezone.utc)
if self._event_emitter:
    self._emit(PipelineStarted(...))

try:
    max_steps = max(len(s.get_steps()) for s in self._strategies)
    for step_index in range(max_steps):
        ... (existing loop body unchanged)

    if self._event_emitter:
        self._emit(PipelineCompleted(...))

    self._current_step = None
    return self

except Exception as e:
    if self._event_emitter:
        self._emit(PipelineError(
            run_id=self.run_id,
            pipeline_name=self.pipeline_name,
            step_name=getattr(self._current_step, '__name__', None) if self._current_step else None,
            error_type=type(e).__name__,
            error_message=str(e),
        ))
    raise
```

**Rationale**:
- PipelineError only emitted if PipelineStarted was already emitted (logical pairing)
- Validation errors (lines 416-439) are NOT wrapped - they fire before pipeline "starts"
- `step_name` derived from `self._current_step` (set at line 466 during loop, None before loop starts)
- `raise` re-raises original exception (non-destructive)
- `traceback` field intentionally omitted (None default) - keeps events lightweight; traceback available in the raised exception

---

## Step Loop Internal Structure (context for task 9)

Lines 447-571 step loop internals (OUT OF SCOPE for task 8, documented for context):
- 452-458: Strategy selection + step_def lookup
- 460-461: Break if no step_def
- 463-466: Set current_strategy, create step instance, set _current_step
- 468-471: should_skip() check (skipped steps still added to _executed_steps)
- 473-479: Logging
- 490-563: Step execution (cached vs fresh paths)
- 566-570: Post-step (add to _executed_steps, action_after)

---

## Available Pipeline Attributes for Event Construction

| Attribute | Available At | Value |
|-----------|-------------|-------|
| self.run_id | __init__ (line 190) | UUID string |
| self.pipeline_name | property (line 226) | snake_case derived from class name |
| self._executed_steps | __init__ (line 182) | set, accumulates during loop |
| self._current_step | __init__ (line 183) | Type or None, set during loop |
| self._strategies | __init__ (line 168) | list of PipelineStrategy |

---

## Import Requirements

The following import is needed in pipeline.py for event construction:
```python
# Already present (line 42, TYPE_CHECKING):
from llm_pipeline.events.types import PipelineEvent

# Need to add inside TYPE_CHECKING block:
from llm_pipeline.events.types import PipelineStarted, PipelineCompleted, PipelineError
```

**Note**: Since events are constructed at runtime (not just type annotations), these imports must be OUTSIDE TYPE_CHECKING or use runtime imports. Options:
1. Move to top-level imports (simplest, but adds import overhead)
2. Inline import inside `if self._event_emitter:` guard (zero overhead when no emitter)
3. Import at top of execute() method (amortized, only when executing)

Recommendation: Import inside `if self._event_emitter:` guards for true zero-overhead, or at top of execute() for cleaner code. Defer decision to implementation phase.

---

## datetime Import

`datetime` and `timezone` are already imported at line 16:
```python
from datetime import datetime, timezone
```
No additional import needed for `start_time = datetime.now(timezone.utc)`.
