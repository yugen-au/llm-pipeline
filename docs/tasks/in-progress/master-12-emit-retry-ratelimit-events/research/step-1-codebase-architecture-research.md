# Codebase Architecture Research: Retry/RateLimit Event Emission

## 1. Event Type Definitions (Already Exist)

All three event types are already defined in `llm_pipeline/events/types.py` (lines 347-378) and exported from `llm_pipeline/events/__init__.py`. No new type definitions needed.

### LLMCallRetry (line 348)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallRetry(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    attempt: int          # current attempt (1-indexed)
    max_retries: int      # total allowed retries
    error_type: str       # category of failure
    error_message: str    # human-readable error detail
```

### LLMCallFailed (line 360)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallFailed(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    max_retries: int
    last_error: str
```

### LLMCallRateLimited (line 369)
```python
@dataclass(frozen=True, slots=True, kw_only=True)
class LLMCallRateLimited(StepScopedEvent):
    EVENT_CATEGORY: ClassVar[str] = CATEGORY_LLM_CALL
    attempt: int
    wait_seconds: float
    backoff_type: str     # 'api_suggested' or 'exponential'
```

All inherit from `StepScopedEvent` which provides `run_id`, `pipeline_name`, `step_name`, `timestamp`, `event_type` (auto-derived from class name).

## 2. GeminiProvider Retry Loop (gemini.py:69-244)

### Current Signature
```python
def call_structured(
    self, prompt, system_instruction, result_class,
    max_retries=3, not_found_indicators=None, strict_types=True,
    array_validation=None, validation_context=None, **kwargs
) -> LLMCallResult:
```

No event_emitter or context params. The `**kwargs` catches any extra keyword args.

### Retry Points (emit LLMCallRetry)

| Line | Trigger | Proposed error_type |
|------|---------|-------------------|
| 109 | Empty/no response from Gemini | `empty_response` |
| 148 | JSON decode error | `json_parse_error` |
| 161-163 | Schema validation failed | `validation_error` |
| 177-179 | Array validation failed | `array_validation_error` |
| 195-197 | Pydantic validation failed | `pydantic_validation_error` |
| 230-235 | General API error (non-rate-limit) | `api_error` |

### Rate Limit Points (emit LLMCallRateLimited)

| Line | Trigger | backoff_type |
|------|---------|-------------|
| 218-222 | `extract_retry_delay_from_error(e)` returns value | `api_suggested` |
| 224-228 | Fallback exponential backoff `2**attempt` | `exponential` |

### Failure Point (emit LLMCallFailed)

Line 237-244: After `for attempt` loop exhausts `max_retries`. Return `LLMCallResult(parsed=None, ...)`.

`last_error`: Use `accumulated_errors[-1]` if non-empty, else `"All {max_retries} attempts failed"`.

## 3. Call Chain & Event Context Threading

```
pipeline.py execute()
  -> injects event_emitter, run_id, pipeline_name, step_name into call_kwargs
    -> executor.py execute_llm_step()
      -> emits LLMCallStarting/LLMCallCompleted
      -> calls provider.call_structured(prompt, system_instruction, result_class, ...)
        -> GeminiProvider retry loop (NO event context currently)
```

### Threading Approach

executor.py (line 134-140) must pass event context to provider:

```python
result: LLMCallResult = provider.call_structured(
    prompt=user_prompt,
    system_instruction=system_instruction,
    result_class=result_class,
    array_validation=array_validation,
    validation_context=validation_context,
    # NEW: pass event context for retry/ratelimit emissions
    event_emitter=event_emitter,
    run_id=run_id,
    pipeline_name=pipeline_name,
    step_name=step_name,
)
```

GeminiProvider receives these via `**kwargs` (no ABC change needed). Extract at top of `call_structured()`:

```python
event_emitter = kwargs.get("event_emitter")
run_id = kwargs.get("run_id", "")
pipeline_name = kwargs.get("pipeline_name", "")
step_name = kwargs.get("step_name")
```

## 4. LLMProvider ABC (provider.py)

Abstract `call_structured()` signature has `**kwargs`. GeminiProvider can accept new optional params without modifying the ABC. Other future providers inherit the same pattern via `**kwargs`. No ABC change required.

## 5. Event Emission Pattern (established by task 11)

Pattern from executor.py:
- Guard with `if event_emitter:` before any emission
- Lazy-import event types inside the guard block (or at function top)
- Zero overhead when no emitter configured
- All events carry `run_id`, `pipeline_name` from pipeline context

Pattern for GeminiProvider (new):
- Extract event context from `**kwargs` at top of `call_structured()`
- Guard each emission point with `if event_emitter:`
- Emit BEFORE the `continue` (for retries) or BEFORE the `time.sleep()` (for rate limits)
- Emit LLMCallFailed BEFORE the final `return LLMCallResult(parsed=None, ...)`

## 6. Emission Sequence Per Attempt

### Validation Retry (attempt N, not last):
1. `LLMCallRetry(attempt=N+1, max_retries=max_retries, error_type=..., error_message=...)`
2. `continue` (next attempt)

### Rate Limit (attempt N, not last):
1. `LLMCallRateLimited(attempt=N+1, wait_seconds=delay, backoff_type=...)`
2. `LLMCallRetry(attempt=N+1, max_retries=max_retries, error_type='rate_limit', error_message=str(e))`
3. `time.sleep(delay)`
4. `continue`

### All Retries Exhausted:
1. `LLMCallFailed(max_retries=max_retries, last_error=accumulated_errors[-1])`
2. `return LLMCallResult(parsed=None, ...)`

## 7. Files to Modify

| File | Changes |
|------|---------|
| `llm_pipeline/llm/gemini.py` | Extract event context from kwargs, emit LLMCallRetry at each retry point, emit LLMCallRateLimited before rate-limit sleep, emit LLMCallFailed after loop exhaustion |
| `llm_pipeline/llm/executor.py` | Pass event_emitter, run_id, pipeline_name, step_name to provider.call_structured() |

No changes needed to:
- `events/types.py` (types already defined)
- `events/__init__.py` (already exported)
- `events/emitter.py` (unchanged)
- `events/handlers.py` (unchanged)
- `llm_pipeline/llm/provider.py` (ABC unchanged, uses **kwargs)
- `pipeline.py` (already injects event context into call_kwargs)

## 8. Test Strategy

Follow test pattern from `tests/events/test_llm_call_events.py`:
- Use `MockProvider` subclass that triggers retries (override `call_structured` or mock Gemini API)
- Direct GeminiProvider unit tests (mock `genai.GenerativeModel` responses)
- Verify LLMCallRetry emitted per retry with correct error_type
- Verify LLMCallRateLimited emitted with wait_seconds and backoff_type
- Verify LLMCallFailed emitted after exhausting retries
- Verify zero-overhead when event_emitter is None
- Test event field values match actual error conditions

## 9. Backward Compatibility

- All new params optional via `**kwargs` extraction with defaults
- Existing callers of `call_structured()` unaffected (they don't pass event context)
- Existing callers of `execute_llm_step()` unaffected (event_emitter already optional with None default)
- No signature changes to ABC or public interfaces
