# Step 1: Codebase Architecture Research

## Critical Finding: LLMCallResult Already Exists

Task 1 (master-1-pipeline-event-types, completed) created `LLMCallResult` at `llm_pipeline/llm/result.py` with the exact 5 fields specified by Task 3:

```python
@dataclass(frozen=True, slots=True)
class LLMCallResult:
    parsed: dict[str, Any] | None = None
    raw_response: str | None = None
    model_name: str | None = None
    attempt_count: int = 1
    validation_errors: list[str] = field(default_factory=list)
```

Current exports:
- `llm_pipeline.llm.result` (canonical location)
- `llm_pipeline.llm.__init__` (re-exports LLMCallResult)
- `llm_pipeline.events.__init__` (re-exports from llm.result)

Task 3 spec says "Create `llm_pipeline/events/result.py`" but file lives at `llm_pipeline/llm/result.py`. Task 4 (downstream) says "Import LLMCallResult from events.result" which would need a file at `events/result.py`.

---

## Module Structure

```
llm_pipeline/
  __init__.py          - Package exports (no LLMCallResult or events yet)
  pipeline.py          - PipelineConfig orchestrator
  step.py              - LLMStep ABC, LLMResultMixin, step_definition decorator
  strategy.py          - PipelineStrategy ABC, PipelineStrategies, StepDefinition
  context.py           - PipelineContext (Pydantic BaseModel)
  state.py             - PipelineStepState, PipelineRunInstance (SQLModel)
  types.py             - ArrayValidationConfig, ValidationContext, TypedDicts
  extraction.py        - PipelineExtraction
  transformation.py    - PipelineTransformation
  registry.py          - PipelineDatabaseRegistry
  events/
    __init__.py         - Re-exports all 31 events + LLMCallResult + category constants
    types.py            - PipelineEvent base, StepScopedEvent, 31 concrete event classes
  llm/
    __init__.py         - Exports LLMProvider, RateLimiter, LLMCallResult, schema utils
    provider.py         - LLMProvider ABC (call_structured -> Optional[Dict])
    gemini.py           - GeminiProvider (concrete, returns Optional[Dict])
    result.py           - LLMCallResult dataclass
    schema.py           - Schema flattening/formatting for LLM prompts
    validation.py       - Response validation utilities
    executor.py         - execute_llm_step() orchestrator
    rate_limiter.py     - RateLimiter
  prompts/
    __init__.py         - PromptService, VariableResolver exports
    service.py          - PromptService
    loader.py           - Prompt loading utilities
    variables.py        - VariableResolver
  session/
    __init__.py         - ReadOnlySession export
    readonly.py         - ReadOnlySession wrapper
  db/
    __init__.py         - init_pipeline_db, Prompt export
    prompt.py           - Prompt SQLModel
```

---

## call_structured() Flow

### LLMProvider ABC (`llm/provider.py`)

```python
@abstractmethod
def call_structured(
    self, prompt, system_instruction, result_class,
    max_retries=3, not_found_indicators=None, strict_types=True,
    array_validation=None, validation_context=None, **kwargs
) -> Optional[Dict[str, Any]]:
```

Returns `Optional[Dict[str, Any]]` - validated JSON dict or None on total failure.

### GeminiProvider (`llm/gemini.py`)

Retry loop (lines 86-216):
1. Rate limiter wait
2. Gemini API call via `genai.GenerativeModel.generate_content()`
3. Not-found indicator check -> returns `None` early
4. JSON extraction (code fence or raw braces)
5. `json.loads()` parse -> `continue` on JSONDecodeError
6. `validate_structured_output()` schema check -> `continue` on failure
7. `validate_array_response()` if array_validation -> `continue` on failure
8. Pydantic model validation (result_class) -> `continue` on failure
9. Success: `return response_json` (the dict)
10. Rate limit handling: exponential backoff with API-suggested delay
11. All retries exhausted: `return None`

Key data points currently LOST (not returned):
- `response.text` (raw_response) - captured in local var `response_text` but not returned
- attempt number - loop variable `attempt` not exposed
- validation error strings - logged but not collected
- model name - available as `self.model_name` but not returned

### execute_llm_step() (`llm/executor.py`)

Calls `provider.call_structured()` at line 103, stores in `result_dict`. If None, calls `result_class.create_failure()`. Otherwise validates with Pydantic and returns the instruction object. This is the integration point where Task 4 will need to handle LLMCallResult instead of Optional[Dict].

---

## Event System (Task 1)

### Pattern: frozen+slots dataclasses with auto-registration

```python
@dataclass(frozen=True, slots=True)
class PipelineEvent:
    run_id: str
    pipeline_name: str
    timestamp: datetime = field(default_factory=utc_now)
    event_type: str = field(init=False)  # derived via __init_subclass__
```

- `__init_subclass__` auto-registers subclasses in `_EVENT_REGISTRY`
- `to_dict()` / `to_json()` serialization
- `resolve_event()` class method for deserialization
- `StepScopedEvent` intermediate adds `step_name: str | None`
- 31 concrete events across 9 categories
- `EVENT_CATEGORY: ClassVar[str]` on each concrete event

### LLMCallCompleted event (already captures same data as LLMCallResult):

```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallCompleted(StepScopedEvent):
    call_index: int
    raw_response: str | None
    parsed_result: dict[str, Any] | None
    model_name: str | None
    attempt_count: int
    validation_errors: list[str] = field(default_factory=list)
```

Note field name difference: `parsed_result` in event vs `parsed` in LLMCallResult.

---

## Dataclass/Pydantic Patterns

### Dataclass pattern (events, types, LLMCallResult):
- `@dataclass(frozen=True, slots=True)` for immutable, memory-efficient records
- `field(default_factory=list)` for mutable defaults
- No `from __future__ import annotations` in types.py (slots+super() CPython issue)
- `from __future__ import annotations` used in result.py (no __init_subclass__)

### Pydantic BaseModel pattern (domain models, context):
- `PipelineContext(BaseModel)` - step context contributions
- `LLMResultMixin(BaseModel)` - LLM instruction results with confidence_score/notes
- `ArrayValidationConfig` and `ValidationContext` are plain dataclasses (not Pydantic)

### SQLModel pattern (state, persistence):
- `PipelineStepState(SQLModel, table=True)` - step audit trail
- `PipelineRunInstance(SQLModel, table=True)` - instance tracking

---

## PipelineStepState Fields

```python
class PipelineStepState(SQLModel, table=True):
    id, pipeline_name, run_id, step_name, step_number,
    input_hash, result_data (JSON), context_snapshot (JSON),
    prompt_system_key, prompt_user_key, prompt_version, model,
    created_at, execution_time_ms
```

Note: `model` field exists (str, max 50) for LLM model tracking. Currently not populated during `_save_step_state()` (pipeline.py:701-715).

---

## Integration Points for LLMCallResult

1. **GeminiProvider.call_structured()** (Task 4): Must build LLMCallResult at all exit points instead of returning dict/None
2. **execute_llm_step()** (Task 4+): Must handle LLMCallResult.parsed instead of raw dict; can pass richer error info
3. **LLMCallCompleted event**: Overlapping fields with LLMCallResult. Event could be constructed FROM LLMCallResult
4. **PipelineStepState.model**: Could be populated from LLMCallResult.model_name
5. **Pipeline consensus** (`_execute_with_consensus`): Currently compares instruction objects. If LLMCallResult wraps them, comparison logic may need adjustment

---

## Downstream Task Boundaries

### Task 4 (pending) - OUT OF SCOPE:
- Change call_structured() return type to LLMCallResult
- Update GeminiProvider to build LLMCallResult
- Track raw_response, attempt_count, validation_errors, model_name

### Task 18 (pending) - OUT OF SCOPE:
- Export LLMCallResult and all events from llm_pipeline/__init__.py

---

## Questions Requiring CEO Input

1. **Task scope overlap**: LLMCallResult already exists at `llm_pipeline/llm/result.py` with exact Task 3 fields (created in Task 1). What additional work does Task 3 need? Options: (a) add serialization methods + tests, (b) relocate file to events/result.py, (c) mark Task 3 done as-is, (d) other.

2. **Canonical file location**: Task 3 spec says `events/result.py`, Task 4 says "import from events.result". Current location is `llm/result.py` with re-export from `events/__init__.py`. Which should be canonical? `llm/result.py` is architecturally cleaner (LLM domain, not an event). `events/result.py` matches task specs.

3. **Serialization methods**: Task 3 testStrategy mentions "serialization" testing. Current LLMCallResult has no methods. PipelineEvent has `to_dict()`/`to_json()`. Should LLMCallResult get similar serialization? `dataclasses.asdict()` works externally but explicit methods improve API consistency.
