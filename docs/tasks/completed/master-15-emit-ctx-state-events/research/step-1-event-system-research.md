# RESEARCH - STEP 1: EVENT SYSTEM RESEARCH
**Status:** complete

## Event System Architecture

### Base Classes
- `PipelineEvent` (frozen dataclass, slots=True): base with run_id, pipeline_name, timestamp, auto-derived event_type
- `StepScopedEvent(PipelineEvent)`: adds optional step_name, skipped from registry via `_skip_registry = True`
- Auto-registration via `__init_subclass__` into `_EVENT_REGISTRY` dict keyed by snake_case event_type

### Emitter Infrastructure
- `PipelineEventEmitter`: runtime_checkable Protocol with `emit(event) -> None`
- `CompositeEmitter`: dispatches to multiple handlers with per-handler error isolation
- Handlers: `LoggingEventHandler` (category-based log levels), `InMemoryEventHandler` (thread-safe list), `SQLiteEventHandler` (session-per-emit)
- Pipeline stores emitter as `self._event_emitter` (None = disabled)
- `self._emit(event)` forwards to emitter if not None

### Emission Pattern (established convention)
```python
if self._event_emitter:
    self._emit(EventType(
        run_id=self.run_id,
        pipeline_name=self.pipeline_name,
        step_name=step.step_name,
        # event-specific fields
        timestamp=datetime.now(timezone.utc),  # explicit timestamp optional (default_factory exists)
    ))
```
All events use kw_only=True construction. Guard check prevents any overhead when emitter is None.

### Category Constants
- CATEGORY_INSTRUCTIONS_CONTEXT = "instructions_context" (log level: DEBUG)
- CATEGORY_STATE = "state" (log level: DEBUG)

## 4 Target Events (Already Defined in events/types.py)

### 1. InstructionsStored (L426-432)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class InstructionsStored(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_INSTRUCTIONS_CONTEXT
    instruction_count: int
```

**Emission points in pipeline.py:**
- **Cached path (L573):** After `self._instructions[step.step_name] = instructions`
- **Fresh path (L669):** After `self._instructions[step.step_name] = instructions`
- `instruction_count = len(instructions)` (instructions is always a list)

### 2. InstructionsLogged (L435-445)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class InstructionsLogged(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_INSTRUCTIONS_CONTEXT
    logged_keys: list[str] = field(default_factory=list)
```

**Emission points in pipeline.py:**
- **Cached path (L603):** After `step.log_instructions(instructions)`
- **Fresh path (L707):** After `step.log_instructions(instructions)`
- `logged_keys`: `log_instructions()` is void (no return value). Reasonable default: `[step.step_name]` -- the key under which instructions are stored in `self._instructions`. This matches the docstring "instruction keys that were logged."

### 3. ContextUpdated (L448-459)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class ContextUpdated(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_INSTRUCTIONS_CONTEXT
    new_keys: list[str]
    context_snapshot: dict[str, Any]
```

**Emission point in pipeline.py:**
- **_validate_and_merge_context() (L350-372):** After `self._context.update(new_context)` on L372
- Called from both cached (L575) and fresh (L671) paths
- `new_keys = list(new_context.keys())` -- may be [] if new_context was None (converted to {} on L364)
- `context_snapshot = dict(self._context)` -- shallow copy after merge; task description says "full context_snapshot for UI diff display"
- Method has access to self._emit, self.run_id, self.pipeline_name. step_name available via `step.step_name` but _validate_and_merge_context only receives `step` (the LLMStep instance), not step_name string -- `step.step_name` property works.
- Note: new_context may be {} (from None conversion or empty dict return). Emitting ContextUpdated with new_keys=[] is valid -- signals context was validated but nothing new added.

### 4. StateSaved (L530-538)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class StateSaved(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_STATE
    step_number: int
    input_hash: str
    execution_time_ms: float
```

**Emission point in pipeline.py:**
- **_save_step_state() (L868-910):** After `self._real_session.flush()` on L910
- Called only on fresh path (L704-706). Not called on cached path (no new state to save).
- All required fields available as method params: step_number, input_hash, execution_time_ms
- step_name available via `step.step_name`
- Note: execution_time_ms param is int but event field is float. Cast not needed (int is subtype of float in Python).

## Imports Needed

Add to pipeline.py L35-42 import block:
```python
from llm_pipeline.events.types import (
    # existing imports...
    InstructionsStored, InstructionsLogged, ContextUpdated, StateSaved,
)
```

## Existing Emission Reference (pipeline.py)

| Line | Event | Path |
|------|-------|------|
| 458 | PipelineStarted | both |
| 468 | StepSelecting | both |
| 497 | StepSelected | both |
| 508 | StepSkipped | both |
| 536 | StepStarted | both |
| 551 | CacheLookup | cache-enabled |
| 561 | CacheHit | cached |
| 580 | TransformationStarting | cached |
| 593 | TransformationCompleted | cached |
| 608 | CacheReconstruction | cached |
| 621 | CacheMiss | fresh+cache-enabled |
| 638 | LLMCallPrepared | fresh |
| 676 | TransformationStarting | fresh |
| 689 | TransformationCompleted | fresh |
| 712 | StepCompleted | both |
| 730 | PipelineCompleted | both |
| 743 | PipelineError | error |

## Test Infrastructure

- Fixtures in `tests/events/conftest.py`: MockProvider, seeded_session, in_memory_handler
- Existing pipelines: SuccessPipeline (SimpleStep), ExtractionPipeline (ItemDetectionStep), TransformationPipeline (TransformationStep)
- Test pattern: run pipeline with InMemoryEventHandler, filter events by event_type, assert fields
- Both SuccessPipeline (with SimpleStep + SimpleContext) and ExtractionPipeline work for InstructionsStored/InstructionsLogged/ContextUpdated tests
- StateSaved requires fresh path (use_cache=False or no cache) -- SuccessPipeline works

## Upstream Task 9 Deviations
None observed. Task 9 (step lifecycle events) established the guard+emit pattern now used throughout.

## Downstream Task 53
Not fetched (errored). Out of scope per contract.

## Decisions
- logged_keys for InstructionsLogged: use `[step.step_name]` as reasonable default matching "instruction keys that were logged" docstring
- ContextUpdated emits even when new_keys is empty (context was validated, just no new keys added)
- StateSaved only on fresh path (matches existing _save_step_state call pattern)
