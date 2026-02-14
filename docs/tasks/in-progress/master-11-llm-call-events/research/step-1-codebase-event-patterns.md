# Research Step 1: Codebase Event Patterns

## 1. Event System Architecture

### Event Type Hierarchy
```
PipelineEvent (frozen dataclass, slots=True)
  |-- run_id, pipeline_name, timestamp, event_type (derived)
  |-- auto-registers in _EVENT_REGISTRY via __init_subclass__
  |-- to_dict() / to_json() serialization
  |
  +-- StepScopedEvent (_skip_registry=True, intermediate base)
        |-- step_name: str | None
        |
        +-- LLMCallPrepared  (CATEGORY_LLM_CALL)
        +-- LLMCallStarting  (CATEGORY_LLM_CALL)
        +-- LLMCallCompleted (CATEGORY_LLM_CALL)
        +-- StepStarted, StepCompleted, etc.
```

### Event Emission Pattern
All events emitted in `pipeline.py` via `self._emit(EventClass(...))`, guarded by `if self._event_emitter:`. The `_emit()` method (L211-218) delegates to whatever `PipelineEventEmitter` protocol implementor was passed to constructor.

### Emitter Infrastructure
- `PipelineEventEmitter` -- runtime-checkable Protocol with single `emit(event)` method
- `CompositeEmitter` -- dispatches to multiple handlers with per-handler error isolation
- `InMemoryEventHandler` -- thread-safe list store, used in tests
- `LoggingEventHandler` -- logs with category-based level mapping
- `SQLiteEventHandler` -- persists to `pipeline_events` table

### Category Constants
`CATEGORY_LLM_CALL = "llm_call"` already exists in `events/types.py` L30. `DEFAULT_LEVEL_MAP` in `handlers.py` L38 already maps it to `logging.INFO`.

## 2. Existing LLM Call Event Definitions

All three target events are already defined in `events/types.py` L304-344:

### LLMCallPrepared (L307-315)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallPrepared(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    call_count: int
    system_key: str | None = None
    user_key: str | None = None
```

### LLMCallStarting (L318-326)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallStarting(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    call_index: int
    rendered_system_prompt: str
    rendered_user_prompt: str
```

### LLMCallCompleted (L329-344)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallCompleted(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    call_index: int
    raw_response: str | None
    parsed_result: dict[str, Any] | None
    model_name: str | None
    attempt_count: int
    validation_errors: list[str] = field(default_factory=list)
```

All three are already exported in `__all__` (L572-574) and registered via auto-registration.

## 3. Current Execution Flow (pipeline.py L571-615)

Non-cached execution path (the path that needs LLM call events):

```
L580: call_params = step.prepare_calls()          # returns List[StepCallParams]
L581: instructions = []
L583: for params in call_params:                   # loop over individual calls
L584:   call_kwargs = step.create_llm_call(**params)  # builds dict with keys, vars, result_class
L586:   call_kwargs["provider"] = self._provider
L587:   call_kwargs["prompt_service"] = prompt_service
L589-592: consensus branch
L594:   instruction = execute_llm_step(**call_kwargs)  # RENDERS prompts + calls LLM
L595:   instructions.append(instruction)
```

### Event Insertion Points
- **LLMCallPrepared**: After L580 (`step.prepare_calls()`), before the for-loop
- **LLMCallStarting**: Inside loop, before `execute_llm_step()` -- needs rendered prompts
- **LLMCallCompleted**: Inside loop, after `execute_llm_step()` -- needs LLMCallResult

## 4. The Core Challenge: Data Visibility

`execute_llm_step()` (executor.py L21-130) currently:
1. Renders system prompt via `prompt_service.get_system_prompt()` or `get_prompt()` (L82-94)
2. Renders user prompt via `prompt_service.get_user_prompt()` (L97-102)
3. Calls `provider.call_structured()` which returns `LLMCallResult` (L105-111)
4. Returns only the validated Pydantic model instance (`T`) -- discards rendered prompts AND LLMCallResult

The rendered prompts and LLMCallResult are **local variables inside execute_llm_step()** and never exposed to pipeline.py. This is the central problem.

### LLMCallResult fields needed by LLMCallCompleted:
- `raw_response: str | None`
- `parsed: dict[str, Any] | None` (maps to `parsed_result`)
- `model_name: str | None`
- `attempt_count: int`
- `validation_errors: list[str]`

## 5. Integration Options Analysis

### Option A: Return Enriched Result from execute_llm_step()
Create new `LLMStepExecutionResult` dataclass wrapping instruction + rendered prompts + LLMCallResult. Pipeline unpacks it for events.

- **Pro**: Clean separation, executor stays event-unaware
- **Pro**: All emission stays in pipeline.py (consistent with Task 9 pattern)
- **Con**: Changes return type of `execute_llm_step()` (breaking for external callers)
- **Mitigation**: Add `return_metadata=True` flag, or create separate function

### Option B: Pass Emitter into execute_llm_step()
Add optional `event_emitter` + context params. Emit inside executor.

- **Pro**: Events fire at exact right moment
- **Con**: Breaks pattern -- ALL other events emitted from pipeline.py, not executor
- **Con**: Couples executor to event system

### Option C: Split Rendering from Calling
Extract prompt rendering into pipeline, then pipeline emits LLMCallStarting, then calls provider directly.

- **Pro**: Pipeline owns everything
- **Con**: Duplicates executor logic, significant refactoring

### Option D (Recommended): New Function + Backward Compat
Add `execute_llm_step_with_metadata()` that returns enriched result. Pipeline calls it; old `execute_llm_step()` wraps it for backward compat.

- **Pro**: Zero breaking changes
- **Pro**: All emission stays in pipeline.py
- **Pro**: Minimal refactoring
- **Con**: Slight code duplication (thin wrapper)

## 6. Consensus Path (pipeline.py L916-942)

`_execute_with_consensus()` also calls `execute_llm_step()` in a loop (L922). LLM call events must fire here too. Each consensus attempt is a separate LLM call requiring its own LLMCallStarting/LLMCallCompleted pair.

```python
def _execute_with_consensus(self, call_kwargs, consensus_threshold, maximum_step_calls):
    for attempt in range(maximum_step_calls):
        instruction = execute_llm_step(**call_kwargs)  # needs events here too
```

## 7. Test Infrastructure

### Existing Pattern (test_step_lifecycle_events.py)
- Uses `conftest.py` fixtures: `MockProvider`, `SuccessPipeline`, `SkipPipeline`, `seeded_session`, `in_memory_handler`
- `MockProvider.call_structured()` returns `LLMCallResult.success(parsed=response, raw_response="mock response", model_name="mock-model", attempt_count=1)`
- Tests filter `in_memory_handler.get_events()` by `event_type` string
- Each event class gets its own test class
- Ordering tests verify event sequence

### conftest.py Adequacy
- `MockProvider` already returns `LLMCallResult` with all fields needed by `LLMCallCompleted`
- `seeded_session` already has prompts with templates (`"Process: {data}"`) -- sufficient for rendered prompt testing
- No changes needed to conftest.py

## 8. Files Requiring Changes (Implementation Phase)

| File | Change | Scope |
|------|--------|-------|
| `llm_pipeline/llm/executor.py` | Add `execute_llm_step_with_metadata()` returning enriched result | New function, ~40 lines |
| `llm_pipeline/pipeline.py` | Add LLMCallPrepared/Starting/Completed emissions in execute() and _execute_with_consensus() | ~30 lines of event emission code |
| `llm_pipeline/pipeline.py` | Import LLMCallPrepared, LLMCallStarting, LLMCallCompleted | 1 import line |
| `tests/events/test_llm_call_events.py` | New test file for all 3 events | ~200 lines |

## 9. Files NOT Requiring Changes

| File | Reason |
|------|--------|
| `events/types.py` | Event classes already defined |
| `events/__init__.py` | Already exports LLM call events |
| `events/emitter.py` | Protocol unchanged |
| `events/handlers.py` | Generic handlers work with any event type, CATEGORY_LLM_CALL already mapped |
| `events/models.py` | PipelineEventRecord is generic |
| `tests/events/conftest.py` | MockProvider already returns LLMCallResult with needed fields |

## 10. Key Code References

### executor.py -- Prompt rendering (L68-102)
```python
# Variables dict conversion
if hasattr(variables, "model_dump"):
    variables_dict = variables.model_dump()
else:
    variables_dict = variables

# System instruction rendering
if system_variables_dict:
    system_instruction = prompt_service.get_system_prompt(system_instruction_key, variables=system_variables_dict, ...)
else:
    system_instruction = prompt_service.get_prompt(system_instruction_key, prompt_type="system", ...)

# User prompt rendering
user_prompt = prompt_service.get_user_prompt(user_prompt_key, variables=variables_dict, ...)
```

### executor.py -- LLM call (L105-111)
```python
result: LLMCallResult = provider.call_structured(
    prompt=user_prompt,
    system_instruction=system_instruction,
    result_class=result_class,
    array_validation=array_validation,
    validation_context=validation_context,
)
```

### LLMCallResult (result.py)
```python
@dataclass(frozen=True, slots=True)
class LLMCallResult:
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)
```

### PromptService rendering (service.py L86-168)
- `get_system_prompt()` -- fetches template from DB, calls `template.format(**variables)`
- `get_user_prompt()` -- same pattern for user prompts
- Both return fully rendered strings

## 11. Summary

Event types exist. Emission infrastructure exists. The gap is purely in **wiring**: `execute_llm_step()` discards rendered prompts and LLMCallResult before returning to pipeline.py. The recommended approach (Option D) adds a metadata-returning variant function, letting pipeline.py emit all three LLM call events while maintaining backward compatibility and the established pattern of pipeline-owned event emission.
